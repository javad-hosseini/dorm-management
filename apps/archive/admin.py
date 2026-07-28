from django.contrib import admin
from .models import ArchivedResident, ArchivedTransaction


@admin.register(ArchivedResident)
class ArchivedResidentAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'national_code', 'dormitory_name', 'room_number',
                    'entry_date', 'exit_date', 'archived_at']
    search_fields = ['first_name', 'last_name', 'national_code']
    list_filter = ['dormitory_name', 'archived_at']
    readonly_fields = ['original_id', 'archived_at']

    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"

    full_name.short_description = "Name"

    def has_add_permission(self, request):
        return False  # فقط از طریق آرشیو خودکار پر میشه

    def has_change_permission(self, request, obj=None):
        return False  # آرشیو قابل ویرایش نیست


@admin.register(ArchivedTransaction)
class ArchivedTransactionAdmin(admin.ModelAdmin):
    list_display = ['resident_name', 'amount_display', 'transaction_type',
                    'payment_method', 'payment_date', 'dormitory_name']
    search_fields = ['resident_name', 'reference_number']
    list_filter = ['transaction_type', 'payment_method', 'payment_date']
    readonly_fields = ['original_id', 'original_resident_id', 'archived_at']

    def amount_display(self, obj):
        return f"{obj.amount / 10000000:,.3f}M Tomans"

    amount_display.short_description = "Amount"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False