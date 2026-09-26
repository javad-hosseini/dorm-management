from django.urls import path
from .views import StudentLoginView, StudentLogoutView, StudentPasswordChangeView

app_name = "accounts"

urlpatterns = [
    path("login/", StudentLoginView.as_view(), name="login"),
    path("logout/", StudentLogoutView.as_view(), name="logout"),
    path("password-change/", StudentPasswordChangeView.as_view(), name="password_change"),
]
