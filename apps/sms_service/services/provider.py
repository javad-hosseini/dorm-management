"""
Provider abstraction and MeliPayamak Simple SMS REST implementation.

Handles secure communication with the MeliPayamak Console SMS API without leaking
the API token into logs, exceptions, or templates.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import logging
import uuid
import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

# Standard MeliPayamak error code descriptions
MELIPAYAMAK_ERROR_MESSAGES = {
    "0": "نام کاربری، رمز عبور یا توکن سامانه پیامک اشتباه است.",
    "2": "اعتبار پنل پیامکی کافی نمی‌باشد.",
    "3": "محدودیت در تعداد ارسال روزانه.",
    "4": "محدودیت در حجم ارسال.",
    "5": "شماره فرستنده معتبر نمی‌باشد یا به پنل تعلق ندارد.",
    "6": "سامانه پیامک در حال بروزرسانی می‌باشد.",
    "7": "متن پیامک حاوی کلمات فیلتر شده می‌باشد.",
    "9": "ارسال از خطوط عمومی از طریق وب‌سرویس امکان‌پذیر نمی‌باشد.",
    "10": "حساب کاربری در سامانه پیامک فعال نمی‌باشد.",
    "11": "پیامک ارسال نشد.",
    "12": "مدارک هویتی در سامانه پیامک تایید نشده است.",
    "14": "متن پیامک حاوی لینک غیرمجاز می‌باشد.",
    "15": "ارسال گروهی بدون درج گزینه لغو امکان‌پذیر نیست.",
    "16": "شماره گیرنده‌ای یافت نشد.",
    "17": "متن پیامک خالی می‌باشد.",
    "18": "شماره گیرنده نامعتبر است.",
    "21": "فیلتر یا مسدود بودن محتوا یا شماره در سامانه پیامک.",
    "22": "شماره در لیست سیاه اپراتور قرار دارد (دریافت پیامک‌های تبلیغاتی توسط مخاطب مسدود شده است).",
    "35": "شماره در لیست سیاه اپراتور قرار دارد (عدم دریافت پیامک تبلیغاتی).",
    "لیست سیاه": "شماره در لیست سیاه اپراتور است (دریافت پیامک‌های تبلیغاتی توسط مخاطب مسدود شده است).",
    "بلک لیست": "شماره در لیست سیاه اپراتور است (دریافت پیامک‌های تبلیغاتی توسط مخاطب مسدود شده است).",
    "بلک‌لیست": "شماره در لیست سیاه اپراتور است (دریافت پیامک‌های تبلیغاتی توسط مخاطب مسدود شده است).",
    "عدم دریافت پیامک تبلیغاتی": "مخاطب دریافت پیامک‌های تبلیغاتی را مسدود کرده است (خطوط ۵۰۰۰ تحویل نمی‌شود).",
    "ارسال نشده": "عدم ارسال از سمت سامانه ملی‌پیامک (دلایل اصلی: ۱- ناکافی بودن موجودی اعتبار پنل ۲- مسدود بودن پیامک‌های تبلیغاتی توسط گیرنده/لیست سیاه روی خط ۵۰۰۰ ۳- نیاز به تایید مدارک در پنل).",
    "شماره فرستنده معتبر نیست": "شماره فرستنده در پنل ملی‌پیامک معتبر نیست یا به این پنل تعلق ندارد.",
    "متن پیامک خالی می باشد": "متن پیامک خالی است.",
    "-108": "آدرس IP به دلیل تلاش‌های ناموفق مکرر مسدود شده است.",
    "-109": "الزام به تنظیم آدرس IP مجاز در پنل ملی‌پیامک.",
    "-110": "الزام به استفاده از کلید API (ApiKey) به جای رمز عبور.",
}


def is_blacklist_indication(code: str = "", status: str = "", message: str = "", raw: str = "") -> bool:
    """
    Detect whether a gateway error response indicates that the recipient has
    blocked advertising SMS (blacklisted at telecom operator level).
    """
    clean_code = str(code).strip()
    if clean_code in ("21", "22", "35"):
        return True
    haystack = f"{clean_code} {status} {message} {raw}".lower()
    blacklist_keywords = [
        "لیست سیاه",
        "بلک لیست",
        "بلک‌لیست",
        "blacklist",
        "black_list",
        "مسدود توسط گیرنده",
        "عدم دریافت پیامک تبلیغاتی",
        "تبلیغاتی مسدود",
    ]
    return any(kw in haystack for kw in blacklist_keywords)


@dataclass
class ProviderResult:
    success: bool
    rec_id: str = ""
    error_code: str = ""
    error_message: str = ""
    raw_response: str = ""
    is_blacklist: bool = False


class BaseSmsProvider(ABC):
    """Abstract SMS gateway provider interface."""

    @abstractmethod
    def send_simple_sms(
        self,
        recipients: list[str],
        text: str,
        is_flash: bool = False,
    ) -> ProviderResult:
        """
        Send an arbitrary SMS to one or multiple recipients.

        Args:
            recipients: List of normalized 11-digit phone numbers.
            text: SMS body text.
            is_flash: Whether to send as flash SMS.

        Returns:
            ProviderResult: Result structure indicating success or failure.
        """
        pass

    def send_pattern_sms(
        self,
        to: str,
        body_id: int,
        args: list[str],
    ) -> ProviderResult:
        """
        Extensible hook for future Pattern SMS (SendByBaseNumber).
        """
        raise NotImplementedError("ارسال پیامک پترن هنوز در این نسخه فعال نشده است.")

    def get_credit(self) -> dict:
        """Query account credit balance."""
        return {"success": False, "amount_rials": 0, "amount_tomans": 0, "status": "پشتیبانی نمی‌شود"}


class MeliPayamakRestProvider(BaseSmsProvider):
    """
    Direct HTTP/REST client for MeliPayamak Simple SMS Console API using requests.
    Endpoint: https://console.melipayamak.com/api/send/simple/{api_token}
    Payload (JSON):
        {
            "from": MELIPAYAMAK_SENDER,
            "to": recipient_phone,
            "text": message
        }
    Response (JSON):
        {
            "recId": 3741437414,
            "status": "..."
        }
    """

    def __init__(
        self,
        api_token: str | None = None,
        from_number: str | None = None,
        base_url: str | None = None,
        timeout: int = 15,
    ):
        if api_token is None:
            api_token = getattr(settings, "MELIPAYAMAK_API_TOKEN", "")
        self.api_token = str(api_token).strip()

        if from_number is None:
            from_number = getattr(settings, "MELIPAYAMAK_SENDER", "")
        self.from_number = str(from_number).strip()

        if base_url is None:
            base_url = getattr(
                settings,
                "MELIPAYAMAK_API_BASE_URL",
                "https://console.melipayamak.com/api/send/simple",
            )
        self.base_url = str(base_url).strip()
        self.timeout = timeout

        if not self.api_token or not self.from_number:
            raise ImproperlyConfigured(
                "تنظیمات وب‌سرویس ملی‌پیامک (توکن API و شماره خط فرستنده) در فایل تنظیمات تعریف نشده است."
            )

    def _get_endpoint_url(self) -> str:
        base = self.base_url.rstrip("/")
        if self.api_token and not base.endswith(self.api_token):
            return f"{base}/{self.api_token}"
        return base

    def _sanitize(self, text: str) -> str:
        """Remove the API token from any string before logging or storing in responses."""
        if not text:
            return ""
        if self.api_token:
            return text.replace(self.api_token, "***")
        return text

    def send_simple_sms(
        self,
        recipients: list[str],
        text: str,
        is_flash: bool = False,
    ) -> ProviderResult:
        if not recipients:
            return ProviderResult(
                success=False,
                error_code="EMPTY_RECIPIENTS",
                error_message="لیست گیرندگان خالی است.",
            )

        if not text or not text.strip():
            return ProviderResult(
                success=False,
                error_code="EMPTY_TEXT",
                error_message="متن پیامک نمی‌تواند خالی باشد.",
            )

        # Single recipient: direct send
        if len(recipients) == 1:
            return self._send_single_request(recipients[0], text)

        # Multiple recipients: iterate through list
        rec_ids: list[str] = []
        last_result: ProviderResult | None = None
        for phone in recipients:
            res = self._send_single_request(phone, text)
            if res.success:
                rec_ids.append(res.rec_id)
            last_result = res

        if len(rec_ids) == len(recipients):
            return ProviderResult(
                success=True,
                rec_id=",".join(rec_ids),
                error_code=last_result.error_code if last_result else "",
                raw_response=last_result.raw_response if last_result else "",
            )
        elif rec_ids:
            return ProviderResult(
                success=False,
                rec_id=",".join(rec_ids),
                error_code="PARTIAL_SUCCESS",
                error_message=f"ارسال به {len(rec_ids)} از {len(recipients)} گیرنده انجام شد.",
                raw_response=last_result.raw_response if last_result else "",
            )
        else:
            return last_result or ProviderResult(
                success=False,
                error_code="ALL_FAILED",
                error_message="ارسال به تمامی گیرندگان با خطا مواجه شد.",
            )

    def _send_single_request(self, recipient_phone: str, message: str) -> ProviderResult:
        url = self._get_endpoint_url()
        payload = {
            "from": self.from_number,
            "to": recipient_phone,
            "text": message,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            raw_text = self._sanitize(response.text.strip())

            # Parse JSON response
            try:
                data = response.json()
            except (ValueError, json.JSONDecodeError):
                data = None

            # Handle HTTP errors (4xx / 5xx)
            if response.status_code >= 400:
                err_msg = ""
                err_code = f"HTTP_{response.status_code}"
                if isinstance(data, dict):
                    err_msg = str(
                        data.get("message")
                        or data.get("error")
                        or data.get("status")
                        or ""
                    ).strip()
                if not err_msg:
                    if response.status_code == 401:
                        err_msg = "توکن وب‌سرویس ملی‌پیامک نامعتبر یا منقضی شده است."
                    elif response.status_code == 400:
                        err_msg = "درخواست ارسال پیامک نامعتبر است."
                    elif response.status_code == 403:
                        err_msg = "دسترسی به درگاه ارسال پیامک مجاز نمی‌باشد."
                    else:
                        err_msg = f"خطای سرور پیامک (کد HTTP: {response.status_code})"

                logger.error("MeliPayamak HTTP %d error: %s", response.status_code, self._sanitize(err_msg))
                return ProviderResult(
                    success=False,
                    error_code=err_code,
                    error_message=err_msg,
                    raw_response=raw_text,
                )

            # HTTP 200: Parse provider response
            if isinstance(data, dict):
                rec_id = data.get("recId")
                status = str(data.get("status", "") or "").strip()

                is_success = False
                rec_id_str = ""
                if rec_id is not None:
                    try:
                        rec_id_num = int(rec_id)
                        # recId > 15 is standard valid message ID in MeliPayamak
                        if rec_id_num > 15:
                            is_success = True
                            rec_id_str = str(rec_id_num)
                        elif rec_id_num == 1:
                            is_success = True
                            rec_id_str = "OK"
                    except (ValueError, TypeError):
                        if str(rec_id).strip():
                            is_success = True
                            rec_id_str = str(rec_id).strip()

                if is_success:
                    return ProviderResult(
                        success=True,
                        rec_id=rec_id_str,
                        error_code=status[:50],
                        raw_response=raw_text,
                    )
                else:
                    err_code = status or str(rec_id or "ERROR")
                    err_desc = MELIPAYAMAK_ERROR_MESSAGES.get(
                        err_code,
                        str(data.get("message") or status or f"خطا در ارسال پیامک (کد: {err_code})"),
                    )
                    is_bl = is_blacklist_indication(err_code, status, err_desc, raw_text)
                    if is_bl:
                        err_code = "BLACKLIST"
                        err_desc = "⛔ لیست سیاه مخابرات: دریافت پیامک تبلیغاتی توسط مخاطب مسدود شده است (خط ۵۰۰۰)."
                    return ProviderResult(
                        success=False,
                        rec_id=str(rec_id or ""),
                        error_code=err_code[:50],
                        error_message=err_desc,
                        raw_response=raw_text,
                        is_blacklist=is_bl,
                    )

            # Fallback for non-JSON text response
            return self._parse_fallback_response(raw_text)

        except requests.exceptions.Timeout:
            logger.error("Timeout connecting to MeliPayamak gateway.")
            return ProviderResult(
                success=False,
                error_code="TIMEOUT",
                error_message="مهلت زمانی ارتباط با درگاه ملی‌پیامک به پایان رسید.",
            )
        except requests.exceptions.ConnectionError:
            logger.error("Connection error connecting to MeliPayamak gateway.")
            return ProviderResult(
                success=False,
                error_code="CONNECTION_ERROR",
                error_message="خطای اتصال به سرور ملی‌پیامک رخ داد. لطفاً ارتباط اینترنت سرور را بررسی کنید.",
            )
        except requests.exceptions.RequestException as e:
            logger.error("HTTP error connecting to MeliPayamak: %s", type(e).__name__)
            return ProviderResult(
                success=False,
                error_code="HTTP_ERROR",
                error_message="خطای شبکه در ارتباط با سرور پیامک رخ داد.",
            )
        except Exception:
            logger.exception("Unexpected error in MeliPayamakRestProvider")
            return ProviderResult(
                success=False,
                error_code="INTERNAL_ERROR",
                error_message="خطای سیستمی در ارسال پیامک رخ داد.",
            )

    def _parse_fallback_response(self, raw_text: str) -> ProviderResult:
        """Parses fallback plain text responses if provider ever returns non-JSON."""
        value_str = raw_text.strip().strip('"').strip("'")
        try:
            code_num = int(float(value_str))
            if code_num > 15:
                return ProviderResult(
                    success=True,
                    rec_id=str(code_num),
                    raw_response=raw_text,
                )
            elif code_num == 1:
                return ProviderResult(
                    success=True,
                    rec_id="OK",
                    raw_response=raw_text,
                )
            else:
                err_desc = MELIPAYAMAK_ERROR_MESSAGES.get(
                    str(code_num),
                    f"خطای ناشناخته از درگاه پیامک (کد: {code_num})",
                )
                is_bl = is_blacklist_indication(str(code_num), "", err_desc, raw_text)
                err_code = "BLACKLIST" if is_bl else str(code_num)
                if is_bl:
                    err_desc = "⛔ لیست سیاه مخابرات: دریافت پیامک تبلیغاتی توسط مخاطب مسدود شده است (خط ۵۰۰۰)."
                return ProviderResult(
                    success=False,
                    error_code=err_code,
                    error_message=err_desc,
                    raw_response=raw_text,
                    is_blacklist=is_bl,
                )
        except (ValueError, TypeError):
            if "ok" in value_str.lower() or "success" in value_str.lower():
                return ProviderResult(
                    success=True,
                    rec_id=value_str,
                    raw_response=raw_text,
                )
            is_bl = is_blacklist_indication("", value_str, value_str, raw_text)
            err_code = "BLACKLIST" if is_bl else "INVALID_RESPONSE"
            err_msg = (
                "⛔ لیست سیاه مخابرات: دریافت پیامک تبلیغاتی توسط مخاطب مسدود شده است (خط ۵۰۰۰)."
                if is_bl
                else f"پاسخ ناشناخته از درگاه ملی‌پیامک: {value_str[:100]}"
            )
            return ProviderResult(
                success=False,
                error_code=err_code,
                error_message=err_msg,
                raw_response=raw_text,
                is_blacklist=is_bl,
            )

    def get_credit(self) -> dict:
        """
        Query current credit from MeliPayamak Console.
        Returns dict with amount_rials, amount_tomans, and status.
        """
        try:
            url = f"https://console.melipayamak.com/api/receive/credit/{self.api_token}"
            response = requests.get(url, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                amount_rials = float(data.get("amount", 0))
                amount_tomans = int(round(amount_rials / 10))
                return {
                    "success": True,
                    "amount_rials": amount_rials,
                    "amount_tomans": amount_tomans,
                    "status": data.get("status", "موفق"),
                }
        except Exception as e:
            logger.warning("Failed to query MeliPayamak credit: %s", e)
        return {"success": False, "amount_rials": 0, "amount_tomans": 0, "status": "خطا در استعلام"}


class ConsoleSmsProvider(BaseSmsProvider):
    """
    Mock SMS provider that logs outgoing SMS to console/logger without contacting external APIs.
    Used for local development and testing to prevent external network side effects and billing.
    """

    def send_simple_sms(
        self,
        recipients: list[str],
        text: str,
        is_flash: bool = False,
    ) -> ProviderResult:
        mock_rec_id = f"MOCK-{uuid.uuid4().hex[:8].upper()}"
        logger.info(
            "[CONSOLE SMS] Sent to %d recipient(s): %s | RecId: %s | Text: %s",
            len(recipients),
            recipients[:5] if len(recipients) > 5 else recipients,
            mock_rec_id,
            text[:100] + ("..." if len(text) > 100 else ""),
        )
        return ProviderResult(
            success=True,
            rec_id=mock_rec_id,
            raw_response=f"Console mock send to {len(recipients)} numbers",
        )

    def get_credit(self) -> dict:
        return {"success": True, "amount_rials": 10000000, "amount_tomans": 1000000, "status": "حالت آزمایشی (کنسول)"}



def get_sms_provider() -> BaseSmsProvider:
    """
    Factory function to obtain the active SMS provider instance.
    Falls back to ConsoleSmsProvider if SMS_CONSOLE_MODE is True or credentials are empty.
    """
    is_console = getattr(settings, "SMS_CONSOLE_MODE", False)
    api_token = getattr(settings, "MELIPAYAMAK_API_TOKEN", "")
    sender = getattr(settings, "MELIPAYAMAK_SENDER", "")

    if is_console or not (api_token and sender):
        if not is_console:
            logger.warning(
                "MeliPayamak credentials (API token and sender) are not fully configured. Falling back to ConsoleSmsProvider."
            )
        return ConsoleSmsProvider()

    return MeliPayamakRestProvider()
