from django import forms
from django.apps import apps
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db import models
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.html import format_html

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
        label="Monthly Rent (Million Tomans)",
        help_text="Enter rent in Million Tomans (e.g., 4 for 4,000,000 Tomans, 2.5 for 2,500,000 Tomans)"
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

    def lookups(self, request, model_admin):
        return [
            ('has_space', 'Has empty beds'),
            ('full', 'Full'),
            ('empty', 'Completely empty'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'has_space':
            return queryset.annotate(
                occ=Count('residents', filter=Q(residents__exit_date__isnull=True))
            ).filter(capacity__gt=models.F('occ'))
        if self.value() == 'full':
            return queryset.annotate(
                occ=Count('residents', filter=Q(residents__exit_date__isnull=True))
            ).filter(capacity__lte=models.F('occ'))
        if self.value() == 'empty':
            return queryset.annotate(
                occ=Count('residents', filter=Q(residents__exit_date__isnull=True))
            ).filter(occ=0)
        return queryset


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
    actions = ['mark_as_full', 'mark_as_available']

    def monthly_rent_display(self, obj):
        """Show rent in Million Tomans"""
        return f"{obj.monthly_rent / 10000000:,.1f} Million Tomans"

    monthly_rent_display.short_description = "Monthly Rent"

    monthly_rent_display.short_description = "Monthly Rent"
    monthly_rent_display.admin_order_field = 'monthly_rent'

    def vacancy_status(self, obj):
        """Show colored vacancy status"""
        available = obj.available_capacity
        if available > 0:
            return format_html(
                '<span style="color: green; font-weight: bold;">{} empty bed{}</span>',
                available,
                's' if available > 1 else ''
            )
        return format_html('<span style="color: red; font-weight: bold;">Full</span>')

    vacancy_status.short_description = "Vacancy"

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

    @admin.action(description="Mark as full")
    def mark_as_full(self, request, queryset):
        pass

    @admin.action(description="Mark as available")
    def mark_as_available(self, request, queryset):
        pass


# ============================================
# TRANSACTION INLINE (نشون دادن پرداختی‌ها داخل جزئیات ساکن)
# ============================================
class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    fields = ['amount_display', 'transaction_type', 'payment_method', 'payment_date', 'reference_number',
              'view_receipt']
    readonly_fields = ['amount_display', 'view_receipt']
    can_delete = False
    show_change_link = True
    ordering = ['-payment_date']

    def amount_display(self, obj):
        """Show amount in Tomans"""
        amount = obj.amount / 10
        return format_html('<b>{}</b> Tomans', f'{amount:,.1f}')

    amount_display.short_description = "Amount"

    def view_receipt(self, obj):
        """Link to view receipt details"""
        if obj.pk:
            url = reverse('admin:dormitory_transaction_change', args=[obj.pk])
            return format_html('<a href="{}" target="_blank">📄 View Receipt</a>', url)
        return "-"

    view_receipt.short_description = "Receipt"

    def has_add_permission(self, request, obj):
        return False  # از طریق Transaction admin اضافه کن


# ============================================
# RESIDENT ADMIN
# ============================================
@admin.register(Resident)
class ResidentAdmin(admin.ModelAdmin):
    list_display = [
        'full_name', 'national_code', 'occupation_badge', 'dormitory_link',
        'room_number_display', 'status_badge', 'monthly_payment_day',
        'entry_date', 'payment_summary', 'view_transactions_link',
        'settled_until', 'debt_status',

    ]

    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'national_code', 'occupation', 'phone_number', 'parent_phone_number')
        }),
        ('Room Assignment', {
            'fields': ('dormitory', 'room', 'monthly_payment_day')
        }),
        ('Status & Dates', {
            'fields': ('entry_date', 'exit_date', 'settled_until', 'status')
        }),
        ('Administrative', {
            'fields': ('registered_by', 'id_card_image')
        }),
        ('Payment History', {
            'fields': ('payment_history_display',),
            'classes': ('wide',)
        }),
    )
    list_filter = [
        'status', 'occupation', 'dormitory', 'entry_date', 'monthly_payment_day', 'settled_until'

    ]
    search_fields = ['first_name', 'last_name', 'national_code', 'phone_number', 'room__room_number']
    readonly_fields = ['created_at', 'payment_history_display']
    list_select_related = ['dormitory', 'room']
    inlines = [TransactionInline]

    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'national_code', 'occupation', 'phone_number', 'parent_phone_number')
        }),
        ('Room Assignment', {
            'fields': ('dormitory', 'room', 'monthly_payment_day')
        }),
        ('Status & Dates', {
            'fields': ('entry_date', 'exit_date', 'settled_until', 'status')
        }),
        ('Administrative', {
            'fields': ('registered_by', 'id_card_image')
        }),
        ('Payment History', {
            'fields': ('payment_history_display',),
            'classes': ('wide',)
        }),
    )

    def debt_status(self, obj):
        """Show debt status with color"""
        if obj.is_in_debt:
            return format_html(
                '<span style="color: red; font-weight: bold;">⚠️ In Debt</span>'
            )
        return format_html(
            '<span style="color: green;">✅ Settled</span>'
        )

    debt_status.short_description = "Debt Status"

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


# ============================================
# TRANSACTION FORM & ADMIN
# ============================================
class TransactionForm(forms.ModelForm):
    amount_tomans = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        label="Amount (Tomans)",
        help_text="Enter amount in Tomans (e.g., 2.5 for 2,500,000 Tomans)"
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
            self.fields['created_by'].required = True

        if self.instance and self.instance.pk:
            # تبدیل ریال به میلیون تومان
            self.fields['amount_tomans'].initial = self.instance.amount / 10000000

        if 'is_approved' in self.fields:
            self.fields['is_approved'].help_text = "Check to approve. Required for CASH and CARD tranfers."

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method')
        transaction_type = cleaned_data.get('transaction_type')  # این خط رو اضافه کن
        resident = cleaned_data.get('resident')

        # BANK_TRANSFER and ONLINE_GATEWAY are auto-approved
        if payment_method in ['BANK_TRANSFER', 'ONLINE_GATEWAY']:
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
        'receipt_number', 'resident_link', 'amount_display', 'applicable_rent_display',
        'transaction_type_badge', 'payment_method', 'approval_status',
        'payment_date', 'dormitory', 'created_by'
    ]

    list_filter = [
        'transaction_type', 'payment_method', 'is_approved', 'dormitory',
        'payment_date', 'created_by'
    ]

    search_fields = ['resident__first_name', 'resident__last_name', 'reference_number', 'id']
    date_hierarchy = 'payment_date'
    readonly_fields = ['created_at', 'receipt_display']
    list_select_related = ['resident', 'dormitory', 'created_by']
    actions = ['approve_transactions', 'unapprove_transactions']

    fieldsets = (
        ('Transaction Information', {
            'fields': ('resident', 'dormitory', 'amount_tomans', 'transaction_type', 'payment_method')
        }),
        ('Payment Details', {
            'fields': ('payment_date', 'reference_number', 'description')
        }),
        ('Approval', {
            'fields': ('is_approved',),
            'description': 'CASH and BANK_TRANSFER payments need approval'
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at'),
        }),
        ('Receipt Preview', {
            'fields': ('receipt_display',),
            'classes': ('wide', 'collapse')
        }),
    )

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

        return format_html(
            '''
            <div style="border: 2px solid #ddd; padding: 20px; max-width: 400px; font-family: monospace; 
                        background: #fafafa; border-radius: 5px;">
                <h3 style="text-align: center; margin-bottom: 15px;">🧾 PAYMENT RECEIPT</h3>
                <hr>
                <p><b>Receipt No:</b> RCP-{id:06d}</p>
                <p><b>Date:</b> {date}</p>
                <p><b>Resident:</b> {resident}</p>
                <p><b>Dormitory:</b> {dormitory}</p>
                <p><b>Room:</b> {room}</p>
                <p><b>Type:</b> {type}</p>
                <p><b>Method:</b> {method}</p>
                {rate_line}
                <p style="font-size: 18px; font-weight: bold;">Amount: {amount:,.3f}M Tomans</p>
                <p><b>Status:</b> <span style="color: {approval_color};">{approval_text}</span></p>
                <p><b>Ref:</b> {ref}</p>
                <p><b>Description:</b> {desc}</p>
                <hr>
                <p style="text-align: center; font-size: 11px; color: #888;">
                    Registered by: {created_by} | {created_at}
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
            rate_line=format_html(
                '<p><b>Room Rate:</b> {}M Tomans</p>',
                f"{obj.applicable_rent / 10000000:,.3f}"
            ) if obj.applicable_rent else '',
            amount=obj.amount / 10000000,
            approval_text=approval_text,
            approval_color=approval_color,
            ref=obj.reference_number or '-',
            desc=obj.description or '-',
            created_by=obj.created_by.full_name if obj.created_by else '-',
            created_at=obj.created_at.strftime('%Y/%m/%d - %H:%M')
        )

    receipt_display.short_description = "Receipt"

    def receipt_number(self, obj):
        return f"RCP-{obj.id:06d}"

    receipt_number.short_description = "Receipt #"
    receipt_number.admin_order_field = 'id'

    def applicable_rent_display(self, obj):
        if obj.applicable_rent:
            return f"{obj.applicable_rent / 10000000:,.3f}M Tomans"
        return "-"

    applicable_rent_display.short_description = "Room Rate"
    applicable_rent_display.admin_order_field = 'applicable_rent'

    def resident_link(self, obj):
        url = reverse('admin:dormitory_resident_change', args=[obj.resident_id])
        return format_html('<a href="{}">{}</a>', url, obj.resident.full_name)

    resident_link.short_description = "Resident"
    resident_link.admin_order_field = 'resident__last_name'

    def amount_display(self, obj):
        amount = obj.amount / 10000000
        return format_html('<b>{}</b>M Tomans', f'{amount:,.3f}')

    amount_display.short_description = "Amount"
    amount_display.admin_order_field = 'amount'

    def transaction_type_badge(self, obj):
        colors = {'RENT': '#3498db', 'DEPOSIT': '#e67e22', 'OTHER': '#7f8c8d'}
        color = colors.get(obj.transaction_type, '#7f8c8d')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 10px; white-space: nowrap;">{}</span>',
            color, obj.get_transaction_type_display()
        )

    transaction_type_badge.short_description = "Type"

    def approval_status(self, obj):
        # CASH و BANK_TRANSFER نیاز به تأیید دارن
        if obj.payment_method in ['CASH', 'BANK_TRANSFER']:
            if obj.is_approved:
                return format_html(
                    '<span style="background: #27ae60; color: white; padding: 2px 8px; border-radius: 10px; white-space: nowrap;">✅ Approved</span>'
                )
            else:
                return format_html(
                    '<span style="background: #e74c3c; color: white; padding: 2px 8px; border-radius: 10px; white-space: nowrap;">⏳ Pending</span>'
                )
        # CARD و ONLINE_GATEWAY خودکار تأیید میشن
        return format_html(
            '<span style="background: #3498db; color: white; padding: 2px 8px; border-radius: 10px; white-space: nowrap;">🔵 Auto</span>'
        )

    approval_status.short_description = "Approval"

    @admin.action(description="✅ Approve selected transactions")
    def approve_transactions(self, request, queryset):
        # فقط CASH و BANK_TRANSFER که تأیید نشدن
        updated = queryset.filter(
            payment_method__in=['CASH', 'BANK_TRANSFER'],
            is_approved=False
        ).update(is_approved=True)
        self.message_user(request, f"{updated} transaction(s) approved.")

    @admin.action(description="❌ Unapprove selected transactions")
    def unapprove_transactions(self, request, queryset):
        # فقط CASH و BANK_TRANSFER که تأیید شدن
        updated = queryset.filter(
            payment_method__in=['CASH', 'BANK_TRANSFER'],
            is_approved=True
        ).update(is_approved=False)
        self.message_user(request, f"{updated} transaction(s) unapproved.")

    def save_model(self, request, obj, form, change):
        # CARD و ONLINE_GATEWAY خودکار تأیید میشن
        if obj.payment_method in ['CARD', 'ONLINE_GATEWAY']:
            obj.is_approved = True
        # CASH و BANK_TRANSFER اول تأیید نشده هستن
        elif obj.payment_method in ['CASH', 'BANK_TRANSFER'] and not change:
            obj.is_approved = False

        if not change and not obj.created_by_id:
            Supervisor = apps.get_model('accounts', 'Supervisor')
            try:
                obj.created_by = Supervisor.objects.get(id=request.user.id)
            except Supervisor.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'amount' in form.base_fields:
            form.base_fields['amount'].widget = forms.HiddenInput()
        return form
