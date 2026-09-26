from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q
from apps.dormitory.models import Resident

User = get_user_model()


def normalize_input_digits(value: str) -> str:
    """Convert Persian and Arabic numerals to English ASCII digits"""
    if not value:
        return ""
    p_to_e = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧۸۹', '01234567890123456789')
    return str(value).translate(p_to_e).strip()


class NationalCodeOrPhoneBackend(ModelBackend):
    """
    Custom authentication backend that allows users (especially dormitory residents)
    to log in using either their:
    1. National Code (کد ملی) / Foreign Passport ID
    2. Mobile Phone Number (شماره موبایل)
    3. Standard Django Username
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        clean_username = normalize_input_digits(username)

        # 1. First attempt: Direct Django User lookup by username
        user = User.objects.filter(username__iexact=clean_username).first()

        # 2. Second attempt: Lookup resident by national_code or phone_number
        if not user:
            resident = (
                Resident.objects.filter(
                    Q(national_code__iexact=clean_username) | Q(phone_number=clean_username)
                )
                .select_related('user')
                .first()
            )

            if resident:
                if resident.user:
                    user = resident.user
                else:
                    # Provision user account if missing
                    user = resident.ensure_user_account()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None

    def get_user(self, user_id):
        try:
            user = User.objects.get(pk=user_id)
            return user if self.user_can_authenticate(user) else None
        except User.DoesNotExist:
            return None
