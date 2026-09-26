# راهنمای جامع استقرار سامانه مدیریت خوابگاه در سرور واقعی (Production Deployment)

این راهنما مراحل راه‌اندازی و دپلوی سامانه مدیریت خوابگاه را از محیط لوکال به یک سرور واقعی (VPS یا سرویس‌های ابری نظیر لیارا) به صورت گام‌به‌گام توضیح می‌دهد.

---

## فهرست مطالب
1. [پیش‌نیازها](#۱-پیش‌نیازها)
2. [روش اول: استقرار با Docker و Docker Compose (پیشنهادی برای سرور لینوکس VPS)](#۲-روش-اول-استقرار-با-docker-و-docker-compose)
3. [تنظیم گواهی امنیتی SSL رایگان (Let's Encrypt)](#۳-تنظیم-گواهی-امنیتی-ssl-رایگان-lets-encrypt)
4. [روش دوم: استقرار روی هاست‌های ابری داخلی (مانند لیارا)](#۴-روش-دوم-استقرار-روی-هاست‌های-ابری-داخلی-مانند-لیارا)
5. [پشتیبان‌گیری و بازیابی اطلاعات (Backup & Restore)](#۵-پشتیبان‌گیری-و-بازیابی-اطلاعات-backup--restore)
6. [نکات امنیتی پروداکشن](#۶-نکات-امنیتی-پروداکشن)

---

## ۱. پیش‌نیازها

برای استقرار روی یک سرور مجازی (Ubuntu 22.04 یا 24.04 پیشنهادی):
- حداقل مشخصات سخت‌افزاری: ۲ هسته CPU، ۲ گیگابایت رم، ۲۰ گیگابایت هارد SSD
- ابزارهای لازم نصب شده روی سرور:
  ```bash
  sudo apt update && sudo apt upgrade -y
  sudo apt install -y git curl docker.io docker-compose-plugin
  sudo systemctl enable --now docker
  ```

---

## ۲. روش اول: استقرار با Docker و Docker Compose

این روش کاملاً ایزوله، امن و خودکار است. داکر به طور همزمان دیتابیس PostgreSQL، وب‌سرور جنگو (Gunicorn) و وب‌سرور معکوس Nginx را راه‌اندازی می‌کند.

### گام ۱: دریافت پروژه روی سرور
```bash
git clone <آدرس_مخزن_گیت> /opt/dormitory-management
cd /opt/dormitory-management
```

### گام ۲: ایجاد فایل تنظیمات محیطی (`.env`)
فایل نمونه را کپی کرده و مقادیر واقعی را درون آن وارد کنید:
```bash
cp .env.example .env
nano .env
```
مقادیر مهم:
- `SECRET_KEY`: یک رشته طولانی و تصادفی
- `DEBUG=False`
- `ALLOWED_HOSTS`: دامنه یا IP سرور شما (مثلاً `dorm.example.ir,185.120.40.10`)
- `CSRF_TRUSTED_ORIGINS`: آدرس کامل دامنه با پروتکل (مثلاً `https://dorm.example.ir`)
- `DB_PASSWORD`: یک رمز عبور قوی برای دیتابیس PostgreSQL
- `MELIPAYAMAK_API_TOKEN`: کلید وب‌سرویس ملی‌پیامک (در صورت ارسال پیامک)

### گام ۳: راه‌اندازی سامانه با داکر
تنها با اجرای دستور زیر، تمام کانتینرها ساخته شده، مایگریشن‌ها اجرا و فایل‌های استاتیک جمع‌آوری می‌شوند:
```bash
docker compose up -d --build
```

### گام ۴: ساخت حساب مدیر اصلی (Superuser)
برای ورود به پنل ادمین جنگو:
```bash
docker compose exec web python manage.py createsuperuser
```

### گام ۵: بررسی وضعیت کانتینرها
```bash
docker compose ps
docker compose logs -f web
```
اکنون سامانه از طریق پورت ۸۰ سرور و دامنه شما در دسترس است!

---

## ۳. تنظیم گواهی امنیتی SSL رایگان (Let's Encrypt)

برای اینکه آدرس سایت با `https://` باز شود و اطلاعات دانشجوها رمزنگاری گردد:

۱. نرم‌افزار Certbot را نصب کنید:
```bash
sudo apt install -y certbot python3-certbot-nginx
```

۲. دریافت گواهی:
```bash
sudo certbot certonly --webroot -w /opt/dormitory-management/certbot_www -d dorm.example.ir
```

۳. در فایل `.env` سرور، متغیرهای زیر را فعال کنید:
```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

۴. ری‌استارت کانتینر وب:
```bash
docker compose restart web nginx
```

---

## ۴. روش دوم: استقرار روی هاست‌های ابری داخلی (مانند لیارا)

اگر مایل به مدیریت سرور لینوکس نیستید، می‌توانید از پلتفرم ابری **لیارا (Liara)** استفاده نمایید:

۱. ایجاد یک دیتابیس **PostgreSQL** در پنل لیارا.
۲. ایجاد یک برنامه پایتون در لیارا.
۳. تعریف متغیرهای محیطی (`SECRET_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`) در بخش متغیرهای برنامه در پنل لیارا.
۴. ایجاد یک دیسک (Disk) برای ذخیره عکس‌های مدارک با مسیر `/app/media`.
۵. اجرای دستور انتشار با CLI لیارا:
```bash
liara deploy
```

---

## ۵. پشتیبان‌گیری و بازیابی اطلاعات (Backup & Restore)

### پشتیبان‌گیری سریع از دیتابیس:
```bash
# ایجاد فایل بکاپ
docker compose exec db pg_dump -U postgres dormitory_db > backup_$(date +%Y%m%d_%H%M%S).sql

# بکاپ از عکس‌های مدارک ساکنین:
tar -czvf media_backup_$(date +%Y%m%d).tar.gz media/
```

### بازیابی دیتابیس (Restore):
```bash
cat backup_file.sql | docker compose exec -T db psql -U postgres dormitory_db
```

### تنظیم بکاپ خودکار روزانه (Cronjob):
دستور `crontab -e` را در سرور اجرا کرده و خط زیر را اضافه کنید تا هر شب ساعت ۳ بامداد بکاپ گرفته شود:
```bash
0 3 * * * cd /opt/dormitory-management && docker compose exec -T db pg_dump -U postgres dormitory_db | gzip > /opt/backups/db_$(date +\%Y\%m\%d).sql.gz
```

---

## ۶. نکات امنیتی پروداکشن

۱. **محدودسازی دسترسی به پورت دیتابیس:** در فایل `docker-compose.yml` پورت 5432 به بیرون سرور فوروارد نشده است و فقط کانتینر وب از شبکه داخلی به آن دسترسی دارد.
۲. **حفاظت در برابر Brute-force:** وب‌سرور Nginx روی آدرس لاگین (`/accounts/login/`) محدودیت ۵ درخواست در دقیقه به ازای هر IP اعمال می‌کند.
۳. **حجم آپلود فایل:** حداکثر حجم فایل ۱۵ مگابایت تنظیم شده است و سامانه خودکار عکس‌های آپلودشده مدارک را فشرده می‌کند.
۴. **تفکیک دسترسی:** هیچ دانشجویی اجازه دسترسی به پنل مدیریت یا اطلاعات سایر ساکنین را ندارد.
