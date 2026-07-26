from datetime import date, timedelta

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django_jalali.db import models as jmodels


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
        max_length=15,
        unique=True,
    )

    parent_phone_number = models.CharField(
        max_length=15,
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

    created_at = jmodels.jDateTimeField(auto_now_add=True)  # Changed to Jalali

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

    def get_recent_transactions(self, days: int = 30):
        """Return transactions from the last N days"""
        since_date = date.today() - timedelta(days=days)

        return self.transactions.filter(  # type: ignore[attr-defined]
            payment_date__gte=since_date
        ).order_by("-payment_date")

    def has_paid_this_month(self) -> bool:
        """Check whether resident has paid this month's rent"""
        today = date.today()

        return self.transactions.filter(  # type: ignore[attr-defined]
            transaction_type="RENT",
            payment_date__year=today.year,
            payment_date__month=today.month,
        ).exists()



