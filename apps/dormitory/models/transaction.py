from django.db import models
from django_jalali.db import models as jmodels


class Transaction(models.Model):
    """Immutable financial transaction record"""

    class TransactionType(models.TextChoices):
        RENT = 'RENT', 'Monthly Rent'
        DEPOSIT = 'DEPOSIT', 'Security Deposit'
        OTHER = 'OTHER', 'Other Payment'

    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        CARD = 'CARD', 'Card Payment'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
        ONLINE_GATEWAY = 'ONLINE_GATEWAY', 'Online Gateway'

    resident = models.ForeignKey(
        'dormitory.Resident',
        on_delete=models.PROTECT,
        related_name='transactions'
    )
    dormitory = models.ForeignKey(
        'dormitory.Dormitory',
        on_delete=models.PROTECT,
        related_name='transactions'
    )
    amount = models.PositiveBigIntegerField(
        help_text="Amount in Rials (automatically converted from Tomans)"
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices
    )
    description = models.TextField(
        blank=True,
        help_text="Additional notes about the transaction"
    )
    payment_date = jmodels.jDateTimeField(  # Changed to Jalali
        help_text="When the payment was actually made"
    )
    reference_number = models.CharField(
        max_length=255,
        blank=True,
        help_text="Bank reference or receipt number (optional)"
    )
    created_by = models.ForeignKey(
        'accounts.Supervisor',  # درستش اینه
        on_delete=models.PROTECT,
        related_name='created_transactions'
    )
    created_at = jmodels.jDateTimeField(auto_now_add=True)  # Changed to Jalali

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.resident.full_name} - {self.transaction_type} - {self.amount} Rials"

    @property
    def amount_in_tomans(self):
        """Convert Rials to Tomans for display"""
        return self.amount / 10