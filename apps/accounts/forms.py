from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.utils.translation import gettext_lazy as _
from .backends import normalize_input_digits


class StudentLoginForm(forms.Form):
    """Clean and secure login form with Persian digit normalization"""
    username = forms.CharField(
        label=_("کد ملی یا شماره همراه"),
        max_length=50,
        widget=forms.TextInput(
            attrs={
                'class': 'auth-input',
                'placeholder': 'مثال: 0012345678 یا 09123456789',
                'autocomplete': 'username',
                'dir': 'ltr',
                'id': 'username_field',
            }
        ),
    )
    password = forms.CharField(
        label=_("کلمه عبور"),
        widget=forms.PasswordInput(
            attrs={
                'class': 'auth-input',
                'placeholder': '••••••••',
                'autocomplete': 'current-password',
                'dir': 'ltr',
                'id': 'password_field',
            }
        ),
    )
    remember_me = forms.BooleanField(
        required=False,
        initial=True,
        label=_("مرا به خاطر بسپار"),
        widget=forms.CheckboxInput(
            attrs={
                'class': 'auth-checkbox',
                'id': 'remember_me_field',
            }
        ),
    )

    def clean_username(self):
        username = self.cleaned_data.get('username', '')
        return normalize_input_digits(username)


class StudentPasswordChangeForm(PasswordChangeForm):
    """Customized password change form with RTL styling and Persian labels"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'auth-input',
                'dir': 'ltr',
            })
