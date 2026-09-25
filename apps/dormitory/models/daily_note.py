from django.db import models
from django_jalali.db import models as jmodels
import datetime
import jdatetime


def get_yesterday_jalali():
    return jdatetime.date.today() - datetime.timedelta(days=1)


class DailyNote(models.Model):
    """Daily log, maintenance request, or administrative note recorded by supervisor"""

    class NoteType(models.TextChoices):
        MAINTENANCE = 'MAINTENANCE', 'تعمیرات و تاسیسات'
        DISCIPLINARY = 'DISCIPLINARY', 'انضباطی'
        CLEANING = 'CLEANING', 'نظافت'
        GENERAL = 'GENERAL', 'عمومی و اداری'

    dormitory = models.ForeignKey(
        'dormitory.Dormitory',
        on_delete=models.CASCADE,
        related_name='daily_notes'
    )
    date = jmodels.jDateField(
        default=get_yesterday_jalali,
        help_text="تاریخ ثبت یادداشت"
    )
    title = models.CharField(
        max_length=255,
        help_text="عنوان یادداشت یا مشکل"
    )
    content = models.TextField(
        help_text="شرح کامل گزارش یا یادداشت"
    )
    note_type = models.CharField(
        max_length=20,
        choices=NoteType.choices,
        default=NoteType.GENERAL
    )
    room = models.ForeignKey(
        'dormitory.Room',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='daily_notes'
    )
    resident = models.ForeignKey(
        'dormitory.Resident',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='daily_notes'
    )
    is_resolved = models.BooleanField(
        default=False,
        help_text="آیا موضوع رسیدگی و برطرف شده است؟"
    )
    created_by = models.ForeignKey(
        'accounts.Supervisor',
        on_delete=models.PROTECT,
        related_name='daily_notes'
    )
    created_at = jmodels.jDateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Daily Note"
        verbose_name_plural = "Daily Notes"
        ordering = ['-date', '-created_at']

    def __str__(self):
        status = "✅" if self.is_resolved else "⏳"
        room_info = f" (اتاق {self.room.room_number})" if self.room else ""
        return f"{status} [{self.get_note_type_display()}] {self.title}{room_info}"
