from django import forms
from django.apps import apps
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db import models
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.html import format_html
from apps.archive.models import ArchivedResident, ArchivedTransaction
from .models import Dormitory, Room, Resident, Transaction


class VacancyFilter(SimpleListFilter):
    """Custom filter for room vacancy status"""
    title = 'Vacancy Status'
    parameter_name = 'vacancy'

    def lookups(self, request, model_admin):
        return (
            ('has_space', '✅ Has Empty Beds'),
            ('full', '❌ Full'),
            ('empty', '🏠 Completely Empty'),
        )

    def queryset(self, request, queryset):
        # Annotate with current occupant count
        queryset = queryset.annotate(
            occupant_count=Count('residents', filter=Q(residents__exit_date__isnull=True))
        )

        if self.value() == 'has_space':
            # Rooms with at least one empty bed
            return queryset.filter(occupant_count__lt=models.F('capacity'))

        if self.value() == 'full':
            # Rooms at full capacity
            return queryset.filter(occupant_count__gte=models.F('capacity'))

        if self.value() == 'empty':
            # Completely empty rooms
            return queryset.filter(occupant_count=0)

        return queryset


# ============================================
# DORMITORY ADMIN
# ============================================
@admin.register(Dormitory)
class DormitoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'total_rooms', 'occupied_rooms', 'empty_rooms', 'total_active_residents']
    search_fields = ['name', 'address']
    list_filter = ['created_at']


# ============================================
# ROOM ADMIN
# ============================================
class RoomForm(forms.ModelForm):
    """Custom form to convert Tomans to Rials"""
    monthly_rent_tomans = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        label="اجاره ماهانه (میلیون تومان)",
        help_text="مبلغ را به میلیون تومان وارد کنید (مثال: 4 برای 4 میلیون تومان، 2.5 برای 2.5 میلیون تومان)"
    )

    class Meta:
        model = Room
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # تبدیل ریال به میلیون تومان
            self.fields['monthly_rent_tomans'].initial = self.instance.monthly_rent / 10000000

    def save(self, commit=True):
        # تبدیل میلیون تومان به ریال
        self.instance.monthly_rent = int(self.cleaned_data['monthly_rent_tomans'] * 10000000)
        return super().save(commit)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    form = RoomForm
    list_display = [
        '__str__', 'dormitory', 'room_number', 'capacity',
        'current_occupants', 'available_capacity', 'vacancy_status', 'monthly_rent_display'
    ]
    list_filter = ['dormitory', 'capacity', VacancyFilter]
    search_fields = ['room_number', 'dormitory__name']
    list_select_related = ['dormitory']

    def monthly_rent_display(self, obj):
        """Show rent in Million Tomans and formatted Tomans"""
        amount_m = obj.monthly_rent / 10000000
        amount_t = obj.monthly_rent // 10
        return format_html('<b>{:,.1f}</b> م.تومان <small style="color:#666;">({:,.0f} تومان)</small>', amount_m, amount_t)

    monthly_rent_display.short_description = "اجاره ماهانه"
    monthly_rent_display.admin_order_field = 'monthly_rent'

    def vacancy_status(self, obj):
        """Show colored vacancy status"""
        available = obj.available_capacity
        if available > 0:
            return format_html(
                '<span style="color: green; font-weight: bold;">{} تخت خالی</span>',
                available
            )
        return format_html('<span style="color: red; font-weight: bold;">تکمیل (پر)</span>')

    vacancy_status.short_description = "وضعیت ظرفیت"

    def get_queryset(self, request):
        """Optimize with resident count annotation"""
        return super().get_queryset(request).annotate(
            _occupant_count=Count('residents', filter=Q(residents__exit_date__isnull=True))
        )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Hide the actual monthly_rent field
        if 'monthly_rent' in form.base_fields:
            form.base_fields['monthly_rent'].widget = forms.HiddenInput()
        return form


# ============================================
# TRANSACTION INLINE (نشون دادن پرداختی‌ها داخل جزئیات ساکن)
# ============================================
class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    fields = [
        'period_name_display', 'amount_display', 'transaction_type',
        'payment_method', 'approval_badge', 'payment_date', 'reference_number', 'view_receipt'
    ]
    readonly_fields = ['period_name_display', 'amount_display', 'approval_badge', 'view_receipt']
    can_delete = False
    show_change_link = True
    ordering = ['-payment_date']

    def period_name_display(self, obj):
        return format_html('<b>{}</b>', obj.period_name or "اجاره ماهانه")

    period_name_display.short_description = "بابت ماه / دوره"

    def amount_display(self, obj):
        """Show amount in Tomans"""
        amount = obj.amount // 10
        return format_html('<b>{:,.0f}</b> تومان', amount)

    amount_display.short_description = "مبلغ"

    def approval_badge(self, obj):
        if obj.is_approved:
            return format_html('<span style="color: #27ae60; font-weight: bold;">✅ تایید شده</span>')
        return format_html('<span style="color: #e74c3c; font-weight: bold;">⏳ در انتظار تایید</span>')

    approval_badge.short_description = "وضعیت تایید"

    def view_receipt(self, obj):
        """Link to view receipt details"""
        if obj.pk:
            url = reverse('admin:dormitory_transaction_change', args=[obj.pk])
            return format_html('<a href="{}" target="_blank">📄 مشاهده رسید</a>', url)
        return "-"

    view_receipt.short_description = "رسید"

    def has_add_permission(self, request, obj):
        return False  # از طریق Transaction admin اضافه کن


# ============================================
# RESIDENT ADMIN
# ============================================
@admin.register(Resident)
class ResidentAdmin(admin.ModelAdmin):
    list_display = [
        'full_name', 'national_code', 'occupation_badge', 'dormitory_link',
        'room_number_display', 'status_badge',
        'entry_date', 'settled_until', 'debt_status', 'payment_summary',
        'view_transactions_link',
    ]
    actions = ['archive_left_residents']

    fieldsets = (
        ('اطلاعات فردی', {
            'fields': ('first_name', 'last_name', 'national_code', 'occupation', 'phone_number', 'parent_phone_number')
        }),
        ('تخصیص اتاق و روز پرداخت', {
            'fields': ('dormitory', 'room', 'monthly_payment_day')
        }),
        ('وضعیت اقامت و تاریخ‌ها', {
            'fields': ('entry_date', 'exit_date', 'settled_until', 'status')
        }),
        ('وضعیت حساب و ریزجزئیات مالی به روز', {
            'fields': ('financial_account_display',),
            'classes': ('wide',)
        }),
        ('امور اداری', {
            'fields': ('registered_by', 'id_card_image')
        }),
        ('تاریخچه پرداخت‌های ثبت‌شده', {
            'fields': ('payment_history_display',),
            'classes': ('wide',)
        }),
    )
    list_filter = [
        'status', 'occupation', 'dormitory', 'entry_date', 'monthly_payment_day', 'settled_until'
    ]
    search_fields = ['first_name', 'last_name', 'national_code', 'phone_number', 'room__room_number']
    readonly_fields = ['created_at', 'financial_account_display', 'payment_history_display']
    list_select_related = ['dormitory', 'room']
    inlines = [TransactionInline]

    def save_model(self, request, obj, form, change):
        if not change and not obj.registered_by_id:
            Supervisor = apps.get_model('accounts', 'Supervisor')
            supervisor = (
                Supervisor.objects.filter(id=request.user.id).first()
                or Supervisor.objects.filter(national_code=getattr(request.user, 'username', '')).first()
                or Supervisor.objects.first()
            )
            if supervisor:
                obj.registered_by = supervisor
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "registered_by":
            Supervisor = apps.get_model('accounts', 'Supervisor')
            supervisor = (
                Supervisor.objects.filter(id=request.user.id).first()
                or Supervisor.objects.filter(national_code=getattr(request.user, 'username', '')).first()
                or Supervisor.objects.first()
            )
            if supervisor:
                kwargs["initial"] = supervisor.id
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def debt_status(self, obj):
        """Show detailed daily debt status with overdue days and unpaid months"""
        summary = obj.financial_status_summary
        status = summary["status"]

        if status == "SETTLED":
            days = summary["days_until_due"]
            due_date = obj.settled_until.strftime('%Y/%m/%d') if obj.settled_until else ''
            return format_html(
                '<div style="white-space: nowrap;">'
                '<span style="background: #27ae60; color: white; padding: 2px 8px; border-radius: 8px; font-weight: bold; font-size: 11px;">🟢 تسویه به روز</span><br>'
                '<small style="color: #27ae60; font-size: 11px;">⏳ {} روز تا سررسید ({})</small>'
                '</div>',
                days, due_date
            )
        elif status == "DUE_TODAY":
            debt_t = summary["debt_tomans"]
            unpaid = summary["unpaid_months"]
            return format_html(
                '<div style="white-space: nowrap;">'
                '<span style="background: #f39c12; color: white; padding: 2px 8px; border-radius: 8px; font-weight: bold; font-size: 11px;">🟡 سررسید امروز</span><br>'
                '<small style="color: #d35400; font-size: 11px;">{} ({:,.0f} ت)</small>'
                '</div>',
                unpaid, debt_t
            )
        elif status == "OVERDUE":
            overdue = summary["overdue_days"]
            debt_t = summary["debt_tomans"]
            unpaid = summary["unpaid_months"]
            return format_html(
                '<div style="white-space: nowrap;">'
                '<span style="background: #e74c3c; color: white; padding: 2px 8px; border-radius: 8px; font-weight: bold; font-size: 11px;">🔴 {} روز تاخیر</span><br>'
                '<small style="color: #c0392b; font-weight: bold; font-size: 11px;">{}</small><br>'
                '<small style="color: #666; font-size: 11px;">بدهی: {:,.0f} تومان</small>'
                '</div>',
                overdue, unpaid, debt_t
            )
        elif status == "NO_ROOM":
            return format_html('<span style="color: #7f8c8d; font-size: 11px;">⚪ بدون اتاق</span>')
        else:
            return format_html('<span style="color: #7f8c8d; font-size: 11px;">⚪ {}</span>', obj.get_status_display())

    debt_status.short_description = "وضعیت تسویه و بدهی"

    def financial_account_display(self, obj):
        """Rich detailed financial account view for resident change form"""
        if not obj.pk:
            return "پس از ذخیره اولیه، محاسبات مالی نمایش داده می‌شود."

        summary = obj.financial_status_summary
        rent_tomans = obj.current_monthly_rent_tomans
        settled_str = obj.settled_until.strftime('%Y/%m/%d') if obj.settled_until else 'ثبت نشده'
        unpaid = obj.unpaid_periods

        if unpaid:
            unpaid_rows = "".join([
                f"<tr style='border-bottom: 1px solid #fee2e2;'>"
                f"<td style='padding: 8px 12px; font-weight: bold; color: #991b1b;'>{p['name']}</td>"
                f"<td style='padding: 8px 12px; color: #666;'>{p['start_date']} تا {p['end_date']}</td>"
                f"<td style='padding: 8px 12px; color: #b91c1c; font-weight: bold;'>{p['overdue_days']} روز تاخیر</td>"
                f"<td style='padding: 8px 12px; font-weight: bold;'>{p['amount_tomans']:,} تومان</td>"
                f"</tr>"
                for p in unpaid
            ])
            table_html = f"""
            <table style='width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; text-align: right; background: white; border-radius: 6px; overflow: hidden; border: 1px solid #fee2e2;'>
                <thead>
                    <tr style='background: #fecaca; color: #991b1b;'>
                        <th style='padding: 8px 12px;'>نام ماه عقب‌افتاده</th>
                        <th style='padding: 8px 12px;'>بازه دوره اجاره</th>
                        <th style='padding: 8px 12px;'>دیرکرد</th>
                        <th style='padding: 8px 12px;'>مبلغ ماهانه</th>
                    </tr>
                </thead>
                <tbody>{unpaid_rows}</tbody>
            </table>
            """
        else:
            table_html = "<div style='color: #27ae60; font-weight: bold; margin-top: 8px; font-size: 13px;'>✅ تمامی ماه‌های اقامت تا این لحظه به طور کامل تسویه هستند.</div>"

        counter_color = "#c0392b" if summary["overdue_days"] > 0 else "#27ae60"
        counter_text = f"{summary['overdue_days']} روز تاخیر" if summary["overdue_days"] > 0 else f"{summary['days_until_due']} روز مانده تا موعد"
        debt_color = "#c0392b" if summary["debt_tomans"] > 0 else "#27ae60"

        return format_html(
            '''
            <div style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 10px; padding: 16px; font-family: tahoma, sans-serif; direction: rtl;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 14px;">
                    <div>
                        <span style="font-size: 14px; font-weight: bold; margin-left: 8px;">وضعیت لحظه‌ای حساب:</span>
                        <span style="background: {color}; color: white; padding: 4px 12px; border-radius: 12px; font-weight: bold; font-size: 12px;">{badge}</span>
                    </div>
                    <div style="font-size: 13px;">
                        <b>اجاره ماهانه اتاق:</b> {rent:,} تومان
                    </div>
                </div>

                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px;">
                    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;">
                        <span style="color: #64748b; font-size: 12px;">تسویه شده تا تاریخ:</span><br>
                        <b style="font-size: 14px; color: #1e293b;">{settled_until}</b>
                    </div>
                    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;">
                        <span style="color: #64748b; font-size: 12px;">شمارنده روزها:</span><br>
                        <b style="font-size: 14px; color: {counter_color};">{counter_text}</b>
                    </div>
                    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;">
                        <span style="color: #64748b; font-size: 12px;">مبلغ کل بدهی معوقه:</span><br>
                        <b style="font-size: 15px; color: {debt_color};">{debt_amount:,} تومان</b>
                    </div>
                    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;">
                        <span style="color: #64748b; font-size: 12px;">آخرین ماه تسویه شده:</span><br>
                        <b style="font-size: 12px; color: #334155;">{last_paid}</b>
                    </div>
                </div>

                <div>
                    <span style="font-size: 13px; font-weight: bold; color: #334155;">ریزجزئیات ماه‌های معوقه:</span>
                    {table}
                </div>
            </div>
            ''',
            color=summary["color"],
            badge=summary["label"],
            rent=rent_tomans,
            settled_until=settled_str,
            counter_color=counter_color,
            counter_text=counter_text,
            debt_color=debt_color,
            debt_amount=summary["debt_tomans"],
            last_paid=summary.get("last_paid", "-"),
            table=format_html(table_html)
        )

    financial_account_display.short_description = "ریزجزئیات حساب مالی به روز"

    # ---- Custom display methods ----
    def occupation_badge(self, obj):
        """Colored occupation badge"""
        colors = {'STUDENT': '#3498db', 'EMPLOYED': '#2ecc71', 'OTHER': '#95a5a6'}
        color = colors.get(obj.occupation, '#95a5a6')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px;">{}</span>',
            color, obj.get_occupation_display()
        )

    occupation_badge.short_description = "Occupation"

    def status_badge(self, obj):
        """Colored status badge"""
        colors = {'ACTIVE': '#27ae60', 'INACTIVE': '#f39c12', 'LEFT': '#e74c3c'}
        color = colors.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px;">{}</span>',
            color, obj.get_status_display()
        )

    status_badge.short_description = "Status"

    def dormitory_link(self, obj):
        """Clickable dormitory link"""
        url = reverse('admin:dormitory_dormitory_change', args=[obj.dormitory_id])
        return format_html('<a href="{}">{}</a>', url, obj.dormitory.name)

    dormitory_link.short_description = "Dormitory"
    dormitory_link.admin_order_field = 'dormitory__name'

    def room_number_display(self, obj):
        """Show room number with link"""
        if obj.room:
            url = reverse('admin:dormitory_room_change', args=[obj.room_id])
            return format_html('<a href="{}">{}</a>', url, obj.room.room_number)
        return "-"

    room_number_display.short_description = "Room"
    room_number_display.admin_order_field = 'room__room_number'

    def payment_summary(self, obj):
        """Show last payment info"""
        last = obj.transactions.order_by('-payment_date').first()
        if last:
            return format_html(
                'Last: {} Tomans<br><small>{}</small>',
                f"{last.amount / 10:,.0f}",
                last.payment_date.strftime('%Y/%m/%d')
            )
        return format_html('<span style="color: red;">No payments</span>')

    payment_summary.short_description = "Last Payment"

    def view_transactions_link(self, obj):
        """Link to filtered transactions list"""
        url = reverse('admin:dormitory_transaction_changelist') + f'?resident__id__exact={obj.id}'
        return format_html('<a href="{}">💰 View All Transactions</a>', url)

    view_transactions_link.short_description = "Transactions"

    def payment_history_display(self, obj):
        """Show payment history in detail view"""
        transactions = obj.transactions.all().order_by('-payment_date')[:10]
        if not transactions:
            return "No transactions recorded."

        rows = []
        for t in transactions:
            url = reverse('admin:dormitory_transaction_change', args=[t.id])
            rows.append(
                f'<tr>'
                f'<td><a href="{url}" target="_blank">{t.payment_date.strftime("%Y/%m/%d")}</a></td>'
                f'<td>{t.get_transaction_type_display()}</td>'
                f'<td>{t.amount / 10:,.0f} Tomans</td>'
                f'<td>{t.get_payment_method_display()}</td>'
                f'</tr>'
            )

        return format_html(
            '<table style="width:100%; border-collapse: collapse;">'
            '<thead><tr style="background:#f5f5f5;">'
            '<th>Date</th><th>Type</th><th>Amount</th><th>Method</th>'
            '</tr></thead><tbody>{}</tbody></table>',
            format_html(''.join(rows))
        )

    payment_history_display.short_description = "Recent Payments"

    @admin.action(description="📦 Archive selected LEFT residents and their transactions")
    def archive_left_residents(self, request, queryset):
        # فقط کسایی که LEFT هستن
        left_residents = queryset.filter(status='LEFT')

        if not left_residents.exists():
            self.message_user(request, "❌ No LEFT residents selected.", level='error')
            return

        archived_count = 0
        transactions_count = 0

        for resident in left_residents:
            # آرشیو تراکنش‌ها
            for transaction in resident.transactions.all():
                ArchivedTransaction.objects.create(
                    resident_name=resident.full_name,
                    amount=transaction.amount,
                    transaction_type=transaction.transaction_type,
                    payment_method=transaction.payment_method,
                    description=transaction.description,
                    payment_date=transaction.payment_date,
                    reference_number=transaction.reference_number,
                    applicable_rent=transaction.applicable_rent,
                    is_approved=transaction.is_approved,
                    dormitory_name=transaction.dormitory.name,
                    original_id=transaction.id,
                    original_resident_id=resident.id,
                )
                transactions_count += 1

            # آرشیو ساکن
            ArchivedResident.objects.create(
                first_name=resident.first_name,
                last_name=resident.last_name,
                national_code=resident.national_code,
                phone_number=resident.phone_number,
                parent_phone_number=resident.parent_phone_number,
                occupation=resident.occupation,
                entry_date=resident.entry_date,
                exit_date=resident.exit_date,
                monthly_payment_day=resident.monthly_payment_day,
                status=resident.status,
                original_id=resident.id,
                dormitory_name=resident.dormitory.name,
                room_number=resident.room.room_number if resident.room else None,
            )

            # حذف تراکنش‌ها و ساکن اصلی
            resident.transactions.all().delete()
            resident.delete()
            archived_count += 1

        self.message_user(
            request,
            f"✅ {archived_count} residents and {transactions_count} transactions archived and removed."
        )


# ============================================
# TRANSACTION FORM & ADMIN
# ============================================
class TransactionForm(forms.ModelForm):
    amount_tomans = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        label="مبلغ پرداختی (میلیون تومان)",
        help_text="مبلغ را به میلیون تومان وارد کنید (مثال: 2.5 برای ۲,۵۰۰,۰۰۰ تومان)"
    )

    class Meta:
        model = Transaction
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'applicable_rent' in self.fields:
            self.fields['applicable_rent'].widget = forms.HiddenInput()
        if 'created_by' in self.fields:
            Supervisor = apps.get_model('accounts', 'Supervisor')
            self.fields['created_by'].queryset = Supervisor.objects.all()
            self.fields['created_by'].required = False

        if self.instance and self.instance.pk:
            # تبدیل ریال به میلیون تومان
            self.fields['amount_tomans'].initial = self.instance.amount / 10000000

        if 'is_approved' in self.fields:
            self.fields['is_approved'].help_text = "برای پرداخت‌های نقدی و کارت‌به‌کارت نیاز به تایید است (کارت‌خوان و درگاه خودکار تایید می‌شوند)."

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method')
        transaction_type = cleaned_data.get('transaction_type')
        resident = cleaned_data.get('resident')

        # CARD (دستگاه کارتخوان) و ONLINE_GATEWAY خودکار تایید میشن
        if payment_method in ['CARD', 'ONLINE_GATEWAY']:
            cleaned_data['is_approved'] = True

        # اگه اجاره هست، قیمت اتاق رو کپی کن
        if transaction_type == 'RENT' and resident and resident.room:
            cleaned_data['applicable_rent'] = resident.room.monthly_rent

        return cleaned_data

    def save(self, commit=True):
        # تبدیل میلیون تومان به ریال
        self.instance.amount = int(self.cleaned_data['amount_tomans'] * 10000000)
        return super().save(commit)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    form = TransactionForm
    list_display = [
        'receipt_number', 'resident_link', 'period_display', 'amount_display', 'applicable_rent_display',
        'transaction_type_badge', 'payment_method', 'approval_status',
        'payment_date', 'dormitory', 'created_by'
    ]

    list_filter = [
        'transaction_type', 'payment_method', 'is_approved', 'dormitory',
        'payment_date', 'created_by'
    ]

    search_fields = ['resident__first_name', 'resident__last_name', 'reference_number', 'id', 'period_name']
    date_hierarchy = 'payment_date'
    readonly_fields = ['created_at', 'period_name', 'period_start', 'period_end', 'receipt_display']
    list_select_related = ['resident', 'dormitory', 'created_by']
    actions = ['approve_transactions', 'unapprove_transactions']

    fieldsets = (
        ('اطلاعات پرداخت', {
            'fields': ('resident', 'dormitory', 'amount_tomans', 'transaction_type', 'payment_method')
        }),
        ('دوره اجاره و سررسید', {
            'fields': ('period_name', 'period_start', 'period_end'),
            'description': 'دوره ماهانه اجاره به طور خودکار بر اساس وضعیت تسویه ساکن محاسبه می‌شود.'
        }),
        ('جزئیات رسید و پیگیری', {
            'fields': ('payment_date', 'reference_number', 'description')
        }),
        ('تایید و بازبینی', {
            'fields': ('is_approved',),
            'description': 'پرداخت‌های نقدی و کارت‌به‌کارت نیاز به تایید دارند. پس از تایید، تاریخ تسویه ساکن به طور خودکار به روز می‌شود.'
        }),
        ('ثبت‌کننده', {
            'fields': ('created_by', 'created_at'),
        }),
        ('پیش‌نمایش رسید پرداخت', {
            'fields': ('receipt_display',),
            'classes': ('wide', 'collapse')
        }),
    )

    def period_display(self, obj):
        if obj.period_name:
            return format_html('<span style="font-weight: bold; color: #1e3a8a;">{}</span>', obj.period_name)
        return "-"

    period_display.short_description = "بابت ماه / دوره"
    period_display.admin_order_field = 'period_name'

    def receipt_display(self, obj):
        if not obj.pk:
            return "Receipt will be shown after saving."

        if obj.payment_method in ['CARD', 'ONLINE_GATEWAY']:
            approval_text = '🔵 Automatic'
            approval_color = '#3498db'
        elif obj.is_approved:
            approval_text = '✅ Approved'
            approval_color = '#27ae60'
        else:
            approval_text = '⏳ Pending Approval'
            approval_color = '#e74c3c'

        period_line = format_html(
            '<p><b>دوره پرداخت:</b> {}</p>',
            obj.period_name
        ) if obj.period_name else ''

        return format_html(
            '''
            <div style="border: 2px solid #ddd; padding: 20px; max-width: 420px; font-family: monospace; 
                        background: #fafafa; border-radius: 5px; direction: rtl; text-align: right;">
                <h3 style="text-align: center; margin-bottom: 15px;">🧾 رسید پرداخت خوابگاه</h3>
                <hr>
                <p><b>شماره رسید:</b> RCP-{id:06d}</p>
                <p><b>تاریخ:</b> {date}</p>
                <p><b>نام ساکن:</b> {resident}</p>
                <p><b>خوابگاه:</b> {dormitory}</p>
                <p><b>شماره اتاق:</b> {room}</p>
                <p><b>نوع تراکنش:</b> {type}</p>
                <p><b>روش پرداخت:</b> {method}</p>
                {period_line}
                {rate_line}
                <p style="font-size: 16px; font-weight: bold;">مبلغ پرداختی: {amount:,.0f} تومان</p>
                <p><b>وضعیت تایید:</b> <span style="color: {approval_color}; font-weight: bold;">{approval_text}</span></p>
                <p><b>شماره پیگیری:</b> {ref}</p>
                <p><b>توضیحات:</b> {desc}</p>
                <hr>
                <p style="text-align: center; font-size: 11px; color: #888;">
                    ثبت توسط: {created_by} | {created_at}
                </p>
            </div>
            ''',
            id=obj.id,
            date=obj.payment_date.strftime('%Y/%m/%d - %H:%M'),
            resident=obj.resident.full_name,
            dormitory=obj.dormitory.name,
            room=obj.resident.room.room_number if obj.resident.room else 'N/A',
            type=obj.get_transaction_type_display(),
            method=obj.get_payment_method_display(),
            period_line=period_line,
            rate_line=format_html(
                '<p><b>نرخ اتاق:</b> {:,.0f} تومان</p>',
                obj.applicable_rent // 10
            ) if obj.applicable_rent else '',
            amount=obj.amount // 10,
            approval_text=approval_text,
            approval_color=approval_color,
            ref=obj.reference_number or '-',
            desc=obj.description or '-',
            created_by=obj.created_by.full_name if obj.created_by else '-',
            created_at=obj.created_at.strftime('%Y/%m/%d - %H:%M')
        )

    receipt_display.short_description = "رسید چاپی"

    def receipt_number(self, obj):
        return f"RCP-{obj.id:06d}"

    receipt_number.short_description = "شماره رسید"
    receipt_number.admin_order_field = 'id'

    def applicable_rent_display(self, obj):
        if obj.applicable_rent:
            return format_html('{:,.0f} تومان', obj.applicable_rent // 10)
        return "-"

    applicable_rent_display.short_description = "نرخ اتاق"
    applicable_rent_display.admin_order_field = 'applicable_rent'

    def resident_link(self, obj):
        url = reverse('admin:dormitory_resident_change', args=[obj.resident_id])
        return format_html('<a href="{}">{}</a>', url, obj.resident.full_name)

    resident_link.short_description = "ساکن"
    resident_link.admin_order_field = 'resident__last_name'

    def amount_display(self, obj):
        amount_m = obj.amount / 10000000
        amount_t = obj.amount // 10
        return format_html('<b>{:,.3f}</b> م.تومان<br><small style="color:#666;">({:,.0f} تومان)</small>', amount_m, amount_t)

    amount_display.short_description = "مبلغ"
    amount_display.admin_order_field = 'amount'

    def transaction_type_badge(self, obj):
        colors = {'RENT': '#3498db', 'DEPOSIT': '#e67e22', 'OTHER': '#7f8c8d'}
        color = colors.get(obj.transaction_type, '#7f8c8d')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 10px; white-space: nowrap;">{}</span>',
            color, obj.get_transaction_type_display()
        )

    transaction_type_badge.short_description = "نوع"

    def approval_status(self, obj):
        if obj.payment_method in ['CASH', 'BANK_TRANSFER']:
            if obj.is_approved:
                return format_html(
                    '<span style="background: #27ae60; color: white; padding: 2px 8px; border-radius: 10px; white-space: nowrap;">✅ تایید شده</span>'
                )
            else:
                return format_html(
                    '<span style="background: #e74c3c; color: white; padding: 2px 8px; border-radius: 10px; white-space: nowrap;">⏳ در انتظار</span>'
                )
        return format_html(
            '<span style="background: #3498db; color: white; padding: 2px 8px; border-radius: 10px; white-space: nowrap;">🔵 خودکار</span>'
        )

    approval_status.short_description = "وضعیت تایید"

    @admin.action(description="✅ تایید تراکنش‌های انتخابی و تسویه خودکار")
    def approve_transactions(self, request, queryset):
        count = 0
        for transaction in queryset.filter(payment_method__in=['CASH', 'BANK_TRANSFER'], is_approved=False):
            transaction.is_approved = True
            transaction.save()
            count += 1
        self.message_user(request, f"✅ {count} تراکنش با موفقیت تایید شد و وضعیت تسویه ساکنین به‌روزرسانی گردید.")

    @admin.action(description="❌ لغو تایید تراکنش‌های انتخابی")
    def unapprove_transactions(self, request, queryset):
        count = 0
        for transaction in queryset.filter(is_approved=True):
            transaction.is_approved = False
            transaction.save()
            count += 1
        self.message_user(request, f"❌ {count} تراکنش لغو تایید شدند.")

    def save_model(self, request, obj, form, change):
        if obj.payment_method in ['CARD', 'ONLINE_GATEWAY']:
            obj.is_approved = True
        elif obj.payment_method in ['CASH', 'BANK_TRANSFER'] and not change:
            if not form.cleaned_data.get('is_approved'):
                obj.is_approved = False

        if not obj.created_by_id:
            Supervisor = apps.get_model('accounts', 'Supervisor')
            supervisor = (
                Supervisor.objects.filter(id=request.user.id).first()
                or Supervisor.objects.filter(national_code=getattr(request.user, 'username', '')).first()
                or Supervisor.objects.first()
            )
            if supervisor:
                obj.created_by = supervisor
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "created_by":
            Supervisor = apps.get_model('accounts', 'Supervisor')
            supervisor = (
                Supervisor.objects.filter(id=request.user.id).first()
                or Supervisor.objects.filter(national_code=getattr(request.user, 'username', '')).first()
                or Supervisor.objects.first()
            )
            if supervisor:
                kwargs["initial"] = supervisor.id
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'amount' in form.base_fields:
            form.base_fields['amount'].widget = forms.HiddenInput()
        return form

