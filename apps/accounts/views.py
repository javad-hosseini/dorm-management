from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.shortcuts import render, redirect
from django.urls import reverse_lazy, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import FormView

from .forms import StudentLoginForm, StudentPasswordChangeForm


class StudentLoginView(FormView):
    """
    Dedicated Persian login view for dormitory residents and staff.
    Supports login via National Code, Foreign Passport, or Phone Number.
    """
    template_name = "accounts/login.html"
    form_class = StudentLoginForm

    def dispatch(self, request, *args, **kwargs):
        # If user is already authenticated, redirect to appropriate dashboard
        if request.user.is_authenticated:
            return self.get_success_redirect(request.user)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        remember_me = form.cleaned_data.get('remember_me', True)

        user = authenticate(self.request, username=username, password=password)

        if user is not None:
            if not user.is_active:
                form.add_error(None, "این حساب کاربری غیرفعال شده است. لطفاً با مدیریت خوابگاه تماس بگیرید.")
                return self.form_invalid(form)

            auth_login(self.request, user)

            # Session duration
            if not remember_me:
                self.request.session.set_expiry(0)
            else:
                self.request.session.set_expiry(1209600)  # 2 weeks

            messages.success(self.request, f"خوش آمدید، {user.get_full_name() or user.username}!")
            return self.get_success_redirect(user)
        else:
            form.add_error(None, "کد ملی / شماره همراه یا کلمه عبور وارد شده نادرست است.")
            return self.form_invalid(form)

    def get_success_redirect(self, user):
        next_url = self.request.GET.get('next') or self.request.POST.get('next')
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}):
            return redirect(next_url)

        if user.is_staff or user.is_superuser:
            return redirect("dashboard:admin")
        return redirect("dashboard:student")


class StudentLogoutView(View):
    """Secure logout view with session invalidation"""
    def get(self, request, *args, **kwargs):
        return self.handle_logout(request)

    def post(self, request, *args, **kwargs):
        return self.handle_logout(request)

    def handle_logout(self, request):
        if request.user.is_authenticated:
            auth_logout(request)
            messages.info(request, "شما با موفقیت از سامانه خارج شدید.")
        return redirect("accounts:login")


class StudentPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """Change password view for authenticated residents"""
    template_name = "accounts/password_change.html"
    form_class = StudentPasswordChangeForm
    success_url = reverse_lazy("dashboard:student")

    def form_valid(self, form):
        response = super().form_valid(form)
        # Prevent logging out the user after password change
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, "کلمه عبور شما با موفقیت تغییر یافت.")
        return response
