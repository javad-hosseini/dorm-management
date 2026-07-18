from django.apps import AppConfig

class DormitoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.dormitory'  # Important: Full path to the app
    verbose_name = 'Dormitory Management'