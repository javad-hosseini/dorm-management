import re
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.conf import settings

from apps.dormitory.models import Resident
from apps.dormitory.services.excel_export import get_active_debtor_residents
from .models import Contact, SmsCampaign, SmsRecipientLog
from .forms import SmsComposerForm
from .utils import (
    DEFAULT_DEBT_REMINDER_TEMPLATE,
    DEFAULT_GENERAL_ANNOUNCEMENT_TEMPLATE,
    calculate_resident_debt_details,
)
from .services import (
    send_campaign,
    prepare_campaign_preview,
)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    """
    Admin for Contact Book entries (non-resident individuals, staff, emergency numbers).
    """

    list_display = [
        "full_name",
        "phone_number_display",
        "notes_preview",
        "created_at",
        "updated_at",
    ]
    search_fields = ["full_name", "phone_number", "notes"]
    list_filter = ["created_at"]
    ordering = ["-created_at"]
    actions = ["send_sms_to_selected_contacts"]

    def phone_number_display(self, obj):
        return format_html('<span dir="ltr" class="font-weight-bold">{}</span>', obj.phone_number)

    phone_number_display.short_description = "شماره موبایل"
    phone_number_display.admin_order_field = "phone_number"

    def notes_preview(self, obj):
        if not obj.notes:
            return "-"
        return obj.notes[:50] + ("..." if len(obj.notes) > 50 else "")

    notes_preview.short_description = "یادداشت"

    @admin.action(description="ارسال پیامک به مخاطبین انتخاب‌شده")
    def send_sms_to_selected_contacts(self, request, queryset):
        ids = list(queryset.values_list("id", flat=True))
        if not ids:
            self.message_user(request, "هیچ مخاطبی انتخاب نشده است.", level=messages.WARNING)
            return
        send_url = reverse("admin:sms_service_send")
        return redirect(f"{send_url}?contact_ids={','.join(map(str, ids))}")


class SmsRecipientLogInline(admin.TabularInline):
    """
    Inline audit log for recipients within an SMS campaign.
    """

    model = SmsRecipientLog
    extra = 0
    can_delete = False
    max_num = 0
    readonly_fields = [
        "recipient_type_display",
        "recipient_name_display",
        "phone_number",
        "final_message",
        "status_badge",
        "provider_rec_id",
        "error_message",
        "created_at",
    ]
    fields = [
        "recipient_type_display",
        "recipient_name_display",
        "phone_number",
        "status_badge",
        "provider_rec_id",
        "final_message",
        "error_message",
        "created_at",
    ]

    def has_add_permission(self, request, obj=None):
        return False

    def recipient_type_display(self, obj):
        if obj.recipient_type == SmsRecipientLog.RecipientType.RESIDENT:
            return format_html('<span class="badge badge-primary">ساکن خوابگاه</span>')
        elif obj.recipient_type == SmsRecipientLog.RecipientType.CONTACT:
            return format_html('<span class="badge badge-info">دفترچه تلفن</span>')
        return format_html('<span class="badge badge-secondary">کاربر سیستم</span>')

    recipient_type_display.short_description = "نوع مخاطب"

    def recipient_name_display(self, obj):
        if obj.resident:
            room_str = f" (اتاق {obj.resident.room.room_number})" if obj.resident.room else ""
            return f"{obj.resident.full_name}{room_str}"
        if obj.contact:
            return obj.contact.full_name
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return "-"

    recipient_name_display.short_description = "نام مخاطب"

    def status_badge(self, obj):
        colors = {
            SmsRecipientLog.Status.SUCCESS: "success",
            SmsRecipientLog.Status.BLOCKED_ADVERTISING: "danger",
            SmsRecipientLog.Status.FAILED: "danger",
            SmsRecipientLog.Status.SKIPPED_DUPLICATE: "warning",
            SmsRecipientLog.Status.SKIPPED_INVALID: "secondary",
        }
        badge_cls = colors.get(obj.status, "secondary")
        icon = ""
        if obj.status == SmsRecipientLog.Status.BLOCKED_ADVERTISING:
            icon = '<i class="fas fa-ban ml-1"></i> '
        elif obj.status == SmsRecipientLog.Status.SUCCESS:
            icon = '<i class="fas fa-check ml-1"></i> '
        return format_html(
            '<span class="badge badge-{}">{}{}</span>',
            badge_cls,
            format_html(icon),
            obj.get_status_display(),
        )

    status_badge.short_description = "وضعیت"


@admin.register(SmsCampaign)
class SmsCampaignAdmin(admin.ModelAdmin):
    """
    Admin interface for SMS Campaigns and main access point for the Send SMS Center.
    """

    list_display = [
        "id",
        "sender_display",
        "short_message",
        "recipient_source_badge",
        "total_selected",
        "total_deduplicated",
        "successful_count",
        "blocked_count",
        "failed_count",
        "status_badge",
        "created_at",
    ]
    list_filter = ["status", "recipient_source", "created_at"]
    search_fields = ["message_body", "sender__username", "sender__first_name", "sender__last_name"]
    ordering = ["-created_at"]
    readonly_fields = [
        "sender",
        "message_body",
        "recipient_source",
        "total_selected",
        "total_deduplicated",
        "successful_count",
        "blocked_count",
        "failed_count",
        "status",
        "created_at",
    ]
    inlines = [SmsRecipientLogInline]

    def has_add_permission(self, request):
        return False

    def sender_display(self, obj):
        if not obj.sender:
            return "سیستم"
        return obj.sender.get_full_name() or obj.sender.username

    sender_display.short_description = "ارسال‌کننده"

    def recipient_source_badge(self, obj):
        badges = {
            SmsCampaign.Source.RESIDENTS: ("primary", "ساکنین خوابگاه"),
            SmsCampaign.Source.DEBTORS: ("danger", "بدهکاران خوابگاه"),
            SmsCampaign.Source.CONTACTS: ("info", "دفترچه تلفن"),
            SmsCampaign.Source.MIXED: ("warning", "ترکیبی"),
            SmsCampaign.Source.USERS: ("secondary", "کاربران سیستم"),
        }
        color, label = badges.get(obj.recipient_source, ("secondary", obj.get_recipient_source_display()))
        return format_html('<span class="badge badge-{}">{}</span>', color, label)

    recipient_source_badge.short_description = "منبع"

    def status_badge(self, obj):
        colors = {
            SmsCampaign.Status.COMPLETED: "success",
            SmsCampaign.Status.PARTIAL_FAILURE: "warning",
            SmsCampaign.Status.FAILED: "danger",
            SmsCampaign.Status.PENDING: "info",
        }
        color = colors.get(obj.status, "secondary")
        return format_html('<span class="badge badge-{}">{}</span>', color, obj.get_status_display())

    status_badge.short_description = "وضعیت"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        try:
            campaign = self.get_object(request, object_id)
            if campaign:
                recipients = list(
                    campaign.recipients.select_related("resident", "contact", "user", "resident__room")
                    .order_by("status", "resident__last_name", "contact__full_name")
                )
                successful = [r for r in recipients if r.status == SmsRecipientLog.Status.SUCCESS]
                blocked = [r for r in recipients if r.status == SmsRecipientLog.Status.BLOCKED_ADVERTISING]
                failed = [r for r in recipients if r.status == SmsRecipientLog.Status.FAILED]
                skipped = [
                    r for r in recipients
                    if r.status in (SmsRecipientLog.Status.SKIPPED_DUPLICATE, SmsRecipientLog.Status.SKIPPED_INVALID)
                ]

                failed_res_ids = [r.resident_id for r in (blocked + failed) if r.resident_id]
                failed_cnt_ids = [r.contact_id for r in (blocked + failed) if r.contact_id]

                extra_context.update({
                    "campaign_obj": campaign,
                    "successful_logs": successful,
                    "blocked_logs": blocked,
                    "failed_logs": failed,
                    "skipped_logs": skipped,
                    "successful_count": len(successful),
                    "blocked_count": len(blocked),
                    "failed_count": len(failed),
                    "skipped_count": len(skipped),
                    "failed_res_ids_csv": ",".join(map(str, failed_res_ids)),
                    "failed_cnt_ids_csv": ",".join(map(str, failed_cnt_ids)),
                })
        except Exception:
            pass
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "send/",
                self.admin_site.admin_view(self.sms_send_view),
                name="sms_service_send",
            ),
        ]
        return custom_urls + urls

    def sms_send_view(self, request):
        """
        Interactive Send SMS Center view with resident/debtor selection,
        smart template tags, preview, and parallel dispatch.
        """
        if not (request.user.is_staff and (request.user.is_superuser or request.user.has_perm("sms_service.add_smscampaign"))):
            raise PermissionDenied("شما مجوز دسترسی به مرکز ارسال پیامک را ندارید.")

        is_console_mode = getattr(settings, "SMS_CONSOLE_MODE", False) or not (
            getattr(settings, "MELIPAYAMAK_API_TOKEN", "")
            and getattr(settings, "MELIPAYAMAK_SENDER", "")
        )

        active_debtors = get_active_debtor_residents()
        all_active_residents = list(
            Resident.objects.filter(status=Resident.Status.ACTIVE)
            .select_related("room", "dormitory")
            .order_by("room__room_number", "last_name", "first_name")
        )
        contacts = list(Contact.objects.all().order_by("-created_at"))

        if request.method == "POST":
            step = request.POST.get("step", "preview")
            message_body = request.POST.get("message_body", "").strip()

            raw_resident_ids = request.POST.getlist("selected_residents")
            csv_resident_ids = request.POST.get("selected_residents_csv", "")
            if csv_resident_ids:
                raw_resident_ids.extend([x.strip() for x in csv_resident_ids.split(",") if x.strip()])

            raw_contact_ids = request.POST.getlist("selected_contacts")
            csv_contact_ids = request.POST.get("selected_contacts_csv", "")
            if csv_contact_ids:
                raw_contact_ids.extend([x.strip() for x in csv_contact_ids.split(",") if x.strip()])

            select_all_debtors = request.POST.get("select_all_debtors") == "1"
            select_all_active = request.POST.get("select_all_active") == "1"
            select_all_contacts = request.POST.get("select_all_contacts") == "1"

            if select_all_debtors:
                resident_ids = [r.id for r in active_debtors]
            elif select_all_active:
                resident_ids = [r.id for r in all_active_residents]
            else:
                resident_ids = list(dict.fromkeys([int(rid) for rid in raw_resident_ids if str(rid).isdigit()]))

            if select_all_contacts:
                contact_ids = [c.id for c in contacts]
            else:
                contact_ids = list(dict.fromkeys([int(cid) for cid in raw_contact_ids if str(cid).isdigit()]))

            # Validation
            form = SmsComposerForm(request.POST)
            if not form.is_valid():
                messages.error(request, "لطفاً متن پیامک معتبری وارد کنید.")
                return self._render_composer(
                    request,
                    form=form,
                    preselected_resident_ids=resident_ids,
                    preselected_contact_ids=contact_ids,
                    is_console_mode=is_console_mode,
                    active_debtors=active_debtors,
                    all_active_residents=all_active_residents,
                    contacts=contacts,
                )

            if not resident_ids and not contact_ids:
                messages.error(request, "لطفاً حداقل یک مخاطب یا ساکن را انتخاب کنید.")
                return self._render_composer(
                    request,
                    form=form,
                    preselected_resident_ids=resident_ids,
                    preselected_contact_ids=contact_ids,
                    is_console_mode=is_console_mode,
                    active_debtors=active_debtors,
                    all_active_residents=all_active_residents,
                    contacts=contacts,
                )

            # Step 1: Confirmation & Preview
            if step == "preview":
                preview = prepare_campaign_preview(
                    resident_ids=resident_ids,
                    contact_ids=contact_ids,
                    message_body=message_body,
                )
                if preview["valid_count"] == 0:
                    messages.error(
                        request,
                        "هیچ شماره موبایل معتبری در میان مخاطبین انتخاب‌شده وجود ندارد.",
                    )
                    return self._render_composer(
                        request,
                        form=form,
                        preselected_resident_ids=resident_ids,
                        preselected_contact_ids=contact_ids,
                        is_console_mode=is_console_mode,
                        active_debtors=active_debtors,
                        all_active_residents=all_active_residents,
                        contacts=contacts,
                    )

                context = {
                    **self.admin_site.each_context(request),
                    "title": "تأیید و بازبینی نهایی ارسال پیامک",
                    "preview": preview,
                    "message_body": message_body,
                    "resident_ids": resident_ids,
                    "contact_ids": contact_ids,
                    "is_console_mode": is_console_mode,
                }
                return render(request, "admin/sms_service/send_confirm.html", context)

            # Step 2: Final Execute POST
            elif step == "execute":
                result = send_campaign(
                    sender_user=request.user,
                    resident_ids=resident_ids,
                    contact_ids=contact_ids,
                    message_body=message_body,
                )
                campaign = result["campaign"]
                s_count = result["successful_count"]
                b_count = result.get("blocked_count", 0)
                f_count = result["failed_count"]

                # 1. Main summary message
                if campaign.status == SmsCampaign.Status.COMPLETED:
                    messages.success(
                        request,
                        f"✅ کمپین پیامک #{campaign.id} با موفقیت ارسال شد: هر {s_count} پیامک با موفقیت تحویل سامانه گردید.",
                    )
                elif campaign.status == SmsCampaign.Status.PARTIAL_FAILURE:
                    messages.warning(
                        request,
                        f"⚠️ کمپین پیامک #{campaign.id} با موفقیت جزئی ارسال شد: {s_count} ارسال موفق، {f_count} ارسال ناموفق.",
                    )
                else:
                    messages.error(
                        request,
                        f"❌ ارسال کمپین پیامک #{campaign.id} ناموفق بود: تمام {f_count} تلاش با خطا مواجه شدند.",
                    )

                # 2. Detailed list: Who received it
                if result.get("successful_recipients"):
                    succ_items = []
                    for r in result["successful_recipients"][:10]:
                        detail = f" ({r['details']})" if r.get("details") else ""
                        succ_items.append(f"{r['name']}{detail}")
                    remaining = len(result["successful_recipients"]) - 10
                    more_str = f" و {remaining} نفر دیگر" if remaining > 0 else ""
                    messages.info(
                        request,
                        format_html(
                            '<strong>✅ پیامک برای این افراد ارسال شد ({} نفر):</strong> {}',
                            s_count,
                            " ، ".join(succ_items) + more_str,
                        ),
                    )

                # 3. Detailed list: Who had advertising SMS blocked (Blacklist)
                if result.get("blocked_recipients"):
                    blocked_items = []
                    for r in result["blocked_recipients"]:
                        detail = f" ({r['details']})" if r.get("details") else ""
                        blocked_items.append(f"{r['name']}{detail} - {r['phone_number']}")
                    messages.error(
                        request,
                        format_html(
                            '<strong>⛔ مسدود به دلیل بستن پیامک‌های تبلیغاتی ({} نفر):</strong> پیامک به شماره‌های زیر تحویل نشد چون دریافت پیامک‌های تبلیغاتی (خط ۵۰۰۰) را مسدود کرده‌اند: {} <br><small>💡 راهکار: با این افراد تماس تلفنی بگیرید یا به صورت حضوری در خوابگاه اطلاع‌رسانی فرمایید.</small>',
                            b_count,
                            " ، ".join(blocked_items),
                        ),
                    )

                # 4. Detailed list: Other failures
                if result.get("failed_recipients"):
                    failed_items = []
                    for r in result["failed_recipients"][:5]:
                        detail = f" ({r['details']})" if r.get("details") else ""
                        err_snip = f" (خطا: {r['error_message'][:60]})" if r.get("error_message") else ""
                        failed_items.append(f"{r['name']}{detail}{err_snip}")
                    remaining = len(result["failed_recipients"]) - 5
                    more_str = f" و {remaining} مورد دیگر" if remaining > 0 else ""
                    messages.error(
                        request,
                        format_html(
                            '<strong>❌ عدم ارسال به دلیل خطای درگاه ({} نفر):</strong> {}',
                            len(result["failed_recipients"]),
                            " ، ".join(failed_items) + more_str,
                        ),
                    )

                if result["skipped_duplicates"] > 0:
                    messages.info(
                        request,
                        f"ℹ️ {result['skipped_duplicates']} شماره تکراری حذف شدند و فقط یک‌بار پیامک دریافت کردند.",
                    )

                return redirect("admin:sms_service_smscampaign_change", object_id=campaign.id)

        # GET request
        preselected_residents = []
        res_param = request.GET.get("resident_ids", "")
        if res_param:
            preselected_residents = [int(x) for x in res_param.split(",") if x.strip().isdigit()]

        filter_param = request.GET.get("filter", "")
        if filter_param == "debtors" and not preselected_residents:
            preselected_residents = [r.id for r in active_debtors]

        preselected_contacts = []
        contact_param = request.GET.get("contact_ids", "")
        if contact_param:
            preselected_contacts = [int(x) for x in contact_param.split(",") if x.strip().isdigit()]

        initial_message = DEFAULT_DEBT_REMINDER_TEMPLATE if (filter_param == "debtors" or request.GET.get("template") == "debt") else ""
        form = SmsComposerForm(initial={"message_body": initial_message})

        return self._render_composer(
            request,
            form=form,
            preselected_resident_ids=preselected_residents,
            preselected_contact_ids=preselected_contacts,
            is_console_mode=is_console_mode,
            active_debtors=active_debtors,
            all_active_residents=all_active_residents,
            contacts=contacts,
        )

    def _render_composer(
        self,
        request,
        form,
        preselected_resident_ids,
        preselected_contact_ids,
        is_console_mode,
        active_debtors,
        all_active_residents,
        contacts,
    ):
        # Sample resident for previewing smart tags in real time
        sample_resident = active_debtors[0] if active_debtors else (all_active_residents[0] if all_active_residents else None)
        sample_data = calculate_resident_debt_details(sample_resident) if sample_resident else {}

        # Precompute debtor summary
        total_debtors_count = len(active_debtors)
        total_active_count = len(all_active_residents)
        total_contacts_count = len(contacts)

        # Query panel credit
        from .services.provider import get_sms_provider
        provider = get_sms_provider()
        panel_credit = provider.get_credit()

        context = {
            **self.admin_site.each_context(request),
            "title": "مرکز هوشمند ارسال پیامک خوابگاه",
            "form": form,
            "active_debtors": active_debtors,
            "all_active_residents": all_active_residents,
            "contacts": contacts,
            "total_debtors_count": total_debtors_count,
            "total_active_count": total_active_count,
            "total_contacts_count": total_contacts_count,
            "preselected_resident_ids": preselected_resident_ids,
            "preselected_contact_ids": preselected_contact_ids,
            "is_console_mode": is_console_mode,
            "panel_credit": panel_credit,
            "default_debt_template": DEFAULT_DEBT_REMINDER_TEMPLATE,
            "default_general_template": DEFAULT_GENERAL_ANNOUNCEMENT_TEMPLATE,
            "sample_resident": sample_resident,
            "sample_data": sample_data,
        }
        return render(request, "admin/sms_service/send_sms.html", context)


@admin.register(SmsRecipientLog)
class SmsRecipientLogAdmin(admin.ModelAdmin):
    """
    Searchable audit log for individual SMS messages sent.
    """

    list_display = [
        "id",
        "campaign_link",
        "recipient_type_display",
        "recipient_name_display",
        "phone_number",
        "status_badge",
        "provider_rec_id",
        "created_at",
    ]
    list_filter = ["status", "recipient_type", "created_at"]
    search_fields = [
        "phone_number",
        "final_message",
        "provider_rec_id",
        "resident__first_name",
        "resident__last_name",
        "contact__full_name",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def campaign_link(self, obj):
        url = reverse("admin:sms_service_smscampaign_change", args=[obj.campaign.id])
        return format_html('<a href="{}">کمپین #{}</a>', url, obj.campaign.id)

    campaign_link.short_description = "کمپین"

    def recipient_type_display(self, obj):
        if obj.recipient_type == SmsRecipientLog.RecipientType.RESIDENT:
            return format_html('<span class="badge badge-primary">ساکن خوابگاه</span>')
        elif obj.recipient_type == SmsRecipientLog.RecipientType.CONTACT:
            return format_html('<span class="badge badge-info">دفترچه تلفن</span>')
        return format_html('<span class="badge badge-secondary">کاربر سیستم</span>')

    recipient_type_display.short_description = "نوع مخاطب"

    def recipient_name_display(self, obj):
        if obj.resident:
            room_str = f" (اتاق {obj.resident.room.room_number})" if obj.resident.room else ""
            return f"{obj.resident.full_name}{room_str}"
        if obj.contact:
            return obj.contact.full_name
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return "-"

    recipient_name_display.short_description = "نام مخاطب"

    def status_badge(self, obj):
        colors = {
            SmsRecipientLog.Status.SUCCESS: "success",
            SmsRecipientLog.Status.BLOCKED_ADVERTISING: "danger",
            SmsRecipientLog.Status.FAILED: "danger",
            SmsRecipientLog.Status.SKIPPED_DUPLICATE: "warning",
            SmsRecipientLog.Status.SKIPPED_INVALID: "secondary",
        }
        color = colors.get(obj.status, "secondary")
        icon = ""
        if obj.status == SmsRecipientLog.Status.BLOCKED_ADVERTISING:
            icon = '<i class="fas fa-ban ml-1"></i> '
        elif obj.status == SmsRecipientLog.Status.SUCCESS:
            icon = '<i class="fas fa-check ml-1"></i> '
        return format_html('<span class="badge badge-{}">{}{}</span>', color, format_html(icon), obj.get_status_display())

    status_badge.short_description = "وضعیت"
