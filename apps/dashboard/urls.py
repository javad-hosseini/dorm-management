from django.urls import path
from .views import (
    AdminDashboardView,
    AdminDashboardDataApiView,
    StudentDashboardView,
    StudentDashboardDataApiView,
    AdminBackupCreateView,
    AdminBackupListView,
    FinancialDashboardView,
    FinancialDashboardDataApiView,
)

app_name = "dashboard"

urlpatterns = [
    path("admin/", AdminDashboardView.as_view(), name="admin"),
    path("student/", StudentDashboardView.as_view(), name="student"),
    path("finance/", FinancialDashboardView.as_view(), name="finance"),
    path("api/admin-data/", AdminDashboardDataApiView.as_view(), name="api_admin_data"),
    path("api/student-data/", StudentDashboardDataApiView.as_view(), name="api_student_data"),
    path("api/finance-data/", FinancialDashboardDataApiView.as_view(), name="api_finance_data"),
    path("api/backup/create/", AdminBackupCreateView.as_view(), name="api_backup_create"),
    path("api/backup/list/", AdminBackupListView.as_view(), name="api_backup_list"),
]