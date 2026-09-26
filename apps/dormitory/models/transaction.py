from django.db import models
from django_jalali.db import models as jmodels
import jdatetime

from apps.dormitory.jalali_utils import add_jalali_months, format_period_name, calculate_settlement_advance
from .dormitory import get_default_dormitory


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
        related_name='transactions',
        default=get_default_dormitory,
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

    discount_amount = models.PositiveBigIntegerField(
        default=0,
        verbose_name="مبلغ کسورات / تخفیف استثنایی (ریال)",
        help_text="مبلغ کسر شده از اجاره مصوب به دلیل سم‌پاشی، تخلیه موقت یا توافق مدیریت"
    )
    discount_reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="علت و جزئیات کسورات",
        help_text="مثال: سم‌پاشی خوابگاه و ۵ روز تخلیه موقت اتاق"
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
    def discount_in_tomans(self) -> int:
        """Convert discount Rials to Tomans for display"""
        return (self.discount_amount or 0) // 10

    @property
    def discount_in_million_tomans(self) -> float:
        """Convert discount Rials to Million Tomans for display"""
        return (self.discount_amount or 0) / 10_000_000

    @property
    def has_discount(self) -> bool:
        """Check if any discount/deduction was applied to this transaction"""
        return bool(self.discount_amount and self.discount_amount > 0)

    @property
    def total_effective_amount(self) -> int:
        """Total effective amount covering rent: payment amount + exceptional discount"""
        return self.amount + (self.discount_amount or 0)

    @property
    def total_effective_amount_in_tomans(self) -> int:
        """Total effective amount covering rent in Tomans"""
        return self.total_effective_amount // 10

    @property
    def needs_approval(self):
        """Check if this transaction needs supervisor approval (Cash and Bank Transfer only)"""
        return self.payment_method in ['CASH', 'BANK_TRANSFER']

    def save(self, *args, **kwargs):
        is_update = bool(self.pk)
        old_approved = False
        if is_update:
            try:
                old_tx = Transaction.objects.get(pk=self.pk)
                old_approved = old_tx.is_approved
            except Transaction.DoesNotExist:
                pass
        else:
            if self.payment_method in [self.PaymentMethod.CARD, self.PaymentMethod.ONLINE_GATEWAY]:
                self.is_approved = True

        # Auto-fill applicable_rent if empty for RENT type
        if self.transaction_type == self.TransactionType.RENT and not self.applicable_rent:
            if self.resident and self.resident.room:
                rate_date = self.period_start
                if not rate_date and self.payment_date:
                    rate_date = self.payment_date.date() if hasattr(self.payment_date, 'date') else self.payment_date
                if not rate_date:
                    rate_date = self.resident.settled_until or self.resident.entry_date or jdatetime.date.today()
                self.applicable_rent = self.resident.room.get_rent_for_date(rate_date)
            elif self.resident and self.resident.room and self.resident.room.monthly_rent:
                self.applicable_rent = self.resident.room.monthly_rent

        # Auto-compute period for RENT transactions
        if self.transaction_type == self.TransactionType.RENT:
            rent_rate = self.applicable_rent or (self.resident.room.monthly_rent if self.resident and self.resident.room else self.amount)
            effective_paid = self.total_effective_amount

            if not self.period_start and self.resident:
                base_date = self.resident.settled_until or self.resident.entry_date or jdatetime.date.today()
                self.period_start = base_date

            if self.period_start and not self.period_end:
                rent_resolver = self.resident.room.get_rent_for_date if self.resident and self.resident.room else None
                computed_end, days_adv, computed_name = calculate_settlement_advance(
                    start_date=self.period_start,
                    amount_rials=effective_paid,
                    monthly_rent_rials=rent_rate,
                    rent_resolver=rent_resolver
                )
                self.period_end = computed_end
                if not self.period_name and computed_name:
                    self.period_name = computed_name

            if not self.period_name and self.period_start and self.period_end:
                self.period_name = format_period_name(self.period_start, self.period_end)

        super().save(*args, **kwargs)

        # If approved RENT payment, advance resident's settled_until
        if self.resident and self.transaction_type == self.TransactionType.RENT:
            if self.is_approved and self.period_end:
                res = self.resident
                if not res.settled_until or self.period_end > res.settled_until:
                    res.settled_until = self.period_end
                    res.save(update_fields=['settled_until'])
            elif old_approved and not self.is_approved:
                # If unapproved, recalculate settled_until from remaining approved transactions
                self.resident.recalculate_settled_until()

    def delete(self, *args, **kwargs):
        res = self.resident
        tx_type = self.transaction_type
        approved = self.is_approved
        res_to_recalc = res if (approved and tx_type == self.TransactionType.RENT) else None

        super().delete(*args, **kwargs)

        if res_to_recalc:
            res_to_recalc.recalculate_settled_until()


from django.db.models.signals import post_delete
from django.dispatch import receiver


@receiver(post_delete, sender=Transaction)
def on_transaction_deleted(sender, instance, **kwargs):
    if instance.resident and instance.transaction_type == Transaction.TransactionType.RENT and instance.is_approved:
        instance.resident.recalculate_settled_until()

