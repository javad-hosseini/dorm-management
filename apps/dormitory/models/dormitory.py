from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from .resident import Resident


class Dormitory(models.Model):
    """Represents a physical dormitory building"""
    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Dormitory Name"
    )
    address = models.TextField(verbose_name="Address")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dormitory"
        verbose_name_plural = "Dormitories"
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def total_rooms(self):
        """Total number of rooms in this dormitory"""
        return self.rooms.count()  # type: ignore

    @property
    def occupied_rooms(self):
        """Number of rooms that have at least one resident"""
        return self.rooms.filter(  # type: ignore
            residents__exit_date__isnull=True
        ).distinct().count()

    @property
    def empty_rooms(self):
        """Number of completely empty rooms"""
        return self.rooms.exclude(  # type: ignore
            residents__exit_date__isnull=True
        ).count()

    @property
    def total_active_residents(self):
        """Total active residents in this dormitory"""
        from .resident import Resident  # Lazy import
        return Resident.objects.filter(
            dormitory=self,
            exit_date__isnull=True,
            status='ACTIVE'
        ).count()
