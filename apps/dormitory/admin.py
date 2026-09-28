import csv
import datetime
import html
from django import forms
from django.apps import apps
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db import models
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, path
from django.utils.html import format_html
import jdatetime
from django_jalali.db import models as jmodels
from django_jalali import forms as jforms
from apps.archive.models import ArchivedResident, ArchivedTransaction
from .models import Dormitory, Room, RoomPriceHistory, Resident, Transaction, DailyNote, get_default_dormitory


class AdminPersianDateWidget(jforms.jDateInput):
    """Modern Persian Jalali datepicker widget for Django Admin"""
    class Media:
        css = {
            'all': ('dormitory/css/admin_jalali_datepicker.css',)
        }
        js = (
            'dormitory/js/admin_jalali_datepicker.js',
        )

    def __init__(self, attrs=None, format=None):
        final_attrs = {'class': 'vjDateField form-control', 'size': '10'}
        if attrs is not None:
            final_attrs.update(attrs)
        super().__init__(attrs=final_attrs, format=format)


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


class IncompleteProfileFilter(SimpleListFilter):
    """Filter residents by completeness of profile and documents"""
    title = 'وضعیت مدارک و اطلاعات'
    parameter_name = 'profile_status'

    def lookups(self, request, model_admin):
        return (
            ('incomplete', '⚠️ دارای کسری اطلاعات و مدارک'),
            ('missing_id_image', '⚠️ فاقد عکس مدارک شناسایی'),
            ('missing_father_name', '⚠️ فاقد نام پدر'),
            ('missing_lease', '⚠️ فاقد اجاره‌نامه'),
            ('missing_national_code', '⚠️ فاقد کد ملی / پاسپورت'),
            ('missing_parent_phone', '⚠️ فاقد شماره والدین'),
            ('complete', '✅ اطلاعات و مدارک کامل'),
        )

    def queryset(self, request, queryset):
        val = self.value()
        if isinstance(val, (list, tuple)):
            val = val[0] if val else None

        if val == 'incomplete':
            return queryset.filter(
                Q(national_code__isnull=True) | Q(national_code='') |
                Q(father_name__isnull=True) | Q(father_name='') |
                Q(parent_phone_number__isnull=True) | Q(parent_phone_number='') |
                Q(has_lease=False) |
                ((Q(id_card_image__isnull=True) | Q(id_card_image='')) &
                 (Q(id_card_image_2__isnull=True) | Q(id_card_image_2='')) &
                 (Q(id_card_image_3__isnull=True) | Q(id_card_image_3='')))
            )
        if val == 'missing_id_image':
            return queryset.filter(
                (Q(id_card_image__isnull=True) | Q(id_card_image='')) &
                (Q(id_card_image_2__isnull=True) | Q(id_card_image_2='')) &
                (Q(id_card_image_3__isnull=True) | Q(id_card_image_3=''))
            )
        if val == 'missing_father_name':
            return queryset.filter(Q(father_name__isnull=True) | Q(father_name=''))
        if val == 'missing_lease':
            return queryset.filter(has_lease=False)
        if val == 'missing_national_code':
            return queryset.filter(Q(national_code__isnull=True) | Q(national_code=''))
        if val == 'missing_parent_phone':
            return queryset.filter(Q(parent_phone_number__isnull=True) | Q(parent_phone_number=''))
        if val == 'complete':
            return queryset.filter(
                national_code__isnull=False,
                father_name__isnull=False,
                parent_phone_number__isnull=False,
                has_lease=True
            ).exclude(national_code='').exclude(father_name='').exclude(parent_phone_number='').filter(
                (Q(id_card_image__isnull=False) & ~Q(id_card_image='')) |
                (Q(id_card_image_2__isnull=False) & ~Q(id_card_image_2='')) |
                (Q(id_card_image_3__isnull=False) & ~Q(id_card_image_3=''))
            )
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
    """Custom form to convert Tomans to Rials and support effective date for price changes"""
    monthly_rent_tomans = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        label="اجاره ماهانه (میلیون تومان)",
        help_text="مبلغ را به میلیون تومان وارد کنید (مثال: 3.8 برای 3,800,000 تومان، 3.5 برای 3.5 میلیون تومان)"
    )
    effective_date = jforms.jDateField(
        widget=AdminPersianDateWidget,
        required=False,
        label="تاریخ شروع اعمال نرخ",
        help_text="در صورت تغییر مبلغ، این نرخ از تاریخ مشخص‌شده محاسبه می‌شود و ماه‌های قبل با نرخ قبلی حفظ می‌شوند."
    )
    price_change_note = forms.CharField(
        max_length=255,
        required=False,
        label="علت / شرح تغییر نرخ",
        help_text="اختیاری (مثال: افزایش قیمت پاییز ۱۴۰۵ یا مصوبه جدید)"
    )

    class Meta:
        model = Room
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and 'dormitory' in self.fields:
            if not self.initial.get('dormitory'):
                default_dorm_id = get_default_dormitory()
                if default_dorm_id:
                    self.fields['dormitory'].initial = default_dorm_id

        if self.instance and self.instance.pk:
            # تبدیل ریال به میلیون تومان
            self.fields['monthly_rent_tomans'].initial = self.instance.monthly_rent / 10000000
            latest = self.instance.latest_price_history
            if latest:
                self.fields['effective_date'].initial = latest.effective_date
                self.fields['price_change_note'].initial = latest.note
            else:
                self.fields['effective_date'].initial = jdatetime.date.today()
        else:
            self.fields['effective_date'].initial = jdatetime.date.today()

    def save(self, commit=True):
        new_rent_rials = int(self.cleaned_data['monthly_rent_tomans'] * 10000000)
        eff_date = self.cleaned_data.get('effective_date') or jdatetime.date.today()
        note = self.cleaned_data.get('price_change_note') or ''

        self.instance._price_change_effective_date = eff_date
        self.instance._price_change_note = note

        if self.instance.pk:
            old_room = Room.objects.filter(pk=self.instance.pk).first()
            if old_room and old_room.monthly_rent != new_rent_rials:
                self.instance.set_rent(
                    new_rent_rials=new_rent_rials,
                    effective_date=eff_date,
                    note=note
                )
            else:
                self.instance.monthly_rent = new_rent_rials
        else:
            self.instance.monthly_rent = new_rent_rials

        return super().save(commit)


class RoomPriceHistoryInline(admin.TabularInline):
    model = RoomPriceHistory
    extra = 0
    fields = ['monthly_rent_tomans_display', 'effective_date', 'note', 'created_by', 'created_at']
    readonly_fields = ['monthly_rent_tomans_display', 'created_at']
    ordering = ['-effective_date', '-id']
    formfield_overrides = {
        jmodels.jDateField: {'widget': AdminPersianDateWidget},
    }

    def monthly_rent_tomans_display(self, obj):
        if obj.monthly_rent:
            t = f"{obj.monthly_rent // 10:,.0f}"
            m = f"{obj.monthly_rent / 10000000:,.2f}".rstrip('0').rstrip('.')
            return format_html('<b>{} تومان</b> <small style="color:#666;">({} م.تومان)</small>', t, m)
        return "-"
    monthly_rent_tomans_display.short_description = "مبلغ اجاره (تومان)"


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    form = RoomForm
    inlines = [RoomPriceHistoryInline]
    list_display = [
        '__str__', 'dormitory', 'room_number', 'capacity',
        'current_occupants', 'available_capacity', 'vacancy_status', 'monthly_rent_display', 'price_effective_date_display'
    ]
    actions = ['bulk_change_price']
    list_filter = ['dormitory', 'capacity', VacancyFilter]
    search_fields = ['room_number', 'dormitory__name']
    list_select_related = ['dormitory']

    def price_effective_date_display(self, obj):
        latest = obj.latest_price_history
        if latest:
            return format_html(
                '<span style="font-size:12px; color:#2c3e50; font-weight:bold;">{}</span><br><small style="color:#7f8c8d;">{}</small>',
                latest.effective_date.strftime('%Y/%m/%d'),
                latest.note or 'فعال'
            )
        return "-"
    price_effective_date_display.short_description = "تاریخ اعمال نرخ"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "dormitory":
            default_dorm_id = get_default_dormitory()
            if default_dorm_id:
                kwargs["initial"] = default_dorm_id
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if 'dormitory' not in initial:
            default_dorm_id = get_default_dormitory()
            if default_dorm_id:
                initial['dormitory'] = default_dorm_id
        return initial

    def monthly_rent_display(self, obj):
        """Show rent in Million Tomans and formatted Tomans"""
        amount_m = f"{obj.monthly_rent / 10000000:,.1f}"
        amount_t = f"{obj.monthly_rent // 10:,.0f}"
        return format_html('<b>{}</b> م.تومان <small style="color:#666;">({} تومان)</small>', amount_m, amount_t)

    monthly_rent_display.short_description = "اجاره ماهانه فعلی"
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

    @admin.action(description="📈 افزایش / تغییر نرخ دسته‌جمعی اتاق‌های انتخاب‌شده")
    def bulk_change_price(self, request, queryset):
        from apps.dormitory.jalali_utils import parse_jalali_date
        if 'apply' in request.POST:
            try:
                new_rent_m = float(request.POST.get('new_rent_million_tomans', 0))
                new_rent_rials = int(new_rent_m * 10_000_000)
                eff_date_str = request.POST.get('effective_date')
                eff_date = parse_jalali_date(eff_date_str) or jdatetime.date.today()
                note = request.POST.get('note', '').strip() or f"افزایش قیمت دسته‌جمعی از {eff_date}"

                Supervisor = apps.get_model('accounts', 'Supervisor')
                supervisor = (
                    Supervisor.objects.filter(id=request.user.id).first()
                    or Supervisor.objects.filter(national_code=getattr(request.user, 'username', '')).first()
                    or Supervisor.objects.first()
                )

                count = 0
                for room in queryset:
                    room.set_rent(
                        new_rent_rials=new_rent_rials,
                        effective_date=eff_date,
                        note=note,
                        supervisor=supervisor
                    )
                    count += 1

                self.message_user(
                    request,
                    f"✅ نرخ اجاره {count} اتاق با موفقیت به {new_rent_m:,.2f} میلیون تومان ({new_rent_rials // 10:,} تومان) از تاریخ {eff_date} تغییر یافت. سوابق محاسباتی گذشته بدون تغییر محفوظ ماندند."
                )
                return None
            except Exception as e:
                self.message_user(request, f"❌ خطا در ثبت نرخ جدید: {e}", level='error')

        context = {
            'title': 'افزایش و تغییر نرخ دسته‌جمعی اتاق‌ها',
            'rooms': queryset,
            'today': jdatetime.date.today().strftime('%Y/%m/%d'),
            'queryset': queryset,
            'opts': self.model._meta,
        }
        return render(request, 'admin/dormitory/room/bulk_change_price.html', context)



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
        amount = f"{obj.amount // 10:,.0f}"
        return format_html('<b>{}</b> تومان', amount)

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
        'full_name', 'national_code_display', 'document_status_badge', 'id_documents_badge', 'deposit_status_badge', 'occupation_badge', 'dormitory_link',
        'room_number_display', 'status_badge',
        'entry_date', 'settled_until', 'debt_status', 'payment_summary',
        'copy_profile_action',
        'view_transactions_link',
    ]
    actions = ['archive_left_residents', 'export_selected_to_clipboard', 'export_selected_to_csv', 'sync_settled_until_from_transactions', 'export_debtors_to_excel_action']

    fieldsets = (
        ('اطلاعات فردی', {
            'fields': (
                ('first_name', 'last_name', 'father_name'),
                ('is_foreign', 'national_code'),
                'occupation',
                ('phone_number', 'parent_phone_number'),
            )
        }),
        ('تصاویر مدارک هویتی (حداکثر ۳ تصویر با دوربین/فایل - فشرده‌سازی خودکار تا زیر ۱ مگابایت)', {
            'fields': (
                ('id_card_image', 'id_card_image_2', 'id_card_image_3'),
                'id_cards_preview_display',
            ),
            'description': 'با دوربین گوشی یا انتخاب فایل، تا ۳ تصویر از کارت ملی (رو و پشت)، پاسپورت یا شناسنامه را آپلود کنید. حجم فایل‌ها به صورت خودکار به زیر ۱ مگابایت فشرده می‌شود.',
        }),
        ('خروجی و کپی مشخصات', {
            'fields': ('copy_profile_panel',),
            'classes': ('collapse',)
        }),
        ('تخصیص اتاق و روز پرداخت', {
            'fields': ('dormitory', 'room', 'monthly_payment_day')
        }),
        ('وضعیت ودیعه و اجاره‌نامه', {
            'fields': (
                ('has_deposit', 'has_lease'),
            )
        }),
        ('وضعیت اقامت و تاریخ‌ها', {
            'fields': ('entry_date', 'exit_date', 'settled_until', 'status')
        }),
        ('وضعیت حساب و ریزجزئیات مالی به روز', {
            'fields': ('financial_account_display',),
            'classes': ('wide',)
        }),
        ('امور اداری', {
            'fields': ('registered_by',)
        }),
        ('تاریخچه پرداخت‌های ثبت‌شده', {
            'fields': ('payment_history_display',),
            'classes': ('wide',)
        }),
    )
    list_filter = [
        'has_deposit', 'has_lease', 'is_foreign', IncompleteProfileFilter, 'status', 'occupation', 'dormitory', 'entry_date', 'monthly_payment_day', 'settled_until'
    ]
    search_fields = ['first_name', 'last_name', 'father_name', 'national_code', 'phone_number', 'room__room_number']
    readonly_fields = ['created_at', 'financial_account_display', 'payment_history_display', 'copy_profile_panel', 'id_cards_preview_display']
    list_select_related = ['dormitory', 'room']
    inlines = [TransactionInline]

    formfield_overrides = {
        jmodels.jDateField: {'widget': AdminPersianDateWidget},
    }

    class Media:
        css = {
            'all': ('dormitory/css/admin_jalali_datepicker.css',)
        }
        js = (
            'dormitory/js/resident_admin_copy.js',
            'dormitory/js/admin_resident_foreign.js',
            'dormitory/js/admin_jalali_datepicker.js',
        )

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if 'entry_date' not in initial:
            initial['entry_date'] = jdatetime.date.today() - datetime.timedelta(days=1)
        if 'dormitory' not in initial:
            default_dorm_id = get_default_dormitory()
            if default_dorm_id:
                initial['dormitory'] = default_dorm_id
        return initial

    def national_code_display(self, obj):
        if obj.national_code:
            if obj.is_foreign:
                return format_html('<span style="white-space:nowrap; display:inline-flex; align-items:center; gap:4px;">{} <span style="background:#0284c7; color:#fff; font-size:10px; padding:2px 6px; border-radius:4px;">🌐 اتباع</span></span>', obj.national_code)
            return format_html('<span style="white-space:nowrap;">{}</span>', obj.national_code)
        return format_html('<span style="white-space:nowrap; display:inline-flex; align-items:center; gap:3px; color:#e67e22; font-style:italic;">⚠️ ثبت‌نشده</span>')
    national_code_display.short_description = "کد ملی / پاسپورت"
    national_code_display.admin_order_field = 'national_code'

    def id_documents_badge(self, obj):
        count = obj.uploaded_id_images_count
        if count == 0:
            return format_html(
                '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; justify-content:center; gap:4px; background:#e11d48; color:white; padding:3px 9px; border-radius:6px; font-size:11px; font-weight:bold;" title="فاقد عکس مدارک هویتی (کارت ملی، شناسنامه یا پاسپورت)">'
                '🪪 بدون عکس'
                '</span>'
            )
        return format_html(
            '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; justify-content:center; gap:4px; background:#0284c7; color:white; padding:3px 9px; border-radius:6px; font-size:11px; font-weight:bold;" title="{} تصویر مدرک بارگذاری شده">'
            '🪪 {} مدرک'
            '</span>',
            count, count
        )
    id_documents_badge.short_description = "عکس مدارک"
    id_documents_badge.admin_order_field = 'id_card_image'

    def id_cards_preview_display(self, obj):
        if not obj or not obj.id_cards_images_list:
            return format_html('<span style="color:#e67e22; font-style:italic;">⚠️ هنوز هیچ تصویری از مدارک شناسایی بارگذاری نشده است.</span>')
        cards = []
        labels = ["تصویر اول (روی کارت / پاسپورت)", "تصویر دوم (پشت کارت)", "تصویر سوم (شناسنامه / سایر)"]
        for idx, img_field in enumerate(obj.id_cards_images_list):
            lbl = labels[idx] if idx < len(labels) else f"تصویر {idx+1}"
            try:
                size_str = f"{img_field.size / 1024:.1f} KB" if img_field.size < 1024 * 1024 else f"{img_field.size / (1024 * 1024):.2f} MB"
            except Exception:
                size_str = "کمتر از ۱ مگابایت"
            cards.append(format_html(
                '<div style="display:inline-block; margin:6px; text-align:center; border:1px solid rgba(255,255,255,0.15); border-radius:12px; padding:8px; background:rgba(0,0,0,0.2);">'
                '<div style="font-size:11px; margin-bottom:4px; font-weight:bold; color:#38bdf8;">{}</div>'
                '<a href="{}" target="_blank" title="مشاهده اندازه کامل">'
                '<img src="{}" style="max-height:130px; max-width:180px; object-fit:cover; border-radius:8px; border:1px solid rgba(255,255,255,0.1); display:block; margin:0 auto;" />'
                '</a>'
                '<div style="font-size:10px; color:#aaa; margin-top:4px;">حجم: {}</div>'
                '</div>',
                lbl, img_field.url, img_field.url, size_str
            ))
        return format_html('<div style="display:flex; flex-wrap:wrap; gap:8px;">{}</div>', format_html(''.join(cards)))
    id_cards_preview_display.short_description = "پیش‌نمایش مدارک بارگذاری‌شده"

    def deposit_status_badge(self, obj):
        if obj.has_deposit:
            return format_html(
                '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; justify-content:center; gap:4px; color:#16a34a; font-weight:bold; font-size:11px;" title="ودیعه ثبت شده است">'
                '✅ دارد'
                '</span>'
            )
        return format_html(
            '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; justify-content:center; gap:4px; background:#e11d48; color:white; padding:3px 9px; border-radius:6px; font-weight:bold; font-size:11px;" title="ودیعه ثبت یا دریافت نشده است">'
            '❌ فاقد ودیعه'
            '</span>'
        )
    deposit_status_badge.short_description = "ودیعه"
    deposit_status_badge.admin_order_field = 'has_deposit'

    def document_status_badge(self, obj):
        st = obj.profile_completion_status
        if st == "COMPLETE":
            return format_html(
                '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; gap:4px; color:#16a34a; font-size:11px; font-weight:bold;" title="تمامی اطلاعات و مدارک کامل است">'
                '✅ مدارک کامل'
                '</span>'
            )
        elif st == "MISSING_ALL":
            return format_html(
                '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; gap:4px; background:#b91c1c; color:white; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:bold;" title="فاقد تمام مدارک: کد ملی، نام پدر، تلفن والدین، اجاره‌نامه، عکس مدرک">'
                '⚠️ فاقد تمام مدارک (۵ مورد)'
                '</span>'
            )
        elif st == "MISSING_BOTH":
            lbl = "فاقد پاسپورت و والدین" if obj.is_foreign else "فاقد کدملی و والدین"
            return format_html(
                '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; gap:4px; background:#e11d48; color:white; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:bold;" title="{}">'
                '⚠️ {}'
                '</span>',
                lbl, lbl
            )
        elif st == "MISSING_LEASE":
            return format_html(
                '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; gap:4px; background:#e11d48; color:white; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:bold;" title="فاقد قرارداد اجاره‌نامه معتبر">'
                '⚠️ فاقد اجاره‌نامه'
                '</span>'
            )
        elif st == "MISSING_NATIONAL_CODE":
            return format_html(
                '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; gap:4px; background:#d97706; color:white; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:bold;" title="کد ملی ثبت نشده است">'
                '⚠️ فاقد کد ملی'
                '</span>'
            )
        elif st == "MISSING_PASSPORT":
            return format_html(
                '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; gap:4px; background:#d97706; color:white; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:bold;" title="شماره پاسپورت ثبت نشده است">'
                '⚠️ فاقد پاسپورت'
                '</span>'
            )
        elif st == "MISSING_PARENT_PHONE":
            return format_html(
                '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; gap:4px; background:#d97706; color:white; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:bold;" title="شماره تماس والدین یا بستگان ثبت نشده است">'
                '⚠️ فاقد تلفن والدین'
                '</span>'
            )
        elif st == "MISSING_FATHER_NAME":
            return format_html(
                '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; gap:4px; background:#d97706; color:white; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:bold;" title="نام پدر ثبت نشده است">'
                '⚠️ فاقد نام پدر'
                '</span>'
            )
        elif st == "MISSING_ID_IMAGE":
            return format_html(
                '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; gap:4px; background:#d97706; color:white; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:bold;" title="تصویر مدارک هویتی بارگذاری نشده است">'
                '⚠️ فاقد عکس مدارک'
                '</span>'
            )

        missing_fields = obj.missing_profile_fields
        short_names_map = {
            "شماره پاسپورت یا کد فراگیر": "پاسپورت",
            "کد ملی": "کد ملی",
            "نام پدر": "نام پدر",
            "شماره تماس والدین": "تلفن والدین",
            "اجاره‌نامه": "اجاره‌نامه",
            "عکس مدرک شناسایی": "عکس مدرک",
        }
        short_items = "، ".join([short_names_map.get(f, f) for f in missing_fields])
        full_details = "کسری‌ها: " + "، ".join(missing_fields)

        return format_html(
            '<div style="white-space:nowrap; direction:rtl; text-align:right; display:inline-flex; flex-direction:column; align-items:flex-start; gap:2px;" title="{}">'
            '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; display:inline-flex; align-items:center; gap:4px; background:#e11d48; color:white; padding:2px 7px; border-radius:5px; font-size:11px; font-weight:bold;">⚠️ {} مورد کسری مدارک</span>'
            '<span style="white-space:nowrap; direction:rtl; unicode-bidi:isolate; font-size:10px; color:#f87171; font-weight:bold; margin-top:1px;">{}</span>'
            '</div>',
            full_details,
            len(missing_fields),
            short_items
        )
    document_status_badge.short_description = "وضعیت مدارک"

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in ('id_card_image', 'id_card_image_2', 'id_card_image_3'):
            kwargs['widget'] = forms.FileInput(attrs={'accept': 'image/*', 'capture': 'environment'})
        elif db_field.name == 'national_code':
            kwargs['widget'] = forms.TextInput(attrs={
                'maxlength': '10',
                'inputmode': 'numeric',
                'autocomplete': 'off',
            })
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        res = self.get_object(request, object_id)
        if res:
            from django.contrib import messages
            if not res.has_id_card_image:
                messages.warning(
                    request,
                    f"⚠️ هشدار کسری مدارک: تصویر مدارک شناسایی برای «{res.full_name}» بارگذاری نشده است! لطفاً تصویر کارت ملی یا پاسپورت را با دوربین یا فایل آپلود نمایید."
                )
            if not res.father_name:
                messages.warning(
                    request,
                    f"⚠️ هشدار کسری مدارک: نام پدر برای «{res.full_name}» ثبت نشده است! لطفاً جهت تکمیل پرونده نام پدر را وارد نمایید."
                )
            if not res.has_lease:
                messages.warning(
                    request,
                    f"⚠️ هشدار کسری مدارک: «{res.full_name}» فاقد اجاره‌نامه معتبر می‌باشد! لطفاً پس از دریافت، تیک اجاره‌نامه را ثبت نمایید."
                )
            if not res.has_deposit:
                messages.info(
                    request,
                    f"ℹ️ توجه: برای «{res.full_name}» هنوز ودیعه ثبت یا علامت‌گذاری نشده است (فاقد ودیعه)."
                )
        return super().change_view(request, object_id, form_url, extra_context=extra_context)


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
        elif db_field.name == "dormitory":
            default_dorm_id = get_default_dormitory()
            if default_dorm_id:
                kwargs["initial"] = default_dorm_id
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def debt_status(self, obj):
        """Show detailed daily debt status with overdue days and unpaid months"""
        summary = obj.financial_status_summary
        status = summary["status"]

        if status == "SETTLED":
            days = summary["days_until_due"]
            due_date = obj.settled_until.strftime('%Y/%m/%d') if obj.settled_until else ''
            return format_html(
                '<div style="white-space: nowrap; direction: rtl; text-align: right;">'
                '<span style="direction: rtl; unicode-bidi: isolate; display: inline-flex; align-items: center; gap: 4px; background: #27ae60; color: white; padding: 2px 8px; border-radius: 8px; font-weight: bold; font-size: 11px;">🟢 تسویه به روز</span><br>'
                '<small style="direction: rtl; unicode-bidi: isolate; display: block; color: #27ae60; font-size: 11px; margin-top: 2px;">⏳ {} روز تا سررسید ({})</small>'
                '</div>',
                days, due_date
            )
        elif status == "DUE_TODAY":
            debt_t = f"{summary['debt_tomans']:,}"
            unpaid = summary["unpaid_months"]
            return format_html(
                '<div style="white-space: nowrap; direction: rtl; text-align: right;">'
                '<span style="direction: rtl; unicode-bidi: isolate; display: inline-flex; align-items: center; gap: 4px; background: #f39c12; color: white; padding: 2px 8px; border-radius: 8px; font-weight: bold; font-size: 11px;">🟡 سررسید امروز</span><br>'
                '<small style="direction: rtl; unicode-bidi: isolate; display: block; color: #d35400; font-size: 11px; margin-top: 2px;">{} ({} ت)</small>'
                '</div>',
                unpaid, debt_t
            )
        elif status == "OVERDUE":
            overdue = summary["overdue_days"]
            debt_t = f"{summary['debt_tomans']:,}"
            unpaid = summary["unpaid_months"]
            if overdue <= 7:
                return format_html(
                    '<div style="white-space: nowrap; direction: rtl; text-align: right;">'
                    '<span style="direction: rtl; unicode-bidi: isolate; display: inline-flex; align-items: center; gap: 4px; background: #f39c12; color: white; padding: 2px 8px; border-radius: 8px; font-weight: bold; font-size: 11px;">🟡 {} روز تاخیر (هشدار)</span><br>'
                    '<small style="direction: rtl; unicode-bidi: isolate; display: block; color: #d35400; font-weight: bold; font-size: 11px; margin-top: 2px;">{}</small>'
                    '<small style="direction: rtl; unicode-bidi: isolate; display: block; color: #888; font-size: 11px; margin-top: 1px;">بدهی: {} تومان</small>'
                    '</div>',
                    overdue, unpaid, debt_t
                )
            else:
                return format_html(
                    '<div style="white-space: nowrap; direction: rtl; text-align: right;">'
                    '<span style="direction: rtl; unicode-bidi: isolate; display: inline-flex; align-items: center; gap: 4px; background: #e74c3c; color: white; padding: 2px 8px; border-radius: 8px; font-weight: bold; font-size: 11px;">🔴 {} روز تاخیر (بدهکار)</span><br>'
                    '<small style="direction: rtl; unicode-bidi: isolate; display: block; color: #c0392b; font-weight: bold; font-size: 11px; margin-top: 2px;">{}</small>'
                    '<small style="direction: rtl; unicode-bidi: isolate; display: block; color: #888; font-size: 11px; margin-top: 1px;">بدهی: {} تومان</small>'
                    '</div>',
                    overdue, unpaid, debt_t
                )
        elif status == "NO_ROOM":
            return format_html('<span style="color: #7f8c8d; font-size: 11px; direction: rtl; unicode-bidi: isolate;">⚪ بدون اتاق</span>')
        else:
            return format_html('<span style="color: #7f8c8d; font-size: 11px; direction: rtl; unicode-bidi: isolate;">⚪ {}</span>', obj.get_status_display())

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
                f"<td style='padding: 8px 12px; font-weight: bold; color: {'#b45309' if p['overdue_days'] <= 7 else '#991b1b'};'>{p['name']}</td>"
                f"<td style='padding: 8px 12px; color: #666;'>{p['start_date']} تا {p['end_date']}</td>"
                f"<td style='padding: 8px 12px; color: {'#d97706' if p['overdue_days'] <= 7 else '#b91c1c'}; font-weight: bold;'>{'🟡' if p['overdue_days'] <= 7 else '🔴'} {p['overdue_days']} روز تاخیر {'(مهلت تا ۱ هفته)' if p['overdue_days'] <= 7 else '(بیش از ۱ هفته)'}</td>"
                f"<td style='padding: 8px 12px; font-weight: bold;'>{p['amount_tomans']:,} تومان</td>"
                f"</tr>"
                for p in unpaid
            ])
            table_html = f"""
            <table style='width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; text-align: right; background: white; border-radius: 6px; overflow: hidden; border: 1px solid #fee2e2;'>
                <thead>
                    <tr style='background: #fecaca; color: #991b1b;'>
                        <th style='padding: 8px 12px;'>دوره / ماه بدهکار</th>
                        <th style='padding: 8px 12px;'>بازه دوره اجاره</th>
                        <th style='padding: 8px 12px;'>دیرکرد</th>
                        <th style='padding: 8px 12px;'>مبلغ معوقه</th>
                    </tr>
                </thead>
                <tbody>{unpaid_rows}</tbody>
            </table>
            """
        else:
            table_html = "<div style='color: #27ae60; font-weight: bold; margin-top: 8px; font-size: 13px;'>✅ تمامی ماه‌های اقامت تا این لحظه به طور کامل تسویه هستند.</div>"

        if summary["overdue_days"] > 7:
            counter_color = "#c0392b"
            counter_text = f"🔴 {summary['overdue_days']} روز تاخیر (بیش از یک هفته)"
            debt_color = "#c0392b"
        elif summary["overdue_days"] > 0:
            counter_color = "#d97706"
            counter_text = f"🟡 {summary['overdue_days']} روز تاخیر (مهلت تا یک هفته)"
            debt_color = "#d97706"
        elif summary["status"] == "DUE_TODAY":
            counter_color = "#d97706"
            counter_text = "🟡 سررسید امروز"
            debt_color = "#d97706"
        else:
            counter_color = "#27ae60"
            counter_text = f"🟢 {summary['days_until_due']} روز مانده تا موعد"
            debt_color = "#27ae60"

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
                    <span style="font-size: 13px; font-weight: bold; color: #334155;">ریزجزئیات دوره‌ها و مبالغ معوقه (روزشمار):</span>
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
            '<span style="white-space:nowrap; display:inline-block; background:{}; color:white; padding:2px 8px; border-radius:10px; font-size:12px;">{}</span>',
            color, obj.get_occupation_display()
        )

    occupation_badge.short_description = "Occupation"

    def status_badge(self, obj):
        """Colored status badge"""
        colors = {'ACTIVE': '#27ae60', 'INACTIVE': '#f39c12', 'LEFT': '#e74c3c'}
        color = colors.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="white-space:nowrap; display:inline-block; background:{}; color:white; padding:2px 8px; border-radius:10px; font-size:12px;">{}</span>',
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

    @admin.action(description="🔄 همگام‌سازی تاریخ تسویه ساکنان بر اساس تراکنش‌ها")
    def sync_settled_until_from_transactions(self, request, queryset):
        count = 0
        for resident in queryset:
            resident.recalculate_settled_until()
            count += 1
        self.message_user(request, f"🔄 تاریخ تسویه {count} ساکن بر اساس تراکنش‌های تاییدشده همگام‌سازی شد.")

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
                father_name=resident.father_name,
                is_foreign=resident.is_foreign,
                national_code=resident.national_code,
                phone_number=resident.phone_number,
                parent_phone_number=resident.parent_phone_number,
                has_deposit=resident.has_deposit,
                has_lease=resident.has_lease,
                id_card_image=resident.id_card_image,
                id_card_image_2=resident.id_card_image_2,
                id_card_image_3=resident.id_card_image_3,
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

    def copy_profile_action(self, obj):
        text = obj.get_export_text()
        escaped_text = html.escape(text, quote=True)
        return format_html(
            '<button type="button" class="btn btn-xs btn-outline-info" '
            'data-resident-text="{}" onclick="copyResidentClipboard(this)" '
            'title="کپی مشخصات کامل این ساکن" style="white-space:nowrap; font-weight:600; font-size:11px;">'
            '📋 کپی مشخصات</button>',
            escaped_text
        )
    copy_profile_action.short_description = "خروجی / کپی"

    def copy_profile_panel(self, obj):
        if not obj or not obj.pk:
            return "-"
        text = obj.get_export_text()
        escaped_text = html.escape(text, quote=True)
        return format_html(
            '<div style="max-width:650px;">'
            '<button type="button" class="btn btn-sm btn-primary mb-2" '
            'data-resident-text="{}" onclick="copyResidentClipboard(this)" style="font-weight:600;">'
            '📋 کپی مشخصات این ساکن در کلیپ‌بورد</button>'
            '<pre style="direction:rtl; text-align:right; background:#f8fafc; border:1px solid #cbd5e1; padding:12px; border-radius:8px; font-size:12px; line-height:1.7; white-space:pre-wrap;">{}</pre>'
            '</div>',
            escaped_text, text
        )
    copy_profile_panel.short_description = "خروجی و کپی مشخصات فردی"

    @admin.action(description="📋 کپی مشخصات افراد انتخاب‌شده (متن کامل)")
    def export_selected_to_clipboard(self, request, queryset):
        count = queryset.count()
        if count == 0:
            self.message_user(request, "هیچ ساکنی انتخاب نشده است.", level='warning')
            return None

        delimiter = "\n" + ("═" * 45) + "\n\n"
        profiles = []
        ordered_residents = queryset.select_related('dormitory', 'room').order_by(
            'dormitory__name', 'room__room_number', 'last_name'
        )
        for i, resident in enumerate(ordered_residents, 1):
            profiles.append(f"ردیف {i}:\n" + resident.get_export_text())

        combined_text = f"📋 فهرست مشخصات ساکنین ({count} نفر)\n" + ("═" * 45) + "\n\n" + delimiter.join(profiles)
        selected_ids = list(queryset.values_list('id', flat=True))

        context = {
            **self.admin_site.each_context(request),
            'title': 'خروجی مشخصات ساکنین انتخاب‌شده',
            'count': count,
            'combined_text': combined_text,
            'selected_ids': selected_ids,
        }
        return render(request, 'admin/dormitory/resident/export_clipboard.html', context)

    @admin.action(description="📊 خروجی فایل اکسل (CSV) افراد انتخاب‌شده")
    def export_selected_to_csv(self, request, queryset):
        count = queryset.count()
        if count == 0:
            self.message_user(request, "هیچ ساکنی انتخاب نشده است.", level='warning')
            return None

        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = f'attachment; filename="residents_export_{count}_persons.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'ردیف',
            'نام و نام خانوادگی',
            'نام',
            'نام خانوادگی',
            'کد ملی',
            'شماره تماس ساکن',
            'شماره تماس والدین',
            'شغل',
            'خوابگاه',
            'شماره اتاق',
            'اجاره ماهانه (تومان)',
            'تاریخ ورود',
            'موعد پرداخت',
            'وضعیت اقامت',
            'تسویه تا تاریخ',
            'اجاره‌نامه',
            'ودیعه'
        ])

        ordered_residents = queryset.select_related('dormitory', 'room').order_by(
            'dormitory__name', 'room__room_number', 'last_name'
        )
        for i, r in enumerate(ordered_residents, 1):
            d = r.get_export_dict()
            writer.writerow([
                i,
                d['full_name'],
                d['first_name'],
                d['last_name'],
                d['national_code'],
                d['phone_number'],
                d['parent_phone_number'],
                d['occupation'],
                d['dormitory'],
                d['room_number'],
                d['monthly_rent_tomans'],
                d['entry_date'],
                d['monthly_payment_day'],
                d['status'],
                d['settled_until'],
                d['lease_status'],
                d['deposit_status']
            ])

        return response

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'export-debtors-excel/',
                self.admin_site.admin_view(self.export_debtors_excel_view),
                name='dormitory_resident_export_debtors_excel',
            ),
        ]
        return custom_urls + urls

    def export_debtors_excel_view(self, request):
        from apps.dormitory.services.excel_export import export_debtors_to_excel_response
        return export_debtors_to_excel_response()

    @admin.action(description="📊 خروجی فایل اکسل بدهکاران (RTL)")
    def export_debtors_to_excel_action(self, request, queryset):
        from apps.dormitory.services.excel_export import export_debtors_to_excel_response
        return export_debtors_to_excel_response(queryset=queryset)


# ============================================
# TRANSACTION FORM & ADMIN
# ============================================
class TransactionForm(forms.ModelForm):
    amount_tomans = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        label="مبلغ پرداختی (میلیون تومان)",
        help_text="مبلغ واریزی ساکن را به میلیون تومان وارد کنید (مثال: 2.5 برای ۲,۵۰۰,۰۰۰ تومان)"
    )
    discount_tomans = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        required=False,
        initial=0,
        label="کسورات / تخفیف استثنایی (میلیون تومان)",
        help_text="در صورت سم‌پاشی، تخلیه موقت یا توافق خاص، مبلغ کسر شده را وارد کنید (مثال: 0.5 برای ۵۰۰,۰۰۰ تومان)"
    )
    discount_reason = forms.CharField(
        max_length=255,
        required=False,
        label="علت و جزئیات کسورات",
        widget=forms.TextInput(attrs={'placeholder': 'مثال: سم‌پاشی خوابگاه و ۵ روز تخلیه موقت، تعمیرات و...'}),
        help_text="در صورت ثبت کسورات استثنایی، ذکر علت الزامی است."
    )

    class Meta:
        model = Transaction
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and 'dormitory' in self.fields:
            if not self.initial.get('dormitory'):
                default_dorm_id = get_default_dormitory()
                if default_dorm_id:
                    self.fields['dormitory'].initial = default_dorm_id

        if not self.instance.pk and 'payment_date' in self.fields:
            if not self.initial.get('payment_date'):
                self.fields['payment_date'].initial = jdatetime.datetime.now()

        if 'amount' in self.fields:
            self.fields['amount'].required = False
            self.fields['amount'].widget = forms.HiddenInput()
        if 'discount_amount' in self.fields:
            self.fields['discount_amount'].required = False
            self.fields['discount_amount'].widget = forms.HiddenInput()
        if 'applicable_rent' in self.fields:
            self.fields['applicable_rent'].widget = forms.HiddenInput()
        if 'created_by' in self.fields:
            Supervisor = apps.get_model('accounts', 'Supervisor')
            self.fields['created_by'].queryset = Supervisor.objects.all()
            self.fields['created_by'].required = False

        if self.instance and self.instance.pk:
            # تبدیل ریال به میلیون تومان
            self.fields['amount_tomans'].initial = self.instance.amount / 10000000
            if self.instance.discount_amount:
                self.fields['discount_tomans'].initial = self.instance.discount_amount / 10000000
            if self.instance.discount_reason:
                self.fields['discount_reason'].initial = self.instance.discount_reason

        if 'is_approved' in self.fields:
            if not self.instance.pk:
                self.fields['is_approved'].initial = True
            self.fields['is_approved'].help_text = "تمام تراکنش‌ها (نقدی، کارت‌به‌کارت و...) بلافاصله پس از ثبت در تسویه و بدهی ساکن اعمال می‌شوند."

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method')
        transaction_type = cleaned_data.get('transaction_type')
        resident = cleaned_data.get('resident')
        discount_tomans = cleaned_data.get('discount_tomans') or 0
        discount_reason = (cleaned_data.get('discount_reason') or '').strip()

        # پر کردن مقدار ریالی amount و discount_amount
        if cleaned_data.get('amount_tomans') is not None:
            cleaned_data['amount'] = int(cleaned_data['amount_tomans'] * 10000000)
        cleaned_data['discount_amount'] = int(discount_tomans * 10000000)

        # بررسی الزام ذکر دلیل در صورت ثبت تخفیف
        if discount_tomans > 0 and not discount_reason:
            self.add_error('discount_reason', 'هنگامی که مبلغ کسورات استثنایی وارد می‌شود، ذکر علت و جزئیات کسر اجاره الزامی است.')

        # CARD (دستگاه کارتخوان) و ONLINE_GATEWAY خودکار تایید میشن
        if payment_method in ['CARD', 'ONLINE_GATEWAY']:
            cleaned_data['is_approved'] = True

        # اگه اجاره هست، قیمت مصوب اتاق رو کپی کن
        if transaction_type == 'RENT' and resident and resident.room:
            cleaned_data['applicable_rent'] = resident.room.monthly_rent

        return cleaned_data

    def save(self, commit=True):
        # تبدیل میلیون تومان به ریال
        self.instance.amount = int(self.cleaned_data['amount_tomans'] * 10000000)
        disc_tomans = self.cleaned_data.get('discount_tomans') or 0
        self.instance.discount_amount = int(disc_tomans * 10000000)
        self.instance.discount_reason = (self.cleaned_data.get('discount_reason') or '').strip()
        return super().save(commit)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    form = TransactionForm
    list_display = [
        'receipt_number', 'resident_link', 'period_display', 'amount_display',
        'discount_display', 'applicable_rent_display',
        'transaction_type_badge', 'payment_method', 'approval_status',
        'payment_date', 'dormitory', 'created_by'
    ]

    list_filter = [
        'transaction_type', 'payment_method', 'is_approved', 'dormitory',
        'payment_date', 'created_by'
    ]

    search_fields = ['resident__first_name', 'resident__last_name', 'reference_number', 'id', 'period_name', 'discount_reason']
    date_hierarchy = 'payment_date'
    readonly_fields = ['created_at', 'period_name', 'period_start', 'period_end', 'receipt_display']
    list_select_related = ['resident', 'dormitory', 'created_by']
    actions = ['approve_transactions', 'unapprove_transactions']

    formfield_overrides = {
        jmodels.jDateField: {'widget': AdminPersianDateWidget},
    }

    class Media:
        css = {
            'all': ('dormitory/css/admin_jalali_datepicker.css',)
        }
        js = (
            'dormitory/js/admin_jalali_datepicker.js',
        )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'amount' in form.base_fields:
            form.base_fields['amount'].required = False
            form.base_fields['amount'].widget = forms.HiddenInput()
        if 'discount_amount' in form.base_fields:
            form.base_fields['discount_amount'].required = False
            form.base_fields['discount_amount'].widget = forms.HiddenInput()
        return form

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "dormitory":
            default_dorm_id = get_default_dormitory()
            if default_dorm_id:
                kwargs["initial"] = default_dorm_id
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if 'dormitory' not in initial:
            default_dorm_id = get_default_dormitory()
            if default_dorm_id:
                initial['dormitory'] = default_dorm_id
        return initial

    fieldsets = (
        ('اطلاعات پرداخت', {
            'fields': ('resident', 'dormitory', 'amount_tomans', 'transaction_type', 'payment_method')
        }),
        ('کسورات و تخفیف‌های استثنایی (اختیاری)', {
            'fields': ('discount_tomans', 'discount_reason'),
            'description': 'در صورت وقوع رویدادهای خاص (مانند سم‌پاشی، تخلیه چند روزه، تعمیرات و...) مبلغ کسر شده و علت آن را وارد کنید تا دوره ماهانه به طور کامل تسویه گردد.'
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

    def discount_display(self, obj):
        if obj.discount_amount and obj.discount_amount > 0:
            toman_str = f"{obj.discount_in_tomans:,.0f} تومان"
            reason = obj.discount_reason or 'کسورات استثنایی'
            return format_html(
                '<span style="background: #fef3c7; color: #92400e; border: 1px solid #fde68a; '
                'padding: 2px 7px; border-radius: 6px; font-size: 11px; font-weight: bold;" title="{}">'
                '🏷️ کسر {}</span>',
                reason, toman_str
            )
        return format_html('<span style="color: #94a3b8; font-size: 11px;">-</span>')

    discount_display.short_description = "کسورات استثنایی"
    discount_display.admin_order_field = 'discount_amount'

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

        rate_line = format_html(
            '<p><b>نرخ مصوب ماهانه:</b> {} تومان</p>',
            f"{obj.applicable_rent // 10:,.0f}"
        ) if obj.applicable_rent else ''

        discount_line = ''
        settlement_status_line = ''
        if obj.discount_amount and obj.discount_amount > 0:
            discount_line = format_html(
                '<p style="color: #b45309; background: #fffbeb; padding: 5px 8px; border-radius: 5px; border: 1px dashed #fde68a;">'
                '<b>🏷️ کسورات استثنایی:</b> {} تومان کسر<br>'
                '<small style="color: #78350f;"><b>علت کسر:</b> {}</small></p>',
                f"{obj.discount_in_tomans:,.0f}",
                obj.discount_reason or 'استثناء ماهانه'
            )
            settlement_status_line = format_html(
                '<p style="color: #15803d; font-size: 12px; font-weight: bold; margin-top: 6px;">'
                '✅ تسویه کامل این دوره ماهانه (با احتساب کسورات)</p>'
            )

        receipt_number_str = f"RCP-{obj.id:06d}" if obj.id else "RCP-PENDING"
        amount_str = f"{obj.amount // 10:,.0f}"

        return format_html(
            '''
            <div style="border: 2px solid #ddd; padding: 20px; max-width: 440px; font-family: monospace; 
                        background: #fafafa; border-radius: 8px; direction: rtl; text-align: right;">
                <h3 style="text-align: center; margin-bottom: 15px;">🧾 رسید پرداخت خوابگاه</h3>
                <hr>
                <p><b>شماره رسید:</b> {receipt_number_str}</p>
                <p><b>تاریخ:</b> {date}</p>
                <p><b>نام ساکن:</b> {resident}</p>
                <p><b>خوابگاه:</b> {dormitory}</p>
                <p><b>شماره اتاق:</b> {room}</p>
                <p><b>نوع تراکنش:</b> {type}</p>
                <p><b>روش پرداخت:</b> {method}</p>
                {period_line}
                {rate_line}
                {discount_line}
                <p style="font-size: 16px; font-weight: bold; color: #1e293b;">مبلغ خالص واریزی: {amount_str} تومان</p>
                {settlement_status_line}
                <p><b>وضعیت تایید:</b> <span style="color: {approval_color}; font-weight: bold;">{approval_text}</span></p>
                <p><b>شماره پیگیری:</b> {ref}</p>
                <p><b>توضیحات:</b> {desc}</p>
                <hr>
                <p style="text-align: center; font-size: 11px; color: #888;">
                    ثبت توسط: {created_by} | {created_at}
                </p>
            </div>
            ''',
            receipt_number_str=receipt_number_str,
            date=obj.payment_date.strftime('%Y/%m/%d - %H:%M'),
            resident=obj.resident.full_name,
            dormitory=obj.dormitory.name,
            room=obj.resident.room.room_number if obj.resident.room else 'N/A',
            type=obj.get_transaction_type_display(),
            method=obj.get_payment_method_display(),
            period_line=period_line,
            rate_line=rate_line,
            discount_line=discount_line,
            amount_str=amount_str,
            settlement_status_line=settlement_status_line,
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
            return format_html('{} تومان', f"{obj.applicable_rent // 10:,.0f}")
        return "-"

    applicable_rent_display.short_description = "نرخ اتاق"
    applicable_rent_display.admin_order_field = 'applicable_rent'

    def resident_link(self, obj):
        url = reverse('admin:dormitory_resident_change', args=[obj.resident_id])
        return format_html('<a href="{}">{}</a>', url, obj.resident.full_name)

    resident_link.short_description = "ساکن"
    resident_link.admin_order_field = 'resident__last_name'

    def amount_display(self, obj):
        amount_m = f"{obj.amount / 10000000:,.3f}"
        amount_t = f"{obj.amount // 10:,.0f}"
        return format_html('<b>{}</b> م.تومان<br><small style="color:#666;">({} تومان)</small>', amount_m, amount_t)

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

    def delete_queryset(self, request, queryset):
        affected_residents = list(Resident.objects.filter(transactions__in=queryset).distinct())
        super().delete_queryset(request, queryset)
        for resident in affected_residents:
            resident.recalculate_settled_until()

    def save_model(self, request, obj, form, change):
        if not change and form.cleaned_data.get('is_approved') is None:
            obj.is_approved = True

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


# ============================================
# DAILY NOTE & MAINTENANCE ADMIN
# ============================================
@admin.register(DailyNote)
class DailyNoteAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'dormitory', 'date', 'note_type_badge', 'room_display',
        'resident_link', 'is_resolved', 'created_by'
    ]
    list_filter = ['dormitory', 'note_type', 'is_resolved', 'date']
    search_fields = [
        'title', 'content', 'room__room_number',
        'resident__first_name', 'resident__last_name'
    ]
    list_editable = ['is_resolved']

    readonly_fields = ['created_at']

    formfield_overrides = {
        jmodels.jDateField: {'widget': AdminPersianDateWidget},
    }

    class Media:
        css = {
            'all': ('dormitory/css/admin_jalali_datepicker.css',)
        }
        js = (
            'dormitory/js/admin_jalali_datepicker.js',
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "dormitory":
            default_dorm_id = get_default_dormitory()
            if default_dorm_id:
                kwargs["initial"] = default_dorm_id
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if 'date' not in initial:
            initial['date'] = jdatetime.date.today() - datetime.timedelta(days=1)
        if 'dormitory' not in initial:
            default_dorm_id = get_default_dormitory()
            if default_dorm_id:
                initial['dormitory'] = default_dorm_id
        return initial

    def note_type_badge(self, obj):
        colors = {
            'MAINTENANCE': '#e74c3c',
            'DISCIPLINARY': '#e67e22',
            'CLEANING': '#3498db',
            'GENERAL': '#7f8c8d',
        }
        color = colors.get(obj.note_type, '#7f8c8d')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 8px; font-size: 11px;">{}</span>',
            color, obj.get_note_type_display()
        )
    note_type_badge.short_description = "نوع گزارش"

    def is_resolved_badge(self, obj):
        if obj.is_resolved:
            return format_html('<span style="color: #27ae60; font-weight: bold;">✅ حل شده</span>')
        return format_html('<span style="color: #e67e22; font-weight: bold;">⏳ در دست پیگیری</span>')
    is_resolved_badge.short_description = "وضعیت پیگیری"

    def room_display(self, obj):
        if obj.room:
            return f"اتاق {obj.room.room_number}"
        return "-"
    room_display.short_description = "اتاق"

    def resident_link(self, obj):
        if obj.resident:
            url = reverse('admin:dormitory_resident_change', args=[obj.resident.id])
            return format_html('<a href="{}">{}</a>', url, obj.resident.full_name)
        return "-"
    resident_link.short_description = "ساکن مربوطه"

    def save_model(self, request, obj, form, change):
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


