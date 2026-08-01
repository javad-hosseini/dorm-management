from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin


class AdminDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/admin_dashboard.html"


class StudentDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/student_dashboard.html"