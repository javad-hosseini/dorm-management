# SMS Service Module (`apps.sms_service`)
### Production-Ready MeliPayamak (ملی پیامک) SMS Management Architecture

This document provides complete, exhaustive architectural and implementation documentation for the `sms_service` application. It is written specifically so any backend engineer can understand the entire design, data flow, error handling, security policies, and extension points from A to Z.

---

## Table of Contents
1. [High-Level Architecture](#1-high-level-architecture)
2. [Directory & File Structure](#2-directory--file-structure)
3. [Environment Configuration & Credentials](#3-environment-configuration--credentials)
4. [Data Models & Schema Details](#4-data-models--schema-details)
5. [Phone Normalization & Number Etiquette (`utils.py`)](#5-phone-normalization--number-etiquette-utilspy)
6. [Gateway Provider Layer (`services/provider.py`)](#6-gateway-provider-layer-servicesproviderpy)
7. [Campaign Orchestration & Sending Pipeline (`services/campaign_service.py`)](#7-campaign-orchestration--sending-pipeline-servicescampaign_servicepy)
8. [Admin Interface & Multi-Step Workflow](#8-admin-interface--multi-step-workflow)
9. [Security, Permissions & Safety Rules](#9-security-permissions--safety-rules)
10. [Diagnostic CLI Tools (`send_test_sms`)](#10-diagnostic-cli-tools-send_test_sms)
11. [Automated Test Suite](#11-automated-test-suite)
12. [Extending to Pattern SMS (`SendByBaseNumber`)](#12-extending-to-pattern-sms-sendbybasenumber)
13. [Troubleshooting & Common Edge Cases](#13-troubleshooting--common-edge-cases)

---

## 1. High-Level Architecture

The `sms_service` app provides a centralized, reliable, and audited mechanism to compose and send SMS messages to two distinct audiences directly from Django Admin:
1. **Registered Website Users** (`accounts.User`): Users with an account in the database. Messages are **personalized** with their name (`{full_name} عزیز\n{message}`).
2. **Contact Book Entries** (`Contact`): Individuals who are not website users. Messages are sent **raw/plain** (`{message}`) without prepending a name greeting.

### Key Architectural Principles:
- **Direct HTTP/REST over SOAP**: Uses standard Python `requests` (already pinned in the project) to communicate with MeliPayamak's token-based Console REST endpoint (`https://console.melipayamak.com/api/send/simple/{token}`). Eliminates complex SOAP/XML dependencies (`zeep`, `lxml`) that often fail on Windows build environments.
- **Single Source of Truth for Phone Numbers**: All Iranian mobile numbers (+98, 0098, 98, Persian digits `۰-۹`, Arabic digits `٠-٩`) are canonicalized to standard `09xxxxxxxxx` (11 digits).
- **Cross-Source Deduplication**: If a mobile number exists as both a registered user and a contact book entry, the system automatically deduplicates the campaign so the recipient is messaged **only once**, granting precedence to the Registered User so they receive the personalized greeting.
- **Safe Concurrency & Dispatch**:
  - Contacts and users are dispatched concurrently via `concurrent.futures.ThreadPoolExecutor` (up to 5 workers).
  - Every recipient receives an individual audit log tracking their specific gateway receipt ID (`recId`), provider `status`, and error details.
- **Two-Tier Audit Trail**: Every sending action creates a parent `SmsCampaign` and individual child `SmsRecipientLog` rows, storing exact messages, timestamps, status badges, and MeliPayamak receipt IDs (`recId`).
- **Development Mock Mode**: When credentials are unset or `SMS_CONSOLE_MODE=True`, messages are cleanly logged to the server console/logger with mock receipt IDs, preventing accidental billing or broken tests.

---

## 2. Directory & File Structure

```text
apps/sms_service/
├── __init__.py
├── apps.py                     # App configuration (name='apps.sms_service', label='sms_service')
├── admin.py                    # ContactAdmin, SmsCampaignAdmin, SmsRecipientLogAdmin & Send view
├── forms.py                    # SmsComposerForm (validation & clean textarea)
├── models.py                   # Contact, SmsCampaign, SmsRecipientLog
├── utils.py                    # Phone normalization, regex validation, personalization, part calc
├── views.py                    # Reserved for future public webhooks
├── migrations/
│   ├── 0001_initial.py         # Initial database migration
│   └── __init__.py
├── management/
│   ├── __init__.py
│   └── commands/
│       ├── __init__.py
│       └── send_test_sms.py    # Diagnostic CLI command for quick verification
├── sample/                     # Official provider sample references
├── services/
│   ├── __init__.py             # Clean public API exports
│   ├── provider.py             # MeliPayamak REST client, Console mock, error mapping
│   └── campaign_service.py     # Deduplication, ThreadPool dispatch, batching, logging
└── tests/
    ├── __init__.py
    ├── test_utils.py           # 12 tests: normalization, digit mapping, personalization
    ├── test_models.py          # 5 tests: contact uniqueness, clean, campaign models
    ├── test_provider.py        # 7 tests: mocked HTTP calls, error codes, timeouts
    ├── test_services.py        # 5 tests: deduplication precedence, batching, threading
    └── test_admin.py           # 10 tests: permissions, CSRF, GET safety, workflow
```

---

## 3. Environment Configuration & Credentials

Configuration parameters are read via `python-decouple` in [config/settings.py](file:///d:/projects/websites/sidoos-plasco-shop/config/settings.py).

### Environment Files:
- **Local Development**: [.env.dev](file:///d:/projects/websites/sidoos-plasco-shop/.env.dev) (loaded automatically when `DJANGO_ENV` is not set to `production`).
- **Production Server**: [.env.prod](file:///d:/projects/websites/sidoos-plasco-shop/.env.prod) (loaded when `DJANGO_ENV=production`).

### Variables Description:
```dotenv
# ==========================================
# MeliPayamak SMS Gateway Credentials (Console Simple API)
# ==========================================

# 1. MELIPAYAMAK_API_TOKEN:
# The Web Service API token generated in MeliPayamak Console (e.g. e4a91aa15f634647892de8ea00eb5620).
# Appended to the endpoint URL: https://console.melipayamak.com/api/send/simple/{token}
# Never exposed in logs, exceptions, or admin UI.
MELIPAYAMAK_API_TOKEN=your_console_api_token_here

# 2. MELIPAYAMAK_SENDER:
# The approved sender line assigned to your panel (e.g. 50004001985465, 3000..., or 1000...).
MELIPAYAMAK_SENDER=50004001985465

# 3. MELIPAYAMAK_API_BASE_URL:
# Base REST endpoint for Simple SMS. Defaults to https://console.melipayamak.com/api/send/simple
MELIPAYAMAK_API_BASE_URL=https://console.melipayamak.com/api/send/simple

# 4. SMS_CONSOLE_MODE:
# Boolean flag.
# Set to True: SMS messages are mocked and printed to the server log (no actual SMS sent, no charge).
# Set to False: Real HTTP requests are dispatched to MeliPayamak.
# Default in development: True. Must be False in production!
SMS_CONSOLE_MODE=False
```

---

## 4. Data Models & Schema Details

Located in [apps/sms_service/models.py](file:///d:/projects/websites/sidoos-plasco-shop/apps/sms_service/models.py):

### 4.1. `Contact` (Contact Book)
Independent address book for recipients who are not website users.
- `full_name`: `CharField(max_length=150)` — Identification label inside the admin.
- `phone_number`: `CharField(max_length=15, unique=True)` — Normalized 11-digit mobile number (`09xxxxxxxxx`).
- `notes`: `TextField(blank=True)` — Optional staff remarks.
- `created_at` / `updated_at`: Timestamps.
- **Model Hooks**:
  - `clean()` and `save()` automatically invoke `normalize_phone_number(self.phone_number)`.
  - Database-level `unique=True` ensures duplicate phone numbers cannot be entered in the contact book.

### 4.2. `SmsCampaign` (Sending Session Header)
Records the parent campaign metadata when an admin triggers an SMS batch.
- `sender`: `ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)` — Staff member who sent the campaign.
- `message_body`: `TextField` — Raw text composed by the staff member.
- `recipient_source`: `CharField` — Choices:
  - `users`: Registered users only.
  - `contacts`: Contact book only.
  - `mixed`: Both groups targeted simultaneously.
- `total_selected`: `PositiveIntegerField` — Raw count of recipients checked by the admin.
- `total_deduplicated`: `PositiveIntegerField` — Effective unique numbers that actually received an SMS.
- `successful_count`: `PositiveIntegerField` — Numbers successfully accepted by the gateway.
- `failed_count`: `PositiveIntegerField` — Numbers rejected by the gateway or timed out.
- `status`: `CharField` — Lifecycle state:
  - `pending`: Currently dispatching.
  - `completed`: 100% of unique recipients succeeded.
  - `partial_failure`: Some recipients succeeded while others failed.
  - `failed`: All recipients failed.
- `created_at`: `DateTimeField(auto_now_add=True)`.

### 4.3. `SmsRecipientLog` (Individual Recipient Audit Log)
Child record storing the granular delivery status for each recipient.
- `campaign`: `ForeignKey(SmsCampaign, on_delete=models.CASCADE, related_name='recipients')`.
- `recipient_type`: `CharField` — Choices: `user` or `contact`.
- `user`: `ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)` — Linked if recipient is a site user.
- `contact`: `ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL)` — Linked if recipient is a contact book person.
- `phone_number`: `CharField(max_length=15)` — Normalized phone number.
- `final_message`: `TextField` — Exact string delivered to this specific recipient (includes personalized greeting for users).
- `status`: `CharField` — Choices:
  - `success`: Delivered / accepted by MeliPayamak.
  - `failed`: Provider rejected or network failed.
  - `skipped_duplicate`: Not sent because the number was already sent to a higher-priority target in the same campaign.
  - `skipped_invalid`: Invalid phone number syntax.
- `provider_rec_id`: `CharField(max_length=100, blank=True)` — MeliPayamak receipt ID (`recId`).
- `error_code`: `CharField(max_length=50, blank=True)` — Numeric provider error code (e.g. `2`, `5`, `18`).
- `error_message`: `TextField(blank=True)` — Human-readable Persian translation of the failure.
- `created_at`: `DateTimeField(auto_now_add=True)`.

---

## 5. Phone Normalization & Number Etiquette (`utils.py`)

Located in [apps/sms_service/utils.py](file:///d:/projects/websites/sidoos-plasco-shop/apps/sms_service/utils.py):

### 5.1. Normalization Flow (`normalize_phone_number`)
```
Input: "+۹۸ ۹۱۲-۳۴۵-۶۷۸۹"
  │
  ▼ 1. Translate Persian/Arabic digits (۰-۹, ٠-٩) to ASCII (0-9)
"+98 912-345-6789"
  │
  ▼ 2. Strip non-digits (preserving leading +)
"+989123456789"
  │
  ▼ 3. Handle international prefixes
       - Starts with +98 or 0098 or 98 (12 digits) -> strip country code
       - Starts with 9 (10 digits) -> prepend 0
"09123456789"
  │
  ▼ 4. Validate against regex: ^09\d{9}$ (exactly 11 digits, starts with 09)
Valid: Return "09123456789"
Invalid: Raise ValidationError
```

### 5.2. Personalization Etiquette (`format_personalized_message`)
- **Registered User with Name**:
  ```text
  علی رضایی عزیز
  سفارش شما آماده تحویل است.
  ```
- **Registered User without First/Last Name** (fallback):
  ```text
  کاربر گرامی
  سفارش شما آماده تحویل است.
  ```
  *(Avoids broken strings like `عزیز\nسفارش شما...` or awkward username insertions).*
- **Contact Book Person**:
  ```text
  سفارش شما آماده تحویل است.
  ```
  *(Always plain message body without greeting).*

### 5.3. SMS Segment Calculator (`calculate_sms_parts`)
Standard Iranian Unicode/Persian SMS encoding rules:
- Part 1: up to 70 characters.
- Part 2+: 67 characters per additional part.

---

## 6. Gateway Provider Layer (`services/provider.py`)

Located in [apps/sms_service/services/provider.py](file:///d:/projects/websites/sidoos-plasco-shop/apps/sms_service/services/provider.py):

### 6.1. Provider Interface
```python
class BaseSmsProvider(ABC):
    @abstractmethod
    def send_simple_sms(self, recipients: list[str], text: str, is_flash: bool = False) -> ProviderResult:
        pass

    def send_pattern_sms(self, to: str, body_id: int, args: list[str]) -> ProviderResult:
        raise NotImplementedError(...)
```

### 6.2. `ProviderResult` Dataclass
```python
@dataclass
class ProviderResult:
    success: bool
    rec_id: str = ""
    error_code: str = ""
    error_message: str = ""
    raw_response: str = ""
```

### 6.3. Comprehensive Error Code Mapping
MeliPayamak REST returns a string or JSON containing a numeric status code. Large numbers (> 15) represent the delivery receipt ID (`recId`). Small integers or negative numbers represent specific error conditions:

| Return Code | Description | Human-Readable Persian Translation |
| :--- | :--- | :--- |
| `> 15` | **Success** | پیامک با موفقیت به درگاه ارسال شد (شناسه رسید recId). |
| `1` | **Success** | درخواست با موفقیت انجام شد. |
| `0` | Invalid Credentials | نام کاربری یا رمز عبور سامانه پیامک اشتباه است. |
| `2` | Insufficient Credit | اعتبار پنل پیامکی کافی نمی‌باشد. |
| `3` | Daily Limit Reached | محدودیت در تعداد ارسال روزانه. |
| `4` | Volume Limit Reached | محدودیت در حجم ارسال. |
| `5` | Invalid Sender Line | شماره فرستنده معتبر نمی‌باشد یا به پنل تعلق ندارد. |
| `6` | Maintenance | سامانه پیامک در حال بروزرسانی می‌باشد. |
| `7` | Word Filtered | متن پیامک حاوی کلمات فیلتر شده می‌باشد. |
| `9` | Public Line Blocked | ارسال از خطوط عمومی از طریق وب‌سرویس امکان‌پذیر نمی‌باشد. |
| `10` | Account Inactive | حساب کاربری در سامانه پیامک فعال نمی‌باشد. |
| `11` | Not Sent | پیامک ارسال نشد. |
| `12` | Incomplete Verification | مدارک هویتی در سامانه پیامک تایید نشده است. |
| `14` | Disallowed Link | متن پیامک حاوی لینک غیرمجاز می‌باشد. |
| `15` | Opt-out Missing | ارسال گروهی بدون درج گزینه لغو امکان‌پذیر نیست. |
| `16` | Recipient Not Found | شماره گیرنده‌ای یافت نشد. |
| `17` | Empty Text | متن پیامک خالی می‌باشد. |
| `18` | Invalid Recipient Number | شماره گیرنده نامعتبر است. |
| `-108` | IP Blocked | آدرس IP به دلیل تلاش‌های ناموفق مکرر مسدود شده است. |
| `-109` | IP Whitelist Required | الزام به تنظیم آدرس IP مجاز در پنل ملی‌پیامک. |
| `-110` | ApiKey Required | الزام به استفاده از کلید API (ApiKey) به جای رمز عبور. |

### 6.4. `ConsoleSmsProvider`
When `SMS_CONSOLE_MODE = True` or when credentials are not configured in settings:
- Generates a mock receipt ID: `MOCK-XXXXXXXX`.
- Logs the payload via Django logger `apps.sms_service.services.provider`.
- Returns `ProviderResult(success=True, rec_id=...)`.

---

## 7. Campaign Orchestration & Sending Pipeline (`services/campaign_service.py`)

Located in [apps/sms_service/services/campaign_service.py](file:///d:/projects/websites/sidoos-plasco-shop/apps/sms_service/services/campaign_service.py):

### Execution Pipeline Diagram:
```text
Admin Submits IDs & Text
       │
       ▼
[prepare_campaign_preview]
       │
       ├─► 1. Query Users and Contacts from DB
       ├─► 2. Normalize all phone numbers
       ├─► 3. Cross-Deduplication:
       │      User takes precedence. Duplicate Contact marked SKIPPED_DUPLICATE
       └─► 4. Return Preview Metrics (total, deduplicated, duplicates, invalid)
       │
       ▼ (Admin Confirms via POST)
[send_campaign]
       │
       ├─► Atomic DB Transaction: Create SmsCampaign (status='pending')
       │   Log invalid numbers (SKIPPED_INVALID) & duplicates (SKIPPED_DUPLICATE)
       │
       ├─► 1. Registered Users Dispatch (Personalized):
       │      ThreadPoolExecutor(max_workers=5)
       │      Individual API calls with "{name} عزیز\n{text}"
       │      Log each outcome in SmsRecipientLog
       │
       ├─► 2. Contact Book Dispatch (Identical):
       │      Split into chunks of up to 100 numbers (PROVIDER_BATCH_LIMIT)
       │      Batch API calls with plain "{text}"
       │      Log each outcome in SmsRecipientLog
       │
       └─► 3. Update Campaign Totals:
              successful_count, failed_count
              Final status: 'completed' | 'partial_failure' | 'failed'
```

---

## 8. Admin Interface & Multi-Step Workflow

Located in [apps/sms_service/admin.py](file:///d:/projects/websites/sidoos-plasco-shop/apps/sms_service/admin.py) and templates:

### 8.1. Entry Points
1. **Direct Navigation**: `/sidoos-administration/sms_service/smscampaign/send/` (also accessible via sidebar icon `fas fa-sms` under "مرکز ارسال پیامک").
2. **UserAdmin Action**: In `/sidoos-administration/accounts/user/`, check desired users and select action *"ارسال پیامک به کاربران انتخاب‌شده"*. Redirects to the composer with those user IDs pre-selected.
3. **ContactAdmin Action**: In `/sidoos-administration/sms_service/contact/`, check desired contacts and select action *"ارسال پیامک به مخاطبین انتخاب‌شده"*. Redirects to the composer with those contact IDs pre-selected.

### 8.2. Step 1: Selection & Composition ([send_sms.html](file:///d:/projects/websites/sidoos-plasco-shop/templates/admin/sms_service/send_sms.html))
- Two tabs: **کاربران سایت (عضو)** and **دفترچه تلفن (غیرعضو)**.
- Client-side real-time table search filters and "انتخاب همه" (Select All) checkboxes.
- Counter bar updating in real time: `کاربران انتخاب‌شده: X | مخاطبین انتخاب‌شده: Y | کل انتخابی: Z`.
- Textarea with live character counter, live SMS parts counter, and **dual live preview** (showing how the user greeting will look versus the plain contact text).
- Submitting triggers POST with `step=preview`.

### 8.3. Step 2: Review & Confirmation ([send_confirm.html](file:///d:/projects/websites/sidoos-plasco-shop/templates/admin/sms_service/send_confirm.html))
- Server re-queries and validates all IDs from the database (never trusts client state).
- Shows safety alert and deduplication breakdown:
  - Total selected numbers.
  - Unique numbers to be messaged.
  - Duplicates removed (explaining that User precedence was applied).
  - Invalid numbers skipped.
- Renders sample personalized message and sample contact message.
- Table listing sample recipients.
- Explicit confirmation form submitting POST with `step=execute`.

### 8.4. Step 3: Completion & Campaign View
- Dispatches sending pipeline.
- Sets Django user messages:
  - Success message with count of delivered messages.
  - Warning message if partial failure occurred.
  - Info message reporting how many duplicates were safely omitted.
- Redirects to the generated `SmsCampaign` change page with full tabular inline audit logs.

---

## 9. Security, Permissions & Safety Rules

1. **Staff & Permission Checks**:
   - Access to the Send SMS view strictly requires `request.user.is_staff and (request.user.is_superuser or request.user.has_perm('sms_service.add_smscampaign'))`.
   - Unauthorized attempts immediately raise `django.core.exceptions.PermissionDenied` (HTTP 403).
2. **Idempotent GET Requests**:
   - GET requests to the send endpoint **never send an SMS under any circumstances**. Sending strictly requires POST.
3. **CSRF Protection**:
   - Both `send_sms.html` and `send_confirm.html` include `{% csrf_token %}`. All POST endpoints enforce Django's CSRF verification.
4. **Credential Isolation**:
   - MeliPayamak username, password, and line number are never rendered in templates, never returned in API responses to the browser, and never logged in plain text.
5. **Server-Side Re-validation**:
   - Client checkboxes and hidden inputs are treated as untrusted; IDs are validated and re-queried against the database before sending.

---

## 10. Diagnostic CLI Tools (`send_test_sms`)

Located in [apps/sms_service/management/commands/send_test_sms.py](file:///d:/projects/websites/sidoos-plasco-shop/apps/sms_service/management/commands/send_test_sms.py).

Enables instant CLI testing and verification of MeliPayamak credentials without touching a web browser:

```powershell
# 1. Test in simulated console mode (default if credentials are unset or SMS_CONSOLE_MODE=True)
python manage.py send_test_sms 09121234567

# 2. Test with custom text
python manage.py send_test_sms 09121234567 --text "تست اختصاصی پنل پیامک"

# 3. Force real live sending to MeliPayamak (bypasses console mode)
python manage.py send_test_sms 09121234567 --real
```

**Output on Success**:
```text
=== بررسی وضعیت درگاه ملی‌پیامک ===
گیرنده: 09121234567
متن پیامک: تست اختصاصی پنل پیامک
نام کاربری ملی‌پیامک: 0912xxxxxxx
شماره فرستنده: 50004001985465
در حال ارسال درخواست به سرور ملی‌پیامک...
✓ پیامک با موفقیت ارسال شد!
شناسه رسید درگاه (recId): 2458963214
```

**Output on Error (e.g. Insufficient credit)**:
```text
✗ ارسال پیامک با خطا مواجه شد!
کد خطا: 2
پیام خطا: اعتبار پنل پیامکی کافی نمی‌باشد.
پاسخ خام درگاه: 2
```

---

## 11. Automated Test Suite

Located in [apps/sms_service/tests/](file:///d:/projects/websites/sidoos-plasco-shop/apps/sms_service/tests/).

All 39 tests mock external HTTP requests, ensuring **zero real SMS messages and zero credit deductions occur during automated test runs**.

### Test Modules:
1. **`test_utils.py` (12 tests)**:
   - Normalization of `09`, `+98`, `0098`, `98`, without leading zero.
   - Persian (`۰۱۲۳۴۵۶۷۸۹`) and Arabic (`٠١٢٣٤٥٦٧٨٩`) digit translation.
   - Rejection of landlines, short strings, non-numeric characters.
   - Personalization with full name, first name only, and missing name fallback (`کاربر گرامی`).
   - SMS part calculation.
2. **`test_models.py` (5 tests)**:
   - Contact model auto-normalization on save.
   - Database uniqueness constraint enforcement.
   - Contact validation errors.
   - `SmsCampaign` and `SmsRecipientLog` creation and status tracking.
3. **`test_provider.py` (7 tests)**:
   - Console provider mock behavior.
   - Empty input validation.
   - Mocked MeliPayamak HTTP responses (recId parsing).
   - Mocked provider error codes (insufficient credit, invalid sender, timeout).
   - Factory resolution.
4. **`test_services.py` (5 tests)**:
   - Deduplication and User precedence verification.
   - Personalized message generation for users vs plain for contacts.
   - Multi-batch chunking (tested with 105 contacts -> exactly 2 batches: 100 + 5).
   - Concurrency and partial failure handling.
5. **`test_admin.py` (10 tests)**:
   - Anonymous access redirected to login.
   - Non-staff / unauthorized staff rejected with HTTP 403.
   - Authorized staff allowed (HTTP 200).
   - GET request never triggers sending.
   - POST step preview validation.
   - POST step execute completion.
   - CSRF protection enforcement.
   - ContactAdmin and UserAdmin list action redirection with query params.

### Running the Tests:
```powershell
# Run SMS Service tests only
python manage.py test apps.sms_service

# Run all 201 tests across the entire project
python manage.py test
```

---

## 12. Extending to Pattern SMS (`SendByBaseNumber`)

The provider abstraction was engineered to support MeliPayamak Pattern SMS (خدماتی / وب‌سرویس پترن) in the future without modifying the existing codebase:

1. **Provider Hook**:
   In [apps/sms_service/services/provider.py](file:///d:/projects/websites/sidoos-plasco-shop/apps/sms_service/services/provider.py), the method `send_pattern_sms(to, body_id, args)` is already declared in `BaseSmsProvider`.
2. **Implementation**:
   To enable Pattern SMS, implement `send_pattern_sms` in `MeliPayamakRestProvider`:
   - Endpoint: `POST https://rest.payamak-panel.com/api/SendSMS/BaseServiceNumber`
   - Parameters:
     ```python
     payload = {
         "username": self.username,
         "password": self.password,
         "to": to,
         "bodyId": body_id,
         "text": ";".join(args),  # Semicolon-delimited arguments per MeliPayamak documentation
     }
     ```
3. Existing simple SMS functionality, models, and admin send views remain completely unaffected.

---

## 13. Troubleshooting & Common Edge Cases

### 1. `CommandError: خطا در تنظیمات ملی‌پیامک: تنظیمات وب‌سرویس ملی‌پیامک (توکن API و شماره خط فرستنده) ... تعریف نشده است`
- **Cause**: `MELIPAYAMAK_API_TOKEN` or `MELIPAYAMAK_SENDER` is empty in the active environment file.
- **Solution**: Open `.env.dev` (for local development) or `.env.prod` (for production) and set `MELIPAYAMAK_API_TOKEN` and `MELIPAYAMAK_SENDER`.

### 2. Changes in `.env.prod` not taking effect in local `runserver`
- **Cause**: By design in [config/settings.py](file:///d:/projects/websites/sidoos-plasco-shop/config/settings.py), Django only reads `.env.prod` when environment variable `DJANGO_ENV=production` is set. When running locally without this variable, Django loads `.env.dev`.
- **Solution**: Ensure your credentials are also present in `.env.dev` for local testing.

### 3. Error Code `2` from MeliPayamak
- **Cause**: Insufficient SMS credit in the panel.
- **Solution**: Recharge SMS credit on [melipayamak.com](https://www.melipayamak.com).

### 4. Error Code `5` from MeliPayamak
- **Cause**: The line specified in `MELIPAYAMAK_SENDER` does not belong to the account or is unapproved.
- **Solution**: Check the active numbers in your MeliPayamak dashboard and copy the exact line number into `MELIPAYAMAK_SENDER`.

### 5. `UnicodeEncodeError: 'charmap' codec can't encode ...` in Windows PowerShell
- **Cause**: Default Windows PowerShell console code page is CP1252 or Windows-1256.
- **Solution**: The `send_test_sms` command automatically calls `sys.stdout.reconfigure(encoding="utf-8")`. In PowerShell, you can also set `$OutputEncoding = [Console]::InputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8`.

