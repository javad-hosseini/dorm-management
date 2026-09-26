import datetime
from typing import Optional
from django.core.validators import MinValueValidator
from django.db import models
from django_jalali.db import models as jmodels
import jdatetime
from .dormitory import get_default_dormitory


class Room(models.Model):
    """Represents a room within a dormitory"""
    dormitory = models.ForeignKey(
        'dormitory.Dormitory',
        on_delete=models.CASCADE,
        related_name='rooms',
        default=get_default_dormitory,
    )
    room_number = models.IntegerField()
    capacity = models.SmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Maximum number of residents allowed"
    )
    # ذخیره به ریال - کاربر به تومان وارد می‌کنه
    monthly_rent = models.PositiveBigIntegerField(
        default=0,
        help_text="Monthly rent in Rials (automatically converted from Tomans)"
    )

    class Meta:
        verbose_name = "Room"
        verbose_name_plural = "Rooms"
        unique_together = [['dormitory', 'room_number']]
        ordering = ['dormitory', 'room_number']

    def __str__(self):
        return f"{self.dormitory.name} - Room {self.room_number}"

    @property
    def monthly_rent_tomans(self):
        """Show rent in Tomans"""
        return self.monthly_rent / 10

    @property
    def current_occupants(self) -> int:
        """Returns count of current active residents"""
        return self.residents.filter(
            exit_date__isnull=True
        ).count()

    @property
    def available_capacity(self) -> int:
        """How many more residents can be added"""
        return max(0, self.capacity - self.current_occupants)

    @property
    def is_full(self) -> bool:
        """Check if room is at full capacity"""
        return self.current_occupants >= self.capacity

    @property
    def is_empty(self) -> bool:
        """Check if room has no residents"""
        return self.current_occupants == 0

    def get_current_residents(self):
        """Get list of current active residents"""
        return self.residents.filter(
            exit_date__isnull=True
        )

    def get_current_rate(self):
        """Get the current monthly rent in Rials"""
        return self.monthly_rent

    def get_rent_for_date(self, target_date: Optional[jdatetime.date] = None) -> int:
        """
        Returns the monthly rent in Rials in effect on the specified Jalali date.
        If target_date is None, defaults to today.
        Searches price_history for the latest record where effective_date <= target_date.
        If none found, falls back to the earliest recorded price or self.monthly_rent.
        """
        if target_date is None:
            target_date = jdatetime.date.today()
        elif isinstance(target_date, datetime.date) and not isinstance(target_date, jdatetime.date):
            target_date = jdatetime.date.fromgregorian(date=target_date)

        # Look for the latest price history where effective_date <= target_date
        history = self.price_history.filter(effective_date__lte=target_date).order_by('-effective_date', '-id').first()
        if history:
            return history.monthly_rent

        # If target_date is before all recorded price histories, check the earliest recorded
        earliest = self.price_history.order_by('effective_date', 'id').first()
        if earliest and target_date < earliest.effective_date:
            return earliest.monthly_rent

        return self.monthly_rent

    def get_rent_tomans_for_date(self, target_date: Optional[jdatetime.date] = None) -> int:
        """Returns the monthly rent in Tomans in effect on the specified Jalali date"""
        return self.get_rent_for_date(target_date) // 10

    @property
    def latest_price_history(self) -> Optional['RoomPriceHistory']:
        """Returns the most recent price history record"""
        return self.price_history.first()

    def set_rent(
        self,
        new_rent_rials: int,
        effective_date: Optional[jdatetime.date] = None,
        note: str = "",
        supervisor=None
    ) -> 'RoomPriceHistory':
        """
        Safely update room rent with effective date tracking.
        Preserves past rent rates in price_history so previous calculations are not altered.
        """
        if effective_date is None:
            effective_date = jdatetime.date.today()
        elif isinstance(effective_date, datetime.date) and not isinstance(effective_date, jdatetime.date):
            effective_date = jdatetime.date.fromgregorian(date=effective_date)

        # If no previous price history exists for this room, record baseline history
        if not self.price_history.exists():
            initial_date = jdatetime.date(1400, 1, 1)
            RoomPriceHistory.objects.create(
                room=self,
                monthly_rent=self.monthly_rent,
                effective_date=min(initial_date, effective_date),
                note="نرخ پایه اولیه ثبت‌شده اتاق",
                created_by=supervisor
            )

        # Create or update history record for the effective_date
        history, _ = RoomPriceHistory.objects.update_or_create(
            room=self,
            effective_date=effective_date,
            defaults={
                'monthly_rent': new_rent_rials,
                'note': note or "تغییر نرخ ماهانه اتاق",
                'created_by': supervisor
            }
        )

        # If effective_date is today or in the past, update active monthly_rent field
        today = jdatetime.date.today()
        if effective_date <= today:
            self.monthly_rent = new_rent_rials
            self.save(update_fields=['monthly_rent'])

        return history

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_rent = None
        if not is_new:
            orig = Room.objects.filter(pk=self.pk).values('monthly_rent').first()
            if orig:
                old_rent = orig['monthly_rent']

        super().save(*args, **kwargs)

        # On initial creation, record baseline history
        if is_new and self.monthly_rent:
            eff_date = getattr(self, '_price_change_effective_date', None) or jdatetime.date(1400, 1, 1)
            RoomPriceHistory.objects.get_or_create(
                room=self,
                effective_date=eff_date,
                defaults={
                    'monthly_rent': self.monthly_rent,
                    'note': getattr(self, '_price_change_note', '') or 'نرخ اولیه زمان ساخت اتاق'
                }
            )
        elif old_rent is not None and old_rent != self.monthly_rent:
            # If monthly_rent was directly changed without set_rent
            eff_date = getattr(self, '_price_change_effective_date', None) or jdatetime.date.today()
            note = getattr(self, '_price_change_note', '') or 'تغییر نرخ اتاق'
            if not self.price_history.exists():
                RoomPriceHistory.objects.create(
                    room=self,
                    monthly_rent=old_rent,
                    effective_date=jdatetime.date(1400, 1, 1),
                    note="نرخ اولیه پیشین"
                )
            RoomPriceHistory.objects.update_or_create(
                room=self,
                effective_date=eff_date,
                defaults={
                    'monthly_rent': self.monthly_rent,
                    'note': note
                }
            )


class RoomPriceHistory(models.Model):
    """
    Maintains historical record of room monthly rent rates and their effective dates.
    Ensures that past calculations (reports, previous debt, historical receipts)
    retain the rent rate that was active at that time, and future calculations
    adopt the new rate from the effective date forward.
    """
    room = models.ForeignKey(
        'dormitory.Room',
        on_delete=models.CASCADE,
        related_name='price_history',
        verbose_name="اتاق"
    )
    monthly_rent = models.PositiveBigIntegerField(
        verbose_name="اجاره ماهانه (ریال)",
        help_text="مبلغ اجاره به ریال"
    )
    effective_date = jmodels.jDateField(
        verbose_name="تاریخ شروع اعمال نرخ",
        help_text="تاریخی که این نرخ از آن تاریخ به بعد اعمال می‌شود"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ثبت تغییر"
    )
    created_by = models.ForeignKey(
        'accounts.Supervisor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="ثبت‌کننده"
    )
    note = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="توضیحات",
        help_text="علت تغییر نرخ (مثلاً افزایش قیمت پاییز ۱۴۰۵)"
    )

    class Meta:
        verbose_name = "تاریخچه نرخ اتاق"
        verbose_name_plural = "تاریخچه نرخ‌های اتاق"
        ordering = ['-effective_date', '-id']
        unique_together = [['room', 'effective_date']]

    def __str__(self):
        return f"{self.room} - {self.monthly_rent // 10:,} تومان از {self.effective_date}"

    @property
    def monthly_rent_tomans(self) -> int:
        return self.monthly_rent // 10

