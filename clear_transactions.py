#!/usr/bin/env python
"""
اسکریپت پاک‌سازی دستی تراکنش‌های مالی سیستم مدیریت خوابگاه
این اسکریپت تمام تراکنش‌های مالی را به طور ایمن پاک می‌کند
اما اطلاعات ساکنین، اتاق‌ها، خوابگاه‌ها و سرپرستان را کاملاً حفظ می‌کند.

نحوه اجرا:
    python clear_transactions.py
یا
    python manage.py clear_transactions

گزینه‌ها (اختیاری):
    python clear_transactions.py --dry-run          # شبیه‌سازی بدون حذف
    python clear_transactions.py --yes              # حذف مستقیم بدون سوال
    python clear_transactions.py --include-archived # حذف تراکنش‌های آرشیو شده
    python clear_transactions.py --reset-settled    # ریست کردن فیلد تسویه حساب ساکنین
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    
    # Add project root to sys.path
    project_dir = os.path.dirname(os.path.abspath(__file__))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    apps_dir = os.path.join(project_dir, 'apps')
    if apps_dir not in sys.path:
        sys.path.insert(0, apps_dir)

    import django
    django.setup()

    from django.core.management import call_command
    call_command('clear_transactions', *sys.argv[1:])


if __name__ == '__main__':
    main()
