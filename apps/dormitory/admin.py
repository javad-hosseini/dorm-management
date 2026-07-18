# admin.py - Admin configuration for better management
from django.contrib import admin
from django import forms
from django.apps import apps

from .models import Dormitory, Room, Resident, Transaction


@admin.register(Dormitory)
class DormitoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'total_rooms', 'occupied_rooms', 'empty_rooms', 'total_active_residents']
    search_fields = ['name', 'address']
    list_filter = ['created_at']


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'dormitory', 'room_number', 'capacity', 'current_occupants', 'available_capacity',
                    'monthly_rent']
    list_filter = ['dormitory', 'capacity']
    search_fields = ['room_number', 'dormitory__name']
    empty_value_display = 'Not Available'


@admin.register(Resident)
class ResidentAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'national_code', 'phone_number', 'dormitory', 'room', 'status', 'monthly_payment_day',
                    'entry_date']
    list_filter = ['status', 'dormitory', 'entry_date', 'monthly_payment_day']
    search_fields = ['first_name', 'last_name', 'national_code', 'phone_number']
    readonly_fields = ['created_at']

    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'national_code', 'phone_number', 'parent_phone_number')
        }),
        ('Room Assignment', {
            'fields': ('dormitory', 'room', 'monthly_payment_day')
        }),
        ('Status & Dates', {
            'fields': ('entry_date', 'exit_date', 'status')
        }),
        ('Administrative', {
            'fields': ('registered_by', 'id_card_image')
        }),
    )


class TransactionForm(forms.ModelForm):
    amount_tomans = forms.DecimalField(
        max_digits=12,
        decimal_places=1,
        label="Amount (Tomans)",
        help_text="Enter amount in Tomans (e.g., 2.5 for 2,500,000 Tomans)"
    )

    class Meta:
        model = Transaction
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # فقط اگه created_by توی form باشه، queryset رو تنظیم کن
        if 'created_by' in self.fields:
            Supervisor = apps.get_model('accounts', 'Supervisor')
            self.fields['created_by'].queryset = Supervisor.objects.all()

        if self.instance and self.instance.pk:
            self.fields['amount_tomans'].initial = self.instance.amount / 10

    def save(self, commit=True):
        self.instance.amount = int(self.cleaned_data['amount_tomans'] * 10)
        return super().save(commit)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    form = TransactionForm
    list_display = ['resident', 'amount_in_tomans_display', 'transaction_type', 'payment_method', 'payment_date',
                    'dormitory', 'created_by']
    list_filter = ['transaction_type', 'payment_method', 'dormitory', 'payment_date', 'created_by']
    search_fields = ['resident__first_name', 'resident__last_name', 'reference_number']
    date_hierarchy = 'payment_date'
    readonly_fields = ['created_at']  # created_by رو از اینجا بردار
    list_select_related = ['resident', 'dormitory', 'created_by']

    fieldsets = (
        ('Transaction Information', {
            'fields': ('resident', 'dormitory', 'amount_tomans', 'transaction_type', 'payment_method')
        }),
        ('Payment Details', {
            'fields': ('payment_date', 'reference_number', 'description')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at'),
        }),
    )

    def amount_in_tomans_display(self, obj):
        """Display amount in Tomans in list view"""
        return f"{obj.amount / 10:,.1f} Tomans"

    amount_in_tomans_display.short_description = "Amount"
    amount_in_tomans_display.admin_order_field = 'amount'

    def save_model(self, request, obj, form, change):
        # اگه created_by خالی بود، کاربر فعلی رو بذار
        if not obj.created_by_id:
            Supervisor = apps.get_model('accounts', 'Supervisor')
            obj.created_by = Supervisor.objects.get(id=request.user.id)
        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'amount' in form.base_fields:
            form.base_fields['amount'].widget = forms.HiddenInput()
        return form