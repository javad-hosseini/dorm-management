"""
Campaign management service for Dormitory Management System.

Handles resident and contact recipient resolution, phone normalization,
cross-source deduplication, dynamic template personalization, concurrent sending,
and audit logging.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import logging
from typing import Any, List, Optional

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.dormitory.models import Resident
from apps.sms_service.models import Contact, SmsCampaign, SmsRecipientLog
from apps.sms_service.utils import (
    normalize_phone_number,
    render_resident_sms_template,
    format_personalized_message,
)
from .provider import BaseSmsProvider, ProviderResult, get_sms_provider

logger = logging.getLogger(__name__)
User = get_user_model()


@dataclass
class ResolvedRecipient:
    recipient_type: str  # 'resident', 'contact', or 'user'
    id: int
    name: str
    phone_number: str
    message: str
    obj: Any
    is_valid: bool = True
    invalid_reason: str = ""
    is_duplicate: bool = False
    details: str = ""  # e.g. room number or notes


def prepare_campaign_preview(
    resident_ids: Optional[List[int]] = None,
    contact_ids: Optional[List[int]] = None,
    message_body: str = "",
    user_ids: Optional[List[int]] = None,
) -> dict[str, Any]:
    """
    Resolve recipients, render personalized template messages, perform deduplication,
    and return preview metrics without initiating any SMS sending or database writes.
    """
    resident_ids = resident_ids or []
    contact_ids = contact_ids or []
    user_ids = user_ids or []

    residents = list(Resident.objects.filter(id__in=resident_ids).select_related("room", "dormitory"))
    contacts = list(Contact.objects.filter(id__in=contact_ids))
    users = list(User.objects.filter(id__in=user_ids)) if user_ids else []

    seen_phones: dict[str, ResolvedRecipient] = {}
    valid_recipients: list[ResolvedRecipient] = []
    duplicate_recipients: list[ResolvedRecipient] = []
    invalid_recipients: list[ResolvedRecipient] = []

    # 1. Process Dormitory Residents first (Highest Precedence)
    for res in residents:
        raw_phone = res.phone_number or ""
        room_name = str(res.room.room_number) if res.room else "بدون اتاق"
        try:
            norm_phone = normalize_phone_number(raw_phone)
            personalized_msg = render_resident_sms_template(res, message_body)

            rec = ResolvedRecipient(
                recipient_type="resident",
                id=res.id,
                name=res.full_name,
                phone_number=norm_phone,
                message=personalized_msg,
                obj=res,
                details=f"اتاق {room_name}",
            )

            if norm_phone in seen_phones:
                rec.is_duplicate = True
                duplicate_recipients.append(rec)
            else:
                seen_phones[norm_phone] = rec
                valid_recipients.append(rec)
        except ValidationError as e:
            invalid_recipients.append(
                ResolvedRecipient(
                    recipient_type="resident",
                    id=res.id,
                    name=res.full_name,
                    phone_number=raw_phone,
                    message="",
                    obj=res,
                    is_valid=False,
                    invalid_reason=str(e),
                    details=f"اتاق {room_name}",
                )
            )

    # 2. Process Contact Book entries
    clean_body = message_body.strip()
    for c in contacts:
        raw_phone = c.phone_number or ""
        try:
            norm_phone = normalize_phone_number(raw_phone)
            # If template has {نام}, replace with contact's full name
            contact_msg = clean_body.replace("{نام}", c.full_name).replace("{name}", c.full_name)
            rec = ResolvedRecipient(
                recipient_type="contact",
                id=c.id,
                name=c.full_name,
                phone_number=norm_phone,
                message=contact_msg,
                obj=c,
                details="دفترچه تلفن",
            )

            if norm_phone in seen_phones:
                rec.is_duplicate = True
                duplicate_recipients.append(rec)
            else:
                seen_phones[norm_phone] = rec
                valid_recipients.append(rec)
        except ValidationError as e:
            invalid_recipients.append(
                ResolvedRecipient(
                    recipient_type="contact",
                    id=c.id,
                    name=c.full_name,
                    phone_number=raw_phone,
                    message="",
                    obj=c,
                    is_valid=False,
                    invalid_reason=str(e),
                    details="دفترچه تلفن",
                )
            )

    # 3. Process Users (if any passed)
    for u in users:
        raw_phone = getattr(u, "phone_number", "") or ""
        try:
            norm_phone = normalize_phone_number(raw_phone)
            user_msg = format_personalized_message(u, clean_body)
            full_name = u.get_full_name() or u.username
            rec = ResolvedRecipient(
                recipient_type="user",
                id=u.id,
                name=full_name,
                phone_number=norm_phone,
                message=user_msg,
                obj=u,
                details="کاربر سیستم",
            )

            if norm_phone in seen_phones:
                rec.is_duplicate = True
                duplicate_recipients.append(rec)
            else:
                seen_phones[norm_phone] = rec
                valid_recipients.append(rec)
        except ValidationError as e:
            invalid_recipients.append(
                ResolvedRecipient(
                    recipient_type="user",
                    id=u.id,
                    name=u.get_full_name() or u.username,
                    phone_number=raw_phone,
                    message="",
                    obj=u,
                    is_valid=False,
                    invalid_reason=str(e),
                    details="کاربر سیستم",
                )
            )

    sample_msg = ""
    for r in valid_recipients:
        if r.message:
            sample_msg = r.message
            break

    return {
        "total_selected": len(residents) + len(contacts) + len(users),
        "total_residents": len(residents),
        "total_contacts": len(contacts),
        "valid_recipients": valid_recipients,
        "valid_count": len(valid_recipients),
        "duplicates": duplicate_recipients,
        "duplicate_count": len(duplicate_recipients),
        "invalid": invalid_recipients,
        "invalid_count": len(invalid_recipients),
        "sample_message": sample_msg,
    }


def send_campaign(
    sender_user,
    resident_ids: Optional[List[int]] = None,
    contact_ids: Optional[List[int]] = None,
    message_body: str = "",
    user_ids: Optional[List[int]] = None,
    provider: Optional[BaseSmsProvider] = None,
    max_workers: int = 5,
) -> dict[str, Any]:
    """
    Execute an SMS campaign:
    - Resolves and deduplicates recipients
    - Creates SmsCampaign record
    - Sends personalized messages concurrently via ThreadPoolExecutor
    - Records detailed SmsRecipientLog for each recipient
    - Updates campaign statistics and status
    """
    if provider is None:
        provider = get_sms_provider()

    preview = prepare_campaign_preview(
        resident_ids=resident_ids,
        contact_ids=contact_ids,
        message_body=message_body,
        user_ids=user_ids,
    )
    valid_recipients: list[ResolvedRecipient] = preview["valid_recipients"]
    duplicate_recipients: list[ResolvedRecipient] = preview["duplicates"]
    invalid_recipients: list[ResolvedRecipient] = preview["invalid"]

    # Determine recipient source label
    has_res = bool(resident_ids)
    has_cnt = bool(contact_ids)
    if has_res and has_cnt:
        source = SmsCampaign.Source.MIXED
    elif has_cnt:
        source = SmsCampaign.Source.CONTACTS
    elif has_res:
        # Check if all selected residents are in debt
        residents_qs = Resident.objects.filter(id__in=resident_ids)
        all_debtors = all(r.is_in_debt for r in residents_qs) if residents_qs.exists() else False
        source = SmsCampaign.Source.DEBTORS if all_debtors else SmsCampaign.Source.RESIDENTS
    else:
        source = SmsCampaign.Source.MIXED

    with transaction.atomic():
        campaign = SmsCampaign.objects.create(
            sender=sender_user,
            message_body=message_body.strip(),
            recipient_source=source,
            total_selected=preview["total_selected"],
            total_deduplicated=preview["valid_count"],
            status=SmsCampaign.Status.PENDING,
        )

        # Log invalid recipients immediately
        for inv in invalid_recipients:
            SmsRecipientLog.objects.create(
                campaign=campaign,
                recipient_type=inv.recipient_type,
                resident=inv.obj if inv.recipient_type == "resident" else None,
                contact=inv.obj if inv.recipient_type == "contact" else None,
                user=inv.obj if inv.recipient_type == "user" else None,
                phone_number=inv.phone_number or "بدون شماره",
                final_message="",
                status=SmsRecipientLog.Status.SKIPPED_INVALID,
                error_message=inv.invalid_reason or "شماره موبایل نامعتبر است.",
            )

        # Log duplicate recipients
        for dup in duplicate_recipients:
            SmsRecipientLog.objects.create(
                campaign=campaign,
                recipient_type=dup.recipient_type,
                resident=dup.obj if dup.recipient_type == "resident" else None,
                contact=dup.obj if dup.recipient_type == "contact" else None,
                user=dup.obj if dup.recipient_type == "user" else None,
                phone_number=dup.phone_number,
                final_message=dup.message,
                status=SmsRecipientLog.Status.SKIPPED_DUPLICATE,
                error_message="شماره در این کمپین تکراری بود و یک‌بار با اولویت بالاتر ارسال شد.",
            )

    successful_count = 0
    failed_count = 0
    blocked_count = 0
    successful_recipients: list[dict[str, str]] = []
    blocked_recipients: list[dict[str, str]] = []
    failed_recipients: list[dict[str, str]] = []

    # Dispatch valid recipients concurrently with full isolation per recipient
    if valid_recipients:
        def _send_single(recipient: ResolvedRecipient) -> tuple[ResolvedRecipient, ProviderResult]:
            try:
                res = provider.send_simple_sms(
                    recipients=[recipient.phone_number],
                    text=recipient.message,
                )
                return recipient, res
            except Exception as exc:
                logger.exception("Unexpected error sending SMS to %s", recipient.phone_number)
                return recipient, ProviderResult(
                    success=False,
                    error_code="UNEXPECTED_ERROR",
                    error_message=f"خطای غیرمنتظره در ارسال: {str(exc)[:120]}",
                )

        workers = min(max_workers, len(valid_recipients))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_rec = {
                executor.submit(_send_single, rec): rec
                for rec in valid_recipients
            }
            for future in as_completed(future_to_rec):
                rec = future_to_rec[future]
                try:
                    rec, result = future.result()
                except Exception as exc:
                    logger.exception("Error reading future result for %s", rec.phone_number)
                    result = ProviderResult(
                        success=False,
                        error_code="DISPATCH_ERROR",
                        error_message=f"خطا در پردازش نتیجه ارسال: {str(exc)[:120]}",
                    )

                is_bl = getattr(result, "is_blacklist", False) or "BLACKLIST" in str(result.error_code).upper()

                if result.success:
                    status = SmsRecipientLog.Status.SUCCESS
                    successful_count += 1
                    successful_recipients.append({
                        "name": rec.name,
                        "phone_number": rec.phone_number,
                        "details": rec.details,
                        "rec_id": result.rec_id,
                    })
                elif is_bl:
                    status = SmsRecipientLog.Status.BLOCKED_ADVERTISING
                    failed_count += 1
                    blocked_count += 1
                    blocked_recipients.append({
                        "name": rec.name,
                        "phone_number": rec.phone_number,
                        "details": rec.details,
                        "error_message": result.error_message or "دریافت پیامک تبلیغاتی مسدود است (لیست سیاه).",
                    })
                else:
                    status = SmsRecipientLog.Status.FAILED
                    failed_count += 1
                    failed_recipients.append({
                        "name": rec.name,
                        "phone_number": rec.phone_number,
                        "details": rec.details,
                        "error_message": result.error_message or f"خطا در ارسال ({result.error_code})",
                    })

                SmsRecipientLog.objects.create(
                    campaign=campaign,
                    recipient_type=rec.recipient_type,
                    resident=rec.obj if rec.recipient_type == "resident" else None,
                    contact=rec.obj if rec.recipient_type == "contact" else None,
                    user=rec.obj if rec.recipient_type == "user" else None,
                    phone_number=rec.phone_number,
                    final_message=rec.message,
                    status=status,
                    provider_rec_id=result.rec_id,
                    error_code=result.error_code,
                    error_message=result.error_message,
                )

    # Update campaign totals and final status
    total_attempted = preview["valid_count"]
    if total_attempted == 0:
        campaign.status = SmsCampaign.Status.FAILED
    elif successful_count == total_attempted:
        campaign.status = SmsCampaign.Status.COMPLETED
    elif successful_count == 0:
        campaign.status = SmsCampaign.Status.FAILED
    else:
        campaign.status = SmsCampaign.Status.PARTIAL_FAILURE

    campaign.successful_count = successful_count
    campaign.failed_count = failed_count
    campaign.blocked_count = blocked_count
    campaign.save(update_fields=["status", "successful_count", "failed_count", "blocked_count"])

    return {
        "campaign": campaign,
        "total_selected": preview["total_selected"],
        "total_deduplicated": preview["valid_count"],
        "successful_count": successful_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "successful_recipients": successful_recipients,
        "blocked_recipients": blocked_recipients,
        "failed_recipients": failed_recipients,
        "skipped_duplicates": preview["duplicate_count"],
        "skipped_invalid": preview["invalid_count"],
        "status": campaign.status,
    }
