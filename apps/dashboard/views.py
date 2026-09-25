import json
import jdatetime
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.dormitory.models import Dormitory, Room, Resident, Transaction


def get_admin_dashboard_data():
    """Serialize full real database data for the admin dashboard"""
    # 1. Dormitories
    dorms = list(Dormitory.objects.values_list('name', flat=True))

    # 2. Rooms
    rooms_qs = Room.objects.select_related('dormitory').order_by('dormitory__name', 'room_number')
    rooms_data = []
    for r in rooms_qs:
        rooms_data.append({
            "id": r.id,
            "dormitory": r.dormitory.name,
            "room_number": r.room_number,
            "capacity": r.capacity,
            "monthly_rent": r.monthly_rent,
            "current_occupants": r.current_occupants,
        })

    # 3. Residents
    residents_qs = Resident.objects.select_related('room', 'dormitory').order_by('-entry_date')
    residents_data = []
    today = jdatetime.date.today()
    for res in residents_qs:
        residents_data.append({
            "id": res.id,
            "first_name": res.first_name,
            "last_name": res.last_name,
            "father_name": res.father_name or "",
            "full_name": res.full_name,
            "is_foreign": res.is_foreign,
            "national_code": res.national_code,
            "phone_number": res.phone_number,
            "parent_phone_number": res.parent_phone_number or "",
            "room": {
                "id": res.room.id,
                "room_number": res.room.room_number,
                "monthly_rent": res.room.monthly_rent,
                "capacity": res.room.capacity
            } if res.room else None,
            "dormitory": res.dormitory.name if res.dormitory else "",
            "entry_date": str(res.entry_date) if res.entry_date else "",
            "settled_until": str(res.settled_until) if res.settled_until else "",
            "settled_until_display": res.settled_until_display,
            "next_due_date": str(res.next_due_date) if res.next_due_date else "",
            "next_due_date_display": res.next_due_date_display,
            "due_status_display": res.due_status_display,
            "status": res.status,
            "occupation": res.occupation,
            "monthly_payment_day": res.monthly_payment_day,
            "is_in_debt": res.is_in_debt,
            "overdue_days": res.overdue_days,
            "days_until_due": res.days_until_due,
            "unpaid_months": res.unpaid_months_display,
            "total_debt_tomans": res.total_debt_amount_tomans,
            "financial_summary": res.financial_status_summary,
            "has_paid_this_month": res.has_paid_this_month(),
            "has_incomplete_profile": res.has_incomplete_profile,
            "missing_profile_fields": res.missing_profile_fields,
            "profile_status": res.profile_completion_status,
            "has_deposit": res.has_deposit,
            "has_lease": res.has_lease,
            "has_id_card_image": res.has_id_card_image,
            "id_images_count": res.uploaded_id_images_count,
            "id_card_image_url": res.id_card_image.url if res.id_card_image else None,
            "id_card_image_2_url": res.id_card_image_2.url if res.id_card_image_2 else None,
            "id_card_image_3_url": res.id_card_image_3.url if res.id_card_image_3 else None,
        })

    # 4. Transactions
    transactions_qs = Transaction.objects.select_related('resident', 'dormitory').order_by('-payment_date')
    transactions_data = []
    for t in transactions_qs:
        date_str = ""
        if t.payment_date:
            if hasattr(t.payment_date, 'strftime'):
                date_str = t.payment_date.strftime('%Y/%m/%d %H:%M')
            else:
                date_str = str(t.payment_date)

        transactions_data.append({
            "id": t.id,
            "resident": {
                "id": t.resident.id,
                "full_name": t.resident.full_name,
            } if t.resident else {"id": 0, "full_name": "نامشخص"},
            "dormitory": t.dormitory.name if t.dormitory else "",
            "amount": t.amount,
            "amount_toman": t.amount // 10,
            "transaction_type": t.transaction_type,
            "payment_method": t.payment_method,
            "payment_date": date_str,
            "period_name": t.period_name or "",
            "period_start": str(t.period_start) if t.period_start else "",
            "period_end": str(t.period_end) if t.period_end else "",
            "reference_number": t.reference_number or "",
            "description": t.description or "",
            "is_approved": t.is_approved,
            "applicable_rent": t.applicable_rent or (t.resident.room.monthly_rent if t.resident and t.resident.room else 0)
        })

    # 5. Stats
    active_count = sum(1 for r in residents_data if r['status'] == 'ACTIVE')
    debt_count = sum(1 for r in residents_data if r['is_in_debt'] and r['status'] == 'ACTIVE')
    incomplete_count = sum(1 for r in residents_data if r['has_incomplete_profile'] and r['status'] == 'ACTIVE')
    full_rooms = sum(1 for r in rooms_data if r['current_occupants'] >= r['capacity'])
    # اتاق‌های دارای ظرفیت خالی (اتاق‌هایی که حداقل یک تخت خالی دارند):
    empty_rooms = sum(1 for r in rooms_data if r['current_occupants'] < r['capacity'])

    current_month_prefix = f"{today.year:04d}/{today.month:02d}"
    current_month_income = sum(
        t['amount'] for t in transactions_data
        if t['payment_date'].startswith(current_month_prefix)
    )

    stats = {
        "active_residents": active_count,
        "debt_residents": debt_count,
        "incomplete_residents": incomplete_count,
        "total_rooms": len(rooms_data),
        "full_rooms": full_rooms,
        "empty_rooms": empty_rooms,
        "current_month_income": current_month_income,
        "current_month_prefix": current_month_prefix,
    }

    return {
        "dorms": dorms,
        "rooms": rooms_data,
        "residents": residents_data,
        "transactions": transactions_data,
        "stats": stats,
    }


def get_student_dashboard_data(user):
    """Serialize real data for the logged-in student or a fallback student"""
    resident = None
    if user and user.is_authenticated:
        # Match by username or national_code
        resident = Resident.objects.filter(national_code=user.username).first()

    if not resident:
        # Fallback to first active resident with a room for demo/admin preview
        resident = Resident.objects.filter(status='ACTIVE', room__isnull=False).first() or Resident.objects.first()

    if not resident:
        return {
            "me": None,
            "roommates": [],
            "transactions": [],
            "maintenance": [],
            "monthlyHistory": {"labels": [], "values": []}
        }

    # Roommates (other residents in same room)
    roommates_data = []
    if resident.room:
        rm_qs = resident.room.residents.exclude(id=resident.id).filter(exit_date__isnull=True)
        for rm in rm_qs:
            roommates_data.append({
                "id": rm.id,
                "first_name": rm.first_name,
                "last_name": rm.last_name,
                "full_name": rm.full_name,
                "phone": rm.phone_number,
                "entry": str(rm.entry_date) if rm.entry_date else "",
                "national": rm.national_code,
                "me": False
            })
    # Add self to roommates
    roommates_data.append({
        "id": resident.id,
        "first_name": resident.first_name,
        "last_name": resident.last_name,
        "full_name": f"{resident.full_name} (شما)",
        "phone": resident.phone_number,
        "entry": str(resident.entry_date) if resident.entry_date else "",
        "national": resident.national_code,
        "me": True
    })

    # Student transactions
    trans_qs = resident.transactions.order_by('-payment_date')
    transactions_data = []
    month_totals = {}
    for t in trans_qs:
        d_str = t.payment_date.strftime('%Y/%m/%d') if hasattr(t.payment_date, 'strftime') else str(t.payment_date)
        t_toman = f"{t.amount // 10:,.0f} تومان"
        transactions_data.append({
            "type": t.transaction_type,
            "amount": t.amount,
            "toman": t_toman,
            "method": t.payment_method,
            "date": d_str,
            "ref": t.reference_number or "",
            "desc": t.description or "",
            "is_approved": t.is_approved
        })
        m_key = d_str[:7]
        month_totals[m_key] = month_totals.get(m_key, 0) + (t.amount // 10)

    # Monthly history for chart
    sorted_m = sorted(month_totals.keys())[-6:]
    monthly_history = {
        "labels": sorted_m,
        "values": [month_totals[m] for m in sorted_m]
    }

    me_data = {
        "id": resident.id,
        "first_name": resident.first_name,
        "last_name": resident.last_name,
        "full_name": resident.full_name,
        "national_code": resident.national_code,
        "phone_number": resident.phone_number,
        "parent_phone_number": resident.parent_phone_number or "-",
        "occupation": resident.occupation,
        "entry_date": str(resident.entry_date) if resident.entry_date else "",
        "monthly_payment_day": resident.monthly_payment_day,
        "status": resident.status,
        "is_in_debt": resident.is_in_debt,
        "overdue_days": resident.overdue_days,
        "days_until_due": resident.days_until_due,
        "unpaid_months": resident.unpaid_months_display,
        "total_debt_tomans": resident.total_debt_amount_tomans,
        "financial_summary": resident.financial_status_summary,
        "last_paid": resident.last_paid_period_display,
        "settled_until": str(resident.settled_until) if resident.settled_until else "ثبت نشده",
        "settled_until_display": resident.settled_until_display,
        "next_due_date": str(resident.next_due_date) if resident.next_due_date else "",
        "next_due_date_display": resident.next_due_date_display,
        "due_status_display": resident.due_status_display,
        "room": {
            "room_number": resident.room.room_number if resident.room else "تعیین‌نشده",
            "dormitory": resident.dormitory.name if resident.dormitory else "",
            "capacity": resident.room.capacity if resident.room else 0,
            "current_occupants": resident.room.current_occupants if resident.room else 0,
            "monthly_rent": resident.room.monthly_rent if resident.room else 0
        },
        "has_deposit": resident.has_deposit,
        "has_lease": resident.has_lease,
        "contract": {
            "number": f"RES-{resident.id:04d}",
            "start": str(resident.entry_date) if resident.entry_date else "-",
            "end": str(resident.exit_date) if resident.exit_date else "تمدید خودکار",
            "deposit_toman": "-",
            "has_deposit": resident.has_deposit,
            "has_lease": resident.has_lease,
        }
    }

    return {
        "me": me_data,
        "roommates": roommates_data,
        "transactions": transactions_data,
        "maintenance": [],
        "monthlyHistory": monthly_history
    }


class AdminDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/admin_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        data = get_admin_dashboard_data()
        ctx["dashboard_json"] = json.dumps(data, ensure_ascii=False)
        return ctx


class AdminDashboardDataApiView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        data = get_admin_dashboard_data()
        return JsonResponse(data, safe=False, json_dumps_params={'ensure_ascii': False})


class StudentDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/student_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        data = get_student_dashboard_data(self.request.user)
        ctx["student_json"] = json.dumps(data, ensure_ascii=False)
        ctx["student_data"] = data
        return ctx


class StudentDashboardDataApiView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        data = get_student_dashboard_data(request.user)
        return JsonResponse(data, safe=False, json_dumps_params={'ensure_ascii': False})