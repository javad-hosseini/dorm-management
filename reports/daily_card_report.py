# reports/daily_card_report.py
import os
import sys

import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.dormitory.models import Transaction
import jdatetime
from tabulate import tabulate


def get_persian_day_name(date):
    """برگرداندن نام روز هفته به فارسی"""
    days = {
        0: 'شنبه', 1: 'یکشنبه', 2: 'دوشنبه', 3: 'سه‌شنبه',
        4: 'چهارشنبه', 5: 'پنجشنبه', 6: 'جمعه'
    }
    return days[date.weekday()]


def get_persian_month_name(month):
    """برگرداندن نام ماه به فارسی"""
    months = {
        1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد', 4: 'تیر',
        5: 'مرداد', 6: 'شهریور', 7: 'مهر', 8: 'آبان',
        9: 'آذر', 10: 'دی', 11: 'بهمن', 12: 'اسفند'
    }
    return months.get(month, '')


def format_tomans(amount):
    """فرمت کردن مبلغ به تومان با جداکننده هزارگان"""
    return f"{amount:,.0f}"


def daily_card_report():
    """گزارش روزانه پرداخت‌های کارت به کارت و کارتخوان"""
    date_input = input("📅 تاریخ را وارد کنید (مثال: YYYY-MM-DD): ").strip()

    try:
        year, month, day = map(int, date_input.split('-'))
        jalali_date = jdatetime.date(year, month, day)
    except (ValueError, jdatetime.JDTypeError):
        print("❌ فرمت تاریخ اشتباه است! مثال: 1405-05-05")
        return

    day_name = get_persian_day_name(jalali_date)
    month_name = get_persian_month_name(month)

    print()
    print("=" * 60)
    print("                📊 گزارش پرداخت‌های روزانه                ")
    print(f"              📅 {day_name} {day} {month_name} {year}              ")
    print("=" * 60)
    print()

    # Filter transactions for the given date
    transactions = Transaction.objects.filter(
        payment_date__date=jalali_date.togregorian(),
        payment_method__in=['BANK_TRANSFER', 'CARD']
    ).select_related('resident')

    # ---- کارت به کارت ----
    bank_transfers = transactions.filter(payment_method='BANK_TRANSFER').order_by('payment_date')

    print("🏦 کارت به کارت:")
    print("-" * 60)

    total_bank_transfer = 0
    count_bank = 0
    bank_details = []

    if bank_transfers.exists():
        for t in bank_transfers:
            count_bank += 1
            amount_tomans = t.amount / 10
            total_bank_transfer += amount_tomans
            time_str = t.payment_date.strftime('%H:%M')

            bank_details.append([
                count_bank,
                t.resident.full_name,
                f"{format_tomans(amount_tomans)} تومان",
                time_str,
            ])

        print(tabulate(bank_details, headers=["ردیف", "نام", "مبلغ", "ساعت"], tablefmt="grid", stralign="center"))
        print()
        print(f"  ➕ جمع کارت به کارت: {format_tomans(total_bank_transfer)} تومان")
    else:
        print("  ❌ هیچ کارت به کاری در این تاریخ ثبت نشده است.")

    print()

    # ---- کارتخوان ----
    card_payments = transactions.filter(payment_method='CARD').order_by('payment_date')

    print("💳 کارتخوان:")
    print("-" * 60)

    total_card = 0
    count_card = 0
    card_details = []

    if card_payments.exists():
        for t in card_payments:
            count_card += 1
            amount_tomans = t.amount / 10
            total_card += amount_tomans
            time_str = t.payment_date.strftime('%H:%M')

            card_details.append([
                count_card,
                t.resident.full_name,
                f"{format_tomans(amount_tomans)} تومان",
                time_str,
            ])

        print(tabulate(card_details, headers=["ردیف", "نام", "مبلغ", "ساعت"], tablefmt="grid", stralign="center"))
        print()
        print(f"  ➕ جمع کارتخوان: {format_tomans(total_card)} تومان")
    else:
        print("  ❌ هیچ پرداخت کارتخوانی در این تاریخ ثبت نشده است.")

    print()

    # ---- خلاصه نهایی ----
    total_all = total_bank_transfer + total_card

    summary_data = [
        ["کارت به کارت", count_bank, f"{format_tomans(total_bank_transfer)} تومان"],
        ["کارتخوان", count_card, f"{format_tomans(total_card)} تومان"],
        ["جمع کل", count_bank + count_card, f"{format_tomans(total_all)} تومان"],
    ]

    print("=" * 60)
    print("📋 خلاصه گزارش:")
    print(tabulate(summary_data, headers=["نوع پرداخت", "تعداد", "مبلغ"], tablefmt="grid", stralign="center"))
    print("=" * 60)
    print()

    compact_report(jalali_date, transactions)



def compact_report(jalali_date, transactions):
    """نسخه کامپکت گزارش"""
    day_name = get_persian_day_name(jalali_date)
    month_name = get_persian_month_name(jalali_date.month)

    print()
    print("=" * 50)
    print("📊 گزارش پرداخت‌های روزانه (کامپکت)")
    print(f"📅 {day_name} {jalali_date.day} {month_name} {jalali_date.year}")
    print("=" * 50)

    # کارت به کارت
    bank_transfers = transactions.filter(payment_method='BANK_TRANSFER').order_by('payment_date')
    total_bank = 0
    count = 1

    print("🏦 کارت به کارت:")
    if bank_transfers.exists():
        for t in bank_transfers:
            amount = t.amount / 10
            total_bank += amount
            time_str = t.payment_date.strftime('%H:%M')
            print(f" {count} | {t.resident.full_name} | {format_tomans(amount)} تومان | {time_str}")
            count += 1
        print()
        print(f"➕ جمع کارت به کارت: {format_tomans(total_bank)} تومان")
    else:
        print(" ❌ موردی یافت نشد")

    print()

    # کارتخوان
    card_payments = transactions.filter(payment_method='CARD').order_by('payment_date')
    total_card = 0

    print("💳 کارتخوان:")
    if card_payments.exists():
        for t in card_payments:
            amount = t.amount / 10
            total_card += amount
            time_str = t.payment_date.strftime('%H:%M')
            print(f" {count} | {t.resident.full_name} | {format_tomans(amount)} تومان | {time_str}")
            count += 1
        print()
        print(f"➕ جمع کارتخوان: {format_tomans(total_card)} تومان")
    else:
        print(" ❌ موردی یافت نشد")

    print()
    print("-" * 50)
    print(f"💰 جمع کل: {format_tomans(total_bank + total_card)} تومان")
    print("=" * 50)


if __name__ == '__main__':
    daily_card_report()

