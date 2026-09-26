"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include


from apps.dormitory.views import ai_daily_loader_view, export_debtors_excel_view
from django.conf import settings
from django.conf.urls.static import static

from django.shortcuts import redirect
from django.http import JsonResponse
from django.db import connection


def health_check_view(request):
    try:
        connection.ensure_connection()
        return JsonResponse({"status": "ok", "database": "connected"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=503)


urlpatterns = [
    path('', lambda request: redirect('accounts:login'), name='root'),
    path('health/', health_check_view, name='health_check'),
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),
    path('dashboard/', include('apps.dashboard.urls'), name="dashboard"),
    path('i18n/', include('django.conf.urls.i18n')),
    path('admin/ai-loader/', ai_daily_loader_view, name='ai_daily_loader'),
    path('admin/export-debtors-excel/', export_debtors_excel_view, name='admin_export_debtors_excel'),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

