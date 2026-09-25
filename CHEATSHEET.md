# 📋 چیت‌شیت دستورات کاربردی سیستم مدیریت خوابگاه (Cheatsheet)

> راهنمای سریع و کاربردی برای اجرای اسکریپت‌ها، تست‌ها، مدیریت داده‌ها و دستورات روزمره سامانه.

---

## 📑 فهرست دسته‌بندی‌ها
1. [🧹 پاک‌سازی امن تراکنش‌های مالی (Transaction Purge)](#۱-پاکسازی-امن-تراکنشهای-مالی-transaction-purge)
2. [🧪 اجرای تست‌های خودکار (Automated Tests)](#۲-اجرای-تستهای-خودکار-automated-tests)
3. [🚀 راه‌اندازی و مدیریت سرور (Server & Database)](#۳-راهاندازی-و-مدیریت-سرور-server--database)
4. [🤖 ابزارها و آدرس‌های پرکاربرد (URLs & Endpoints)](#۴-ابزارها-و-آدرسهای-پرکاربرد-urls--endpoints)
5. [💡 نکات کلیدی و عیب‌یابی در ویندوز](#۵-نکات-کلیدی-و-عیبیابی-در-ویندوز)

---

## ۱. پاک‌سازی امن تراکنش‌های مالی (Transaction Purge)

> 🛡️ **تضمین ایمنی:** این اسکریپت **فقط و فقط** تراکنش‌های مالی را پاک می‌کند. اطلاعات تمامی **ساکنین (۱۰۶ نفر)**، **اتاق‌ها (۴۱ اتاق)**، **خوابگاه‌ها**، **سرپرستان** و **یادداشت‌ها** ۱۰۰٪ محفوظ می‌مانند.

### سناریوهای متداول اجرا:

#### ۱. شبیه‌سازی بدون حذف (توصیه می‌شود ابتدا این را اجرا کنید):
مشاهده دقیق رکوردهایی که حذف خواهند شد بدون اینکه تغییری در دیتابیس اعمال شود:
```bash
python clear_transactions.py --dry-run --yes
```

#### ۲. اجرای تعاملی (Interactive):
اسکریپت خلاصه آمار را نمایش می‌دهد و قبل از هر اقدام از شما سوال و تاییدیه می‌گیرد:
```bash
python clear_transactions.py
```

#### ۳. پاک‌سازی کامل و ریست تسویه ساکنین (شروع مجدد از نقطه صفر):
تراکنش‌های فعال و آرشیو را پاک کرده و فیلد تسویه (`settled_until`) ساکنین را نیز ریست می‌کند:
```bash
python clear_transactions.py --yes --reset-settled --include-archived
```

#### ۴. پاک‌سازی تراکنش‌ها با حفظ تاریخ تسویه قبلی ساکنین:
```bash
python clear_transactions.py --yes --keep-settled
```

#### ۵. اجرا از طریق دستور مدیریتی جنگو (معادل):
```bash
python manage.py clear_transactions --dry-run --yes
python manage.py clear_transactions --yes --reset-settled
```

### 📊 جدول پارامترها و پرچم‌ها (Flags):

| پرچم (Flag) | عملکرد | کاربرد |
| :--- | :--- | :--- |
| `--dry-run` | شبیه‌سازی ایمن بدون اعمال تغییر در دیتابیس | بررسی اولیه قبل از اقدام |
| `-y` / `--yes` / `--force` | اجرای مستقیم بدون توقف برای سوال و جواب | اجرای خودکار و سریع |
| `--reset-settled` | تنظیم `settled_until = None` برای ساکنین | شروع دوباره تسویه‌ها از نو |
| `--keep-settled` | حفظ تاریخ‌های تسویه فعلی ساکنین | نگه‌داشتن وضعیت قبلی |
| `--include-archived` | پاک‌کردن تراکنش‌های قدیمی افراد ترخیص‌شده | پاک‌سازی کامل تاریخچه مالی |
| `--exclude-archived` | نگه‌داشتن تراکنش‌های آرشیو و فقط پاک‌کردن فعال | حفظ سوابق قدیمی |

---

## ۲. اجرای تست‌های خودکار (Automated Tests)

> سیستم دارای **۱۷ تست خودکار** جامع است که پایداری منطق تقویم شمسی، پیش‌پرداخت، تاخیرها، پاک‌سازی و فرمت‌ها را بررسی می‌کنند.

#### ۱. اجرای کلیه تست‌های بخش خوابگاه:
```bash
python manage.py test apps.dormitory
```

#### ۲. تست اختصاصی اسکریپت پاک‌سازی تراکنش‌ها:
```bash
python manage.py test apps.dormitory.tests.ClearTransactionsCommandTests
```

#### ۳. تست‌های سیستم پروفایل ناقص و نرمال‌سازی کد ملی/والدین:
```bash
python manage.py test apps.dormitory.tests.IncompleteProfileTests
```

#### ۴. تست‌های حسابداری پیش‌پرداخت و روزشمار تاخیر:
```bash
python manage.py test apps.dormitory.tests.ResidentPrepaymentAndOverdueTests
```

#### ۵. تست‌های سیستم ثبت هوشمند صوتی وقایع روزانه:
```bash
python manage.py test apps.dormitory.tests.AILoaderTests
```

---

## ۳. راه‌اندازی و مدیریت سرور (Server & Database)

### فعال‌سازی محیط مجازی پایتون (Virtual Environment):
* **در PowerShell:**
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
* **در Command Prompt (CMD):**
  ```cmd
  .\venv\Scripts\activate.bat
  ```
* **اجرای مستقیم با مفسر venv (بدون نیاز به فعال‌سازی):**
  ```powershell
  .\venv\Scripts\python.exe manage.py runserver
  ```

### دستورات سرور جنگو:
```bash
# اجرای سرور لوکال (پورت پیش‌فرض ۸۰۰۰)
python manage.py runserver

# اجرای سرور روی پورت دلخواه (مثلاً ۸۰۸۰)
python manage.py runserver 8080

# بررسی تغییرات مدل‌ها و ساخت فایل‌های مایگریشن
python manage.py makemigrations

# اعمال مایگریشن‌ها بر روی پایگاه‌داده
python manage.py migrate

# ایجاد کاربر مدیر ارشد (Superuser)
python manage.py createsuperuser

# باز کردن محیط تعاملی شل جنگو (Python Console با دسترسی به مدل‌ها)
python manage.py shell
```

---

## ۴. ابزارها و آدرس‌های پرکاربرد (URLs & Endpoints)

| نام بخش | آدرس مرورگر (URL) | توضیح |
| :--- | :--- | :--- |
| **🏢 داشبورد اصلی مدیریت** | `http://127.0.0.1:8000/dashboard/` | نمای مدرن شیشه‌ای، وضعیت لحظه‌ای اتاق‌ها، دانشجویان، نمودارها و تقویم شمسی |
| **🎙️ لودر صوتی هوش مصنوعی** | `http://127.0.0.1:8000/admin/ai-loader/` | صفحه تبدیل ویس/متن به رکوردهای دیتابیس با DeepSeek |
| **⚙️ پنل ادمین جنگو** | `http://127.0.0.1:8000/admin/` | مدیریت تفکیکی جداول، کاربران و رسیدهای چاپی |
| **💳 لیست تراکنش‌ها** | `http://127.0.0.1:8000/admin/dormitory/transaction/` | مشاهده، فیلتر و تایید پرداخت‌های نقدی و کارت‌خوان |
| **👥 لیست ساکنین** | `http://127.0.0.1:8000/admin/dormitory/resident/` | وضعیت بدهی، ماه‌های معوقه، تسویه تا تاریخ و ویرایش مشخصات |

---

## ۵. نکات کلیدی و عیب‌یابی در ویندوز

### ۱. خطای سیاست اجرای اسکریپت در پاورشل (`ExecutionPolicy`):
اگر هنگام اجرای `Activate.ps1` با خطای اسکریپت در ویندوز روبرو شدید:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### ۲. تازه‌سازی کش مرورگر برای تقویم شمسی و استایل‌ها:
اگر تغییری در صفحات یا اسکریپت تقویم شمسی مشاهده نشد، حافظه کش موقت مرورگر را تازه‌سازی کنید:
* ویندوز: کلید‌های **`Ctrl + F5`** یا **`Ctrl + Shift + R`**

### ۳. بررسی سریع تعداد رکوردهای دیتابیس در خط فرمان:
```powershell
.\venv\Scripts\python.exe manage.py shell -c "from apps.dormitory.models import Transaction, Resident, Room; print('تراکنش‌ها:', Transaction.objects.count()); print('ساکنین:', Resident.objects.count()); print('اتاق‌ها:', Room.objects.count())"
```
