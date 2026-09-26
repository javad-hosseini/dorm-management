from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .utils import normalize_phone_number, validate_iranian_mobile


class Contact(models.Model):
    """
    Independent contact book for recipients who are not website users.
    """

    full_name = models.CharField(
        max_length=150,
        verbose_name="نام و نام خانوادگی",
        help_text="نام و نام خانوادگی برای شناسایی در دفترچه تلفن",
    )
    phone_number = models.CharField(
        max_length=15,
        unique=True,
        validators=[validate_iranian_mobile],
        verbose_name="شماره موبایل",
        help_text="شماره موبایل معتبر ایران (مانند 09123456789)",
    )
    notes = models.TextField(
        blank=True,
        verbose_name="یادداشت",
        help_text="توضیحات اختیاری درباره این مخاطب",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="تاریخ بروزرسانی",
    )

    class Meta:
        verbose_name = "مخاطب دفترچه تلفن"
        verbose_name_plural = "دفترچه تلفن"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"

    def clean(self):
        super().clean()
        if self.phone_number:
            self.phone_number = normalize_phone_number(self.phone_number)

    def save(self, *args, **kwargs):
        if self.phone_number:
            self.phone_number = normalize_phone_number(self.phone_number)
        super().save(*args, **kwargs)


class SmsCampaign(models.Model):
    """
    Represents an SMS sending session or campaign initiated by an administrator.
    """

    class Source(models.TextChoices):
        RESIDENTS = "residents", "ساکنین خوابگاه"
        DEBTORS = "debtors", "بدهکاران خوابگاه"
        CONTACTS = "contacts", "دفترچه تلفن"
        MIXED = "mixed", "ترکیبی"
        USERS = "users", "کاربران سیستم"

    class Status(models.TextChoices):
        PENDING = "pending", "در حال پردازش"
        COMPLETED = "completed", "موفق"
        PARTIAL_FAILURE = "partial_failure", "ارسال جزئی (همراه با خطا)"
        FAILED = "failed", "ناموفق"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="ارسال‌کننده",
        related_name="sms_campaigns",
    )
    message_body = models.TextField(
        verbose_name="متن خام پیامک",
    )
    recipient_source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.RESIDENTS,
        verbose_name="منبع مخاطبین",
    )
    total_selected = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد کل انتخاب شده",
    )
    total_deduplicated = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد پس از حذف تکراری",
    )
    successful_count = models.PositiveIntegerField(
        default=0,
        verbose_name="ارسال‌های موفق",
    )
    failed_count = models.PositiveIntegerField(
        default=0,
        verbose_name="ارسال‌های ناموفق",
    )
    blocked_count = models.PositiveIntegerField(
        default=0,
        verbose_name="مسدود شده (لیست سیاه تبلیغاتی)",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="وضعیت ارسال",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ارسال",
    )

    class Meta:
        verbose_name = "کمپین ارسال پیامک"
        verbose_name_plural = "تاریخچه ارسال‌های پیامک"
        ordering = ["-created_at"]

    def __str__(self):
        return f"کمپین #{self.id} - {self.get_status_display()} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    @property
    def short_message(self):
        if len(self.message_body) > 60:
            return self.message_body[:60] + "..."
        return self.message_body


class SmsRecipientLog(models.Model):
    """
    Detailed audit log for an individual SMS message sent to a specific recipient.
    """

    class RecipientType(models.TextChoices):
        RESIDENT = "resident", "ساکن خوابگاه"
        CONTACT = "contact", "مخاطب دفترچه"
        USER = "user", "کاربر سیستم"

    class Status(models.TextChoices):
        SUCCESS = "success", "موفق"
        BLOCKED_ADVERTISING = "blocked_advertising", "مسدود توسط گیرنده (لیست سیاه تبلیغاتی)"
        FAILED = "failed", "ناموفق"
        SKIPPED_DUPLICATE = "skipped_duplicate", "حذف به دلیل شماره تکراری"
        SKIPPED_INVALID = "skipped_invalid", "شماره نامعتبر"

    campaign = models.ForeignKey(
        SmsCampaign,
        on_delete=models.CASCADE,
        related_name="recipients",
        verbose_name="کمپین پیامکی",
    )
    recipient_type = models.CharField(
        max_length=20,
        choices=RecipientType.choices,
        default=RecipientType.RESIDENT,
        verbose_name="نوع مخاطب",
    )
    resident = models.ForeignKey(
        'dormitory.Resident',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="ساکن خوابگاه",
        related_name="sms_logs",
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="مخاطب دفترچه",
        related_name="sms_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="کاربر سیستم",
        related_name="sms_logs",
    )
    phone_number = models.CharField(
        max_length=15,
        verbose_name="شماره موبایل",
    )
    final_message = models.TextField(
        verbose_name="متن نهایی ارسال‌شده",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        verbose_name="وضعیت ارسال",
    )
    provider_rec_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="شناسه رسید درگاه (recId)",
    )
    error_code = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="کد خطای درگاه",
    )
    error_message = models.TextField(
        blank=True,
        verbose_name="شرح خطای درگاه",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )

    class Meta:
        verbose_name = "گزارش پیامک گیرنده"
        verbose_name_plural = "گزارش پیامک‌های ارسالی"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.phone_number} - {self.get_status_display()}"

