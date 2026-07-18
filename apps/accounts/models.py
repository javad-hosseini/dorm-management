# models/supervisor.py
from django.db import models


class Supervisor(models.Model):
    """Dormitory supervisors who manage the system"""
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    national_code = models.CharField(
        max_length=10,
        unique=True
    )

    # Password will be handled by Django User model later
    # For MVP, we'll use Django's built-in auth

    class Meta:
        verbose_name = "Supervisor"
        verbose_name_plural = "Supervisors"
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        """Return full name of supervisor"""
        return f"{self.first_name} {self.last_name}"