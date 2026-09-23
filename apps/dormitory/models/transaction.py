from django.db import models
from django_jalali.db import models as jmodels
import jdatetime

from apps.dormitory.jalali_utils import add_jalali_months, format_period_name


class Transaction(models.Model):
    """Immutable financial transaction record"""

    class TransactionType(models.TextChoices):
        RENT = 'RENT', 'Monthly Rent'
        DEPOSIT = 'DEPOSIT', 'Deposit'

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
    payment_date = jmodels.jDateTimeField(
        help_text="When the payment was actually made"
    )
    reference_number = models.CharField(
        max_length=255,
        blank=True,
        help_text="Bank reference or receipt number (optional)"
    )

    applicable_rent = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text="Room rent at the time of this transaction (in Rials). Only for RENT type."
    )

    period_start = jmodels.jDateField(
        null=True,
        blank=True,
        help_text="Start date of rent period covered (Jalali)"
    )
    period_end = jmodels.jDateField(
        null=True,
        blank=True,
        help_text="End date of rent period covered (Jalali)"
    )
    period_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Persian name of the covered month/period (e.g. اجاره مهر ماه ۱۴۰۵)"
    )

    is_approved = models.BooleanField(
        default=False,
        help_text="Whether the payment has been approved by supervisor (required for CASH and BANK_TRANSFER)"
    )

    created_by = models.ForeignKey(
        'accounts.Supervisor',
        on_delete=models.PROTECT,
        related_name='created_transactions'
    )
    created_at = jmodels.jDateTimeField(auto_now_add=True)  # Jalali

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-payment_date']

    def __str__(self):
        period_info = f" ({self.period_name})" if self.period_name else ""
        return f"{self.resident.full_name} - {self.get_transaction_type_display()}{period_info} - {self.amount_in_tomans:,} Tomans"

    @property
    def amount_in_tomans(self):
        """Convert Rials to Tomans for display"""
        return self.amount // 10

    @property
    def amount_in_million_tomans(self):
        """Convert Rials to Million Tomans for display"""
        return self.amount / 10_000_000

    @property
    def needs_approval(self):
        """Check if this transaction needs supervisor approval (Cash and Bank Transfer only)"""
        return self.payment_method in ['CASH', 'BANK_TRANSFER']

    def save(self, *args, **kwargs):
        # Auto-fill applicable_rent if empty for RENT type
        if self.transaction_type == self.TransactionType.RENT and not self.applicable_rent:
            if self.resident and self.resident.room and self.resident.room.monthly_rent:
                self.applicable_rent = self.resident.room.monthly_rent

        # Auto-compute period for RENT transactions
        if self.transaction_type == self.TransactionType.RENT:
            rent_rate = self.applicable_rent or (self.resident.room.monthly_rent if self.resident and self.resident.room else self.amount)
            months_paid = max(1, round(self.amount / rent_rate)) if rent_rate and rent_rate > 0 else 1

            if not self.period_start and self.resident:
                base_date = self.resident.settled_until or self.resident.entry_date or jdatetime.date.today()
                self.period_start = base_date

            if self.period_start and not self.period_end:
                self.period_end = add_jalali_months(self.period_start, months_paid)

            if not self.period_name and self.period_start and self.period_end:
                self.period_name = format_period_name(self.period_start, self.period_end)

        super().save(*args, **kwargs)

        # If approved RENT payment, advance resident's settled_until
        if self.is_approved and self.transaction_type == self.TransactionType.RENT and self.period_end:
            res = self.resident
            if res:
                if not res.settled_until or self.period_end > res.settled_until:
                    res.settled_until = self.period_end
                    res.save(update_fields=['settled_until'])

