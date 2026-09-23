from datetime import timedelta
import jdatetime
from typing import List, Dict, Any, Optional

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django_jalali.db import models as jmodels

from apps.dormitory.jalali_utils import (
    add_jalali_months,
    format_period_name,
    calculate_unpaid_periods,
)


class Resident(models.Model):
    """Represents a person living in the dormitory"""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        LEFT = "LEFT", "Left"

    # Personal information
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)

    national_code = models.CharField(
        max_length=10,
        unique=True,
        help_text="National identification number",
    )

    phone_number = models.CharField(
        max_length=11,
        unique=True,
    )

    parent_phone_number = models.CharField(
        max_length=11,
        blank=True,
        null=True,
    )

    # Room assignment
    room = models.ForeignKey(
        "dormitory.Room",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="residents",
    )

    dormitory = models.ForeignKey(
        "dormitory.Dormitory",
        on_delete=models.PROTECT,
        related_name="residents",
    )

    # Dates
    entry_date = jmodels.jDateField(
        help_text="Date when resident moved in"
    )

    exit_date = jmodels.jDateField(
        null=True,
        blank=True,
        help_text="Date when resident moved out (if applicable)",
    )

    monthly_payment_day = models.IntegerField(
        default=1,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(30),
        ],
        help_text="Day of month when recurring payment is due (1-30)",
    )

    # Status
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    settled_until = jmodels.jDateField(
        null=True,
        blank=True,
        help_text="Date until which the resident has fully paid (pre-paid coverage end date)"
    )

    occupation = models.CharField(
        max_length=20,
        choices=[
            ('STUDENT', 'Student'),
            ('EMPLOYED', 'Employed'),
            ('OTHER', 'Other'),
        ],
        default='STUDENT',
        help_text="Resident occupation type",
    )

    # Registration
    registered_by = models.ForeignKey(
        'accounts.Supervisor',
        on_delete=models.PROTECT,
        related_name="registered_residents",
    )

    id_card_image = models.ImageField(
        upload_to="id_cards/",
        null=True,
        blank=True,
        help_text="Scanned copy of ID card",
    )

    created_at = jmodels.jDateTimeField(auto_now_add=True)  # Jalali

    class Meta:
        verbose_name = "Resident"
        verbose_name_plural = "Residents"
        ordering = [
            "dormitory",
            "room",
            "last_name",
            "first_name",
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self) -> str:
        """Return resident full name"""
        return f"{self.first_name} {self.last_name}"

    @property
    def is_active(self) -> bool:
        """Return True if resident currently lives in dormitory"""
        return (
            self.status == self.Status.ACTIVE
            and self.exit_date is None
        )

    # ========================================================
    # ACCOUNTING & PRE-PAYMENT LOGIC (حسابداری پیش‌پرداخت و دیرکرد)
    # ========================================================

    @property
    def current_monthly_rent_tomans(self) -> int:
        """Monthly room rent in Tomans"""
        if self.room and self.room.monthly_rent:
            return self.room.monthly_rent // 10
        return 0

    @property
    def is_in_debt(self) -> bool:
        """
        Check if resident has unpaid rent (Jalali comparison).
        In prepaid model, debt exists when settled_until is None (and today >= entry_date)
        or when today >= settled_until.
        """
        today = jdatetime.date.today()
        if not self.settled_until:
            if self.entry_date and today >= self.entry_date:
                return True
            return False
        return today >= self.settled_until

    @property
    def overdue_days(self) -> int:
        """
        Calculate exact overdue days.
        Returns > 0 if today is strictly past settled_until (or entry_date if unsettled).
        """
        today = jdatetime.date.today()
        if not self.settled_until:
            if self.entry_date and today > self.entry_date:
                return (today - self.entry_date).days
            return 0

        if today > self.settled_until:
            return (today - self.settled_until).days
        return 0

    @property
    def days_until_due(self) -> int:
        """
        Calculate days remaining until next payment is due.
        Applicable when resident is settled (settled_until >= today).
        """
        if not self.settled_until:
            return 0
        today = jdatetime.date.today()
        if self.settled_until >= today:
            return (self.settled_until - today).days
        return 0

    @property
    def unpaid_periods(self) -> List[Dict[str, Any]]:
        """
        Returns list of unpaid monthly periods up to today.
        Billing is strictly monthly (not daily pro-rated).
        """
        start_calc = self.settled_until or self.entry_date
        if not start_calc:
            return []

        rent_rials = self.room.monthly_rent if self.room else 0
        return calculate_unpaid_periods(
            start_date=start_calc,
            as_of_date=jdatetime.date.today(),
            monthly_rent_rials=rent_rials
        )

    @property
    def unpaid_months_display(self) -> str:
        """Human-readable Persian names of unpaid months"""
        periods = self.unpaid_periods
        if not periods:
            return "تسویه کامل"
        return " و ".join([p["name"] for p in periods])

    @property
    def total_debt_amount_tomans(self) -> int:
        """
        Total unpaid rent amount in Tomans.
        Strictly monthly: count of unpaid months * monthly rent.
        """
        return len(self.unpaid_periods) * self.current_monthly_rent_tomans

    @property
    def total_debt_amount_rials(self) -> int:
        """Total unpaid rent amount in Rials"""
        return self.total_debt_amount_tomans * 10

    @property
    def last_paid_period_display(self) -> str:
        """Shows the last period covered by previous payments"""
        if not self.settled_until:
            return "پرداختی ثبت نشده"
        prev_date = add_jalali_months(self.settled_until, -1)
        name = format_period_name(prev_date, self.settled_until)
        return f"{name} (تسویه تا {self.settled_until.strftime('%Y/%m/%d')})"

    @property
    def financial_status_summary(self) -> Dict[str, Any]:
        """
        Comprehensive financial status summary for dashboard, badges, and detail views.
        """
        today = jdatetime.date.today()
        if not self.is_active:
            return {
                "status": "INACTIVE",
                "label": "غیرفعال / خروج",
                "color": "#95a5a6",
                "overdue_days": 0,
                "days_until_due": 0,
                "unpaid_months": "",
                "debt_tomans": 0,
                "details": f"وضعیت ساکن: {self.get_status_display()}",
                "last_paid": self.last_paid_period_display,
            }

        if not self.room:
            return {
                "status": "NO_ROOM",
                "label": "بدون اتاق",
                "color": "#95a5a6",
                "overdue_days": 0,
                "days_until_due": 0,
                "unpaid_months": "",
                "debt_tomans": 0,
                "details": "اتاقی برای ساکن تخصیص داده نشده است.",
                "last_paid": self.last_paid_period_display,
            }

        unpaid = self.unpaid_periods
        monthly_rent_tomans = self.current_monthly_rent_tomans

        if not unpaid:
            days_left = self.days_until_due
            due_str = self.settled_until.strftime('%Y/%m/%d') if self.settled_until else '-'
            return {
                "status": "SETTLED",
                "label": "تسویه به روز",
                "color": "#27ae60",
                "overdue_days": 0,
                "days_until_due": days_left,
                "unpaid_months": "",
                "debt_tomans": 0,
                "details": f"{days_left} روز مانده تا سررسید {due_str}",
                "last_paid": self.last_paid_period_display,
            }
        else:
            overdue = self.overdue_days
            debt = len(unpaid) * monthly_rent_tomans
            unpaid_names = " و ".join([p["name"] for p in unpaid])

            if overdue == 0:
                return {
                    "status": "DUE_TODAY",
                    "label": "سررسید امروز",
                    "color": "#f39c12",
                    "overdue_days": 0,
                    "days_until_due": 0,
                    "unpaid_months": unpaid_names,
                    "debt_tomans": debt,
                    "details": f"موعد {unpaid[0]['name']} فرا رسیده ({debt:,.0f} تومان)",
                    "last_paid": self.last_paid_period_display,
                }
            else:
                return {
                    "status": "OVERDUE",
                    "label": f"{overdue} روز تاخیر",
                    "color": "#e74c3c",
                    "overdue_days": overdue,
                    "days_until_due": 0,
                    "unpaid_months": unpaid_names,
                    "debt_tomans": debt,
                    "details": f"{overdue} روز تاخیر - بدهی: {unpaid_names} ({debt:,.0f} تومان)",
                    "last_paid": self.last_paid_period_display,
                }

    def advance_settlement(self, months: int = 1, save: bool = True) -> jdatetime.date:
        """
        Advance settled_until date by N months.
        If settled_until is None, advances from entry_date.
        """
        base_date = self.settled_until or self.entry_date or jdatetime.date.today()
        new_settled = add_jalali_months(base_date, months)
        self.settled_until = new_settled
        if save:
            self.save(update_fields=['settled_until'])
        return new_settled

    def get_recent_transactions(self, days: int = 30):
        """Return transactions from the last N days"""
        since_date = jdatetime.datetime.now() - timedelta(days=days)
        return self.transactions.filter(
            payment_date__gte=since_date
        ).order_by("-payment_date")

    def has_paid_this_month(self) -> bool:
        """Check whether resident has paid this month's rent (Jalali month)"""
        today = jdatetime.date.today()
        return self.transactions.filter(
            transaction_type="RENT",
            payment_date__year=today.year,
            payment_date__month=today.month,
        ).exists()
