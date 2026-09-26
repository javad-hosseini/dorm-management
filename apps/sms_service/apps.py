from django.apps import AppConfig


class SmsServiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sms_service'
    label = 'sms_service'
    verbose_name = 'مدیریت پیامک'

