from django import forms


class SmsComposerForm(forms.Form):
    """
    Form for composing an SMS message in the admin panel.
    """

    message_body = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "class": "form-control",
                "id": "sms_message_body",
                "placeholder": "متن پیامک خود را اینجا بنویسید...",
                "style": "width: 100%; border-radius: 8px; font-family: inherit; padding: 12px; font-size: 1rem;",
            }
        ),
        label="متن پیامک",
        help_text="می‌توانید از متغیرهای هوشمند {نام}، {اتاق}، {موعد_تسویه}، {امروز}، {مبلغ_بدهی} و {روزهای_تاخیر} استفاده کنید.",
        required=True,
    )

    def clean_message_body(self):
        body = self.cleaned_data.get("message_body", "").strip()
        if not body:
            raise forms.ValidationError("متن پیامک نمی‌تواند خالی باشد.")
        if len(body) > 1000:
            raise forms.ValidationError("طول متن پیامک نمی‌تواند بیش از ۱۰۰۰ کاراکتر باشد.")
        return body

