import json
from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_protect
from django.apps import apps
from django.contrib import messages
import jdatetime

from apps.dormitory.models import Dormitory
from apps.dormitory.services.ai_loader import (
    get_deepseek_prompt_template,
    preview_events,
    execute_events,
)


def get_current_supervisor(request):
    """Resolve current supervisor from logged-in user"""
    Supervisor = apps.get_model('accounts', 'Supervisor')
    supervisor = (
        Supervisor.objects.filter(id=request.user.id).first()
        or Supervisor.objects.filter(national_code=getattr(request.user, 'username', '')).first()
        or Supervisor.objects.first()
    )
    if not supervisor:
        supervisor = Supervisor.objects.create(
            first_name="مدیر",
            last_name="خوابگاه",
            national_code="0000000000"
        )
    return supervisor


@staff_member_required
@csrf_protect
def ai_daily_loader_view(request):
    """
    Interactive AI Daily Log Loader for Dormitory Supervisor.
    Allows pasting LLM-generated JSON, previewing matches, editing fields, and committing batch updates.
    """
    supervisor = get_current_supervisor(request)
    dormitories = Dormitory.objects.all()
    selected_dorm = dormitories.first()

    dorm_id = request.GET.get('dormitory_id') or request.POST.get('dormitory_id')
    if dorm_id:
        selected_dorm = dormitories.filter(id=dorm_id).first() or selected_dorm

    # Handle AJAX API actions
    if request.method == 'POST':
        content_type = request.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            try:
                body = json.loads(request.body.decode('utf-8'))
            except Exception as e:
                return JsonResponse({'success': False, 'error': f'JSON نامعتبر: {str(e)}'}, status=400)
        else:
            body = request.POST

        action = body.get('action')

        # 1. PREVIEW ACTION
        if action == 'preview':
            payload = body.get('payload')
            if not payload:
                return JsonResponse({'success': False, 'error': 'محتوای JSON ارسال نشده است.'}, status=400)

            result = preview_events(payload, supervisor, selected_dorm)
            return JsonResponse(result)

        # 2. EXECUTE ACTION
        elif action == 'execute':
            events_data = body.get('events')
            if isinstance(events_data, str):
                try:
                    events_data = json.loads(events_data)
                except Exception as e:
                    return JsonResponse({'success': False, 'error': f'خطا در ساختار وقایع: {str(e)}'}, status=400)

            if not isinstance(events_data, list) or not events_data:
                return JsonResponse({'success': False, 'error': 'هیچ رویدادی برای ثبت ارسال نشده است.'}, status=400)

            try:
                result = execute_events(events_data, supervisor, selected_dorm)
                return JsonResponse(result)
            except Exception as e:
                return JsonResponse({'success': False, 'error': f'خطای دیتابیس در ثبت اتمیک: {str(e)}'}, status=500)

        return JsonResponse({'success': False, 'error': 'عملیات نامعتبر است.'}, status=400)

    # GET Request: Prepare view context
    today = jdatetime.date.today()
    prompt_text = get_deepseek_prompt_template(today)

    context = {
        'title': 'ثبت هوشمند وقایع روزانه با هوش مصنوعی (لاگ صوتی)',
        'site_title': 'مدیریت خوابگاه',
        'site_header': 'سامانه خوابگاه نوید',
        'supervisor': supervisor,
        'dormitories': dormitories,
        'selected_dormitory': selected_dorm,
        'prompt_text': prompt_text,
        'today_jalali': f"{today.year:04d}/{today.month:02d}/{today.day:02d}",
        'today_jalali_display': f"{today.day} {today.j_months_fa[today.month - 1]} {today.year}",
    }

    return render(request, 'admin/dormitory/ai_loader.html', context)
