from django.urls import path
from .views import AdminDashboardView, StudentDashboardView

app_name = "dashboard"

urlpatterns = [
    path("admin/", AdminDashboardView.as_view(), name="admin"),
    path("student/", StudentDashboardView.as_view(), name="student"),
]