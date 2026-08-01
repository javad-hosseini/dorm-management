# apps/dashboard/urls.py
from django.urls import path
from .views import DashboardView



urlpatterns = [path("admin/", DashboardView.as_view(), name="dashboard")]