from datetime import timedelta
import jdatetime
from typing import List, Dict, Any, Optional

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.contrib.auth.models import User
from django_jalali.db import models as jmodels

from apps.dormitory.jalali_utils import (
    add_jalali_months,
    format_period_name,
    calculate_unpaid_periods,
)
from .dormitory import get_default_dormitory


class Resident(models.Model):
    """Represents a person living in the dormitory"""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        LEFT = "LEFT", "Left"

    # Personal information
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    father_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="نام پدر",
        help_text="نام پدر ساکن. در صورت عدم دسترسی، خالی بگذارید (جزو کسری مدارک محسوب می‌شود).",
    )

    is_foreign = models.BooleanField(
        default=False,
        verbose_name="تبعه خارجی (اتباع)",
        help_text="در صورت علامت زدن، فیلد شناسه به عنوان شماره پاسپورت یا کد فراگیر اتباع ثبت می‌شود.",
    )

    national_code = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        verbose_name="کد ملی / شماره پاسپورت",
        help_text="کد ملی ۱۰ رقمی (ایرانی) یا شماره پاسپورت / کد فراگیر (اتباع). در صورت عدم دسترسی، خالی بگذارید.",
    )

    phone_number = models.CharField(
        max_length=11,
        unique=True,
        verbose_name="شماره تماس ساکن",
    )

    parent_phone_number = models.CharField(
        max_length=11,
        blank=True,
        null=True,
        verbose_name="شماره تماس والدین",
        help_text="شماره تماس والدین یا بستگان درجه یک. در صورت عدم دسترسی، خالی یا 'ندارد' بگذارید.",
    )

    # Django User Account link for Student Portal
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resident_profile",
        verbose_name="حساب کاربری سامانه",
        help_text="حساب کاربری متصل به این ساکن برای ورود به پنل دانشجو.",
    )

    # Documents & Deposit status
    has_deposit = models.BooleanField(
        default=False,
        verbose_name="ودیعه دارد",
        help_text="مشخص می‌کند که آیا ودیعه از ساکن دریافت شده است یا خیر.",
    )

    has_lease = models.BooleanField(
        default=False,
        verbose_name="اجاره‌نامه دارد",
        help_text="مشخص می‌کند که آیا اجاره‌نامه رسمی با ساکن منعقد/تحویل شده است یا خیر.",
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
        default=get_default_dormitory,
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
        help_text="این فیلد با ثبت تراکنش‌های اجاره به طور خودکار به صورت روزشمار جلو می‌رود. در موارد استثنایی می‌توانید آن را به صورت دستی نیز تغییر دهید."
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
        verbose_name="تصویر مدارک شناسایی (۱)",
        help_text="تصویر روی کارت ملی یا صفحه اول پاسپورت (فشرده‌سازی خودکار تا زیر ۱ مگابایت).",
    )

    id_card_image_2 = models.ImageField(
        upload_to="id_cards/",
        null=True,
        blank=True,
        verbose_name="تصویر مدارک شناسایی (۲)",
        help_text="تصویر پشت کارت ملی یا صفحه دوم پاسپورت (اختیاری - فشرده‌سازی خودکار).",
    )

    id_card_image_3 = models.ImageField(
        upload_to="id_cards/",
        null=True,
        blank=True,
        verbose_name="تصویر مدارک شناسایی (۳)",
        help_text="تصویر شناسنامه یا سایر مدارک هویتی (اختیاری - فشرده‌سازی خودکار).",
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
    # PROFILE COMPLETION & MISSING DOCUMENTS (کسری مدارک و اطلاعات)
    # ========================================================

    @property
    def identity_title(self) -> str:
        """Label describing identification code type"""
        return "شماره پاسپورت / کد فراگیر" if self.is_foreign else "کد ملی"

    @property
    def identity_display(self) -> str:
        """Formatted identification string"""
        if not self.national_code:
            return "⚠️ ثبت‌نشده"
        if self.is_foreign:
            return f"{self.national_code} (اتباع)"
        return self.national_code

    @property
    def has_id_card_image(self) -> bool:
        """Check if at least one identity document photo is uploaded"""
        return bool(self.id_card_image or self.id_card_image_2 or self.id_card_image_3)

    @property
    def uploaded_id_images_count(self) -> int:
        """Return count of uploaded identity document photos (max 3)"""
        return sum([bool(self.id_card_image), bool(self.id_card_image_2), bool(self.id_card_image_3)])

    @property
    def id_cards_images_list(self) -> List[Any]:
        """Return list of valid uploaded image fields"""
        imgs = []
        if self.id_card_image:
            imgs.append(self.id_card_image)
        if self.id_card_image_2:
            imgs.append(self.id_card_image_2)
        if self.id_card_image_3:
            imgs.append(self.id_card_image_3)
        return imgs

    @property
    def has_incomplete_profile(self) -> bool:
        """Check if resident has missing national code, father name, parent phone number, lease contract, or ID card image"""
        return (
            not bool(self.national_code)
            or not bool(self.father_name)
            or not bool(self.parent_phone_number)
            or not self.has_lease
            or not self.has_id_card_image
        )

    @property
    def missing_profile_fields(self) -> List[str]:
        """Return list of missing field names in Persian"""
        missing = []
        if not self.national_code:
            missing.append("شماره پاسپورت یا کد فراگیر" if self.is_foreign else "کد ملی")
        if not self.father_name:
            missing.append("نام پدر")
        if not self.parent_phone_number:
            missing.append("شماره تماس والدین")
        if not self.has_lease:
            missing.append("اجاره‌نامه")
        if not self.has_id_card_image:
            missing.append("عکس مدرک شناسایی")
        return missing

    @property
    def profile_completion_status(self) -> str:
        """Return code indicating which documents are missing"""
        missing_code = not bool(self.national_code)
        missing_father = not bool(self.father_name)
        missing_parent = not bool(self.parent_phone_number)
        missing_lease = not self.has_lease
        missing_image = not self.has_id_card_image

        if not any([missing_code, missing_father, missing_parent, missing_lease, missing_image]):
            return "COMPLETE"
        
        missing_count = sum([missing_code, missing_father, missing_parent, missing_lease, missing_image])
        if missing_count == 5:
            return "MISSING_ALL"
        
        if missing_count == 1:
            if missing_code:
                return "MISSING_PASSPORT" if self.is_foreign else "MISSING_NATIONAL_CODE"
            if missing_father:
                return "MISSING_FATHER_NAME"
            if missing_parent:
                return "MISSING_PARENT_PHONE"
            if missing_lease:
                return "MISSING_LEASE"
            if missing_image:
                return "MISSING_ID_IMAGE"

        if missing_code and missing_parent and not missing_father and not missing_lease and not missing_image:
            return "MISSING_BOTH"

        return "INCOMPLETE"

    # ========================================================
    # PROFILE EXPORT & COPY FORMATTING (خروجی و کپی مشخصات بدون مالی)
    # ========================================================

    def get_export_dict(self) -> dict:
        """Return comprehensive non-financial profile dictionary"""
        room_num = str(self.room.room_number) if self.room else "تعیین‌نشده"
        rent_tomans = f"{self.current_monthly_rent_tomans:,}" if self.room and self.room.monthly_rent else "نامشخص"
        dorm_name = self.dormitory.name if self.dormitory else "نامشخص"
        nat_code = self.national_code or "⚠️ ثبت‌نشده"
        if self.is_foreign and self.national_code:
            nat_code = f"{self.national_code} (اتباع / گذرنامه)"
        parent_phone = self.parent_phone_number or "⚠️ ثبت‌نشده"
        occ_map = {"STUDENT": "دانشجو", "EMPLOYED": "شاغل", "OTHER": "سایر"}
        occ_text = occ_map.get(self.occupation, self.occupation or "سایر")
        status_text = "فعال" if self.status == self.Status.ACTIVE else "خارج شده"
        settled_text = str(self.settled_until) if self.settled_until else "ثبت نشده"
        entry_text = str(self.entry_date) if self.entry_date else "نامشخص"

        return {
            "full_name": self.full_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "father_name": self.father_name or "⚠️ ثبت‌نشده",
            "is_foreign": self.is_foreign,
            "identity_title": self.identity_title,
            "national_code": nat_code,
            "phone_number": self.phone_number,
            "parent_phone_number": parent_phone,
            "occupation": occ_text,
            "dormitory": dorm_name,
            "room_number": room_num,
            "monthly_rent_tomans": rent_tomans,
            "entry_date": entry_text,
            "monthly_payment_day": f"{self.monthly_payment_day or 1}ام هر ماه",
            "status": status_text,
            "settled_until": settled_text,
            "settled_until_display": self.settled_until_display,
            "next_due_date": str(self.next_due_date) if self.next_due_date else "",
            "next_due_date_display": self.next_due_date_display,
            "due_status_display": self.due_status_display,
            "debt_urgency": self.debt_urgency,
            "has_deposit": self.has_deposit,
            "has_lease": self.has_lease,
            "deposit_status": "دارد" if self.has_deposit else "ندارد",
            "lease_status": "دارد" if self.has_lease else "ندارد",
            "has_id_card_image": self.has_id_card_image,
            "id_images_count": self.uploaded_id_images_count,
            "id_card_status": f"{self.uploaded_id_images_count} تصویر" if self.has_id_card_image else "ندارد",
        }

    def get_export_text(self) -> str:
        """
        Return cleanly formatted Persian text for clipboard/sharing.
        Includes bio, contact, room, dates, and status (strictly excluding payment/tx history).
        """
        d = self.get_export_dict()
        id_label = "🛂 شماره پاسپورت/فراگیر (اتباع)" if self.is_foreign else "🆔 کد ملی"
        lines = [
            f"👤 نام و نام خانوادگی: {d['full_name']}",
            f"👨 نام پدر: {d['father_name']}",
            f"{id_label}: {d['national_code']}",
            f"📱 شماره تماس: {d['phone_number']}",
            f"👨‍👩‍👦 شماره والدین: {d['parent_phone_number']}",
            f"💼 شغل: {d['occupation']}",
            f"🏢 خوابگاه: {d['dormitory']}",
            f"🚪 شماره اتاق: {d['room_number']} (اجاره: {d['monthly_rent_tomans']} تومان)",
            f"📄 اجاره‌نامه: {'✅ دارد' if d.get('has_lease') else '⚠️ ندارد (کسری مدرک)'}",
            f"📸 عکس مدارک شناسایی: {d['id_card_status'] if d.get('has_id_card_image') else '⚠️ ندارد (کسری مدرک)'}",
            f"💰 ودیعه: {'✅ دارد' if d.get('has_deposit') else '❌ ندارد'}",
            f"📅 تاریخ ورود: {d['entry_date']}",
            f"🗓️ موعد پرداخت: {d['monthly_payment_day']}",
            f"📌 وضعیت اقامت: {d['status']}",
            f"⌛ تسویه تا: {d['settled_until_display']}",
            f"🗓️ سررسید موعد: {d['next_due_date_display']} ({d['due_status_display']})",
        ]
        return "\n".join(lines)

    def clean(self):
        super().clean()

        def clean_val(val, uppercase_letters=False):
            if val is None:
                return None
            val_str = str(val).strip()
            # Normalize Persian/Arabic digits
            p_to_e = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧۸۹', '01234567890123456789')
            val_str = val_str.translate(p_to_e).strip()

            # Common placeholder tokens representing missing/unknown value
            placeholders = {'', '-', '_', 'ندارد', 'null', 'none', 'فاقد', 'نامشخص', 'بدون', 'ثبت نشده', '0', '0000000000'}
            if val_str.lower() in placeholders:
                return None
            if uppercase_letters:
                return val_str.upper()
            return val_str

        self.father_name = clean_val(self.father_name)
        self.national_code = clean_val(self.national_code, uppercase_letters=bool(self.is_foreign))
        self.parent_phone_number = clean_val(self.parent_phone_number)

        if self.phone_number:
            p_to_e = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧۸۹', '01234567890123456789')
            self.phone_number = str(self.phone_number).translate(p_to_e).strip()

    def save(self, *args, **kwargs):
        # Auto-compress any newly uploaded ID card images before saving to disk
        from apps.dormitory.image_utils import compress_image
        from django.core.files.uploadedfile import UploadedFile

        for field_name in ['id_card_image', 'id_card_image_2', 'id_card_image_3']:
            field_file = getattr(self, field_name, None)
            if not field_file:
                continue
            underlying = getattr(field_file, '_file', None) or (field_file if isinstance(field_file, UploadedFile) else None)
            if underlying and isinstance(underlying, UploadedFile):
                compressed = compress_image(underlying)
                setattr(self, field_name, compressed)

        self.clean()
        super().save(*args, **kwargs)

        # Automatically link or provision User account if not yet attached
        if not self.user and (self.national_code or self.phone_number):
            try:
                self.ensure_user_account()
            except Exception:
                pass

    def ensure_user_account(self, password: Optional[str] = None) -> Optional[User]:
        """
        Ensure this resident has an associated Django User for student portal login.
        Default username is national_code (if present) or phone_number.
        Default password is raw national_code or phone_number.
        """
        raw_username = (self.national_code or self.phone_number or "").strip()
        if not raw_username:
            return None

        # If user is already linked
        if self.user:
            return self.user

        # If a User with this username already exists in database
        existing_user = User.objects.filter(username__iexact=raw_username).first()
        if existing_user:
            self.user = existing_user
            Resident.objects.filter(pk=self.pk).update(user=existing_user)
            return existing_user

        # Otherwise create a new Django user
        initial_password = password or self.national_code or self.phone_number
        new_user = User.objects.create_user(
            username=raw_username,
            password=initial_password,
            first_name=self.first_name,
            last_name=self.last_name,
        )
        self.user = new_user
        Resident.objects.filter(pk=self.pk).update(user=new_user)
        return new_user


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
    def next_due_date(self) -> Optional[jdatetime.date]:
        """
        The next payment due date (سررسید موعد بعدی).
        In the prepaid model, this is settled_until date (or entry_date if unsettled).
        """
        return self.settled_until or self.entry_date

    @property
    def next_due_date_display(self) -> str:
        """Formatted string of next due date"""
        d = self.next_due_date
        return d.strftime('%Y/%m/%d') if d else "ثبت نشده"

    @property
    def settled_until_display(self) -> str:
        """Formatted string of settled_until date"""
        return self.settled_until.strftime('%Y/%m/%d') if self.settled_until else "تسویه نشده (فاقد پرداخت)"

    @property
    def debt_urgency(self) -> str:
        """
        Urgency level of settlement / debt:
        - 'settled': no debt
        - 'warning': in debt, overdue_days <= 7 (yellow alert / 1 week grace)
        - 'danger': in debt, overdue_days > 7 (red alert / critical overdue)
        """
        if not self.is_in_debt:
            return 'settled'
        return 'warning' if self.overdue_days <= 7 else 'danger'

    @property
    def due_status_display(self) -> str:
        """
        Human readable Persian summary of settlement date and upcoming due date / overdue days.
        """
        if self.status != self.Status.ACTIVE:
            return self.get_status_display()
        if not self.room:
            return "بدون اتاق"

        due_date_str = self.next_due_date_display

        if not self.settled_until:
            if self.is_in_debt:
                if self.overdue_days == 0:
                    return f"سررسید موعد ورود امروز ({due_date_str})"
                elif self.overdue_days <= 7:
                    return f"{self.overdue_days} روز تاخیر از ورود (مهلت تا ۱ هفته - {due_date_str})"
                return f"{self.overdue_days} روز تاخیر از ورود ({due_date_str})"
            return f"ورود در آینده ({due_date_str})"

        if self.is_in_debt:
            if self.overdue_days == 0:
                return f"سررسید موعد امروز ({due_date_str})"
            elif self.overdue_days <= 7:
                return f"{self.overdue_days} روز تاخیر در پرداخت (مهلت تا ۱ هفته - سررسید: {due_date_str})"
            return f"{self.overdue_days} روز تاخیر در پرداخت (سررسید: {due_date_str})"
        else:
            days = self.days_until_due
            if days == 0:
                return f"سررسید موعد امروز ({due_date_str})"
            return f"{days} روز مانده تا سررسید ({due_date_str})"

    @property
    def unpaid_periods(self) -> List[Dict[str, Any]]:
        """
        Returns list of unpaid monthly periods up to today.
        Billing is strictly monthly (not daily pro-rated).
        Each period dynamically calculates its rent based on the room's
        historical rate in effect for that period.
        """
        start_calc = self.settled_until or self.entry_date
        if not start_calc:
            return []

        rent_rials = self.room.monthly_rent if self.room else 0
        rent_resolver = self.room.get_rent_for_date if self.room else None
        return calculate_unpaid_periods(
            start_date=start_calc,
            as_of_date=jdatetime.date.today(),
            monthly_rent_rials=rent_rials,
            rent_resolver=rent_resolver,
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
        Strictly monthly: sum of amounts of all unpaid periods based on their effective historical rates.
        """
        return sum(p["amount_tomans"] for p in self.unpaid_periods)

    @property
    def total_debt_amount_rials(self) -> int:
        """Total unpaid rent amount in Rials"""
        return sum(p["amount_rials"] for p in self.unpaid_periods)

    @property
    def last_paid_period_display(self) -> str:
        """Shows the last period covered by previous payments"""
        if not self.settled_until:
            return "پرداختی ثبت نشده"

        latest_tx = self.transactions.filter(
            transaction_type='RENT',
            is_approved=True
        ).order_by('-period_end', '-payment_date').first()
        if latest_tx and latest_tx.period_name:
            return f"{latest_tx.period_name} (تسویه تا {self.settled_until.strftime('%Y/%m/%d')})"

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
        debt = sum(p["amount_tomans"] for p in unpaid)

        if not unpaid:
            days_left = self.days_until_due
            due_str = self.settled_until.strftime('%Y/%m/%d') if self.settled_until else '-'
            return {
                "status": "SETTLED",
                "severity": "success",
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
            unpaid_names = " و ".join([p["name"] for p in unpaid])


            if overdue == 0:
                return {
                    "status": "DUE_TODAY",
                    "severity": "warning",
                    "label": "سررسید امروز",
                    "color": "#f39c12",
                    "overdue_days": 0,
                    "days_until_due": 0,
                    "unpaid_months": unpaid_names,
                    "debt_tomans": debt,
                    "details": f"موعد {unpaid[0]['name']} فرا رسیده ({debt:,.0f} تومان)",
                    "last_paid": self.last_paid_period_display,
                }
            elif overdue <= 7:
                return {
                    "status": "OVERDUE",
                    "severity": "warning",
                    "label": f"{overdue} روز تاخیر (مهلت)",
                    "color": "#f39c12",
                    "overdue_days": overdue,
                    "days_until_due": 0,
                    "unpaid_months": unpaid_names,
                    "debt_tomans": debt,
                    "details": f"{overdue} روز تاخیر (مهلت تا ۱ هفته) - بدهی: {unpaid_names} ({debt:,.0f} تومان)",
                    "last_paid": self.last_paid_period_display,
                }
            else:
                return {
                    "status": "OVERDUE",
                    "severity": "danger",
                    "label": f"{overdue} روز تاخیر (بدهکار)",
                    "color": "#e74c3c",
                    "overdue_days": overdue,
                    "days_until_due": 0,
                    "unpaid_months": unpaid_names,
                    "debt_tomans": debt,
                    "details": f"{overdue} روز تاخیر (بیش از یک هفته) - بدهی: {unpaid_names} ({debt:,.0f} تومان)",
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

    def recalculate_settled_until(self, save: bool = True) -> Optional[jdatetime.date]:
        """
        Recalculates settled_until by taking the maximum period_end from all
        approved RENT transactions of this resident.
        """
        approved_rent_txs = self.transactions.filter(
            transaction_type='RENT',
            is_approved=True
        ).exclude(period_end__isnull=True)

        if not approved_rent_txs.exists():
            self.settled_until = None
            if save:
                self.save(update_fields=['settled_until'])
            return None

        max_period_end = None
        for tx in approved_rent_txs:
            if tx.period_end:
                if max_period_end is None or tx.period_end > max_period_end:
                    max_period_end = tx.period_end

        self.settled_until = max_period_end
        if save:
            self.save(update_fields=['settled_until'])
        return self.settled_until

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
