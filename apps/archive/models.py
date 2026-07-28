from django.db import models
from django_jalali.db import models as jmodels


class ArchivedResident(models.Model):
    """Residents who have left the dormitory"""
    # همه فیلدهای Resident کپی میشن
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    national_code = models.CharField(max_length=10)
    phone_number = models.CharField(max_length=15)
    parent_phone_number = models.CharField(max_length=15, blank=True, null=True)
    occupation = models.CharField(max_length=20)
    entry_date = jmodels.jDateField()
    exit_date = jmodels.jDateField(null=True, blank=True)
    monthly_payment_day = models.IntegerField()
    status = models.CharField(max_length=10)
    original_id = models.IntegerField(help_text="Original resident ID")
    archived_at = jmodels.jDateTimeField(auto_now_add=True)

    # اطلاعات اتاق و خوابگاه زمان خروج
    dormitory_name = models.CharField(max_length=255)
    room_number = models.IntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Archived Resident"
        verbose_name_plural = "Archived Residents"
        ordering = ['-archived_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name} (Archived)"


class ArchivedTransaction(models.Model):
    """Transactions of archived residents"""
    resident_name = models.CharField(max_length=255)
    amount = models.PositiveBigIntegerField()
    transaction_type = models.CharField(max_length=20)
    payment_method = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    payment_date = jmodels.jDateTimeField()
    reference_number = models.CharField(max_length=255, blank=True)
    applicable_rent = models.PositiveBigIntegerField(null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    dormitory_name = models.CharField(max_length=255)
    original_id = models.IntegerField(help_text="Original transaction ID")
    original_resident_id = models.IntegerField()
    archived_at = jmodels.jDateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Archived Transaction"
        verbose_name_plural = "Archived Transactions"
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.resident_name} - {self.transaction_type} - {self.amount}"