from django.urls import path
from .views import (
    AdminDashboardView,
    AdminDashboardDataApiView,
    StudentDashboardView,
    StudentDashboardDataApiView
)

app_name = "dashboard"

urlpatterns = [
    path("admin/", AdminDashboardView.as_view(), name="admin"),
    path("student/", StudentDashboardView.as_view(), name="student"),
    path("api/admin-data/", AdminDashboardDataApiView.as_view(), name="api_admin_data"),
    path("api/student-data/", StudentDashboardDataApiView.as_view(), name="api_student_data"),
]