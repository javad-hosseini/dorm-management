from django.contrib import admin
from .models import Supervisor


@admin.register(Supervisor)
class SupervisorAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'national_code']
    search_fields = ['first_name', 'last_name', 'national_code']