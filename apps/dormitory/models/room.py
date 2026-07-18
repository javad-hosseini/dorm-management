from django.core.validators import MinValueValidator
from django.db import models


class Room(models.Model):
    """Represents a room within a dormitory"""
    dormitory = models.ForeignKey(
        'dormitory.Dormitory',  # String reference - no import needed
        on_delete=models.CASCADE,
        related_name='rooms'
    )
    room_number = models.IntegerField()
    capacity = models.SmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Maximum number of residents allowed"
    )
    monthly_rent = models.PositiveIntegerField(
        default=0,
        help_text="Monthly rent amount in local currency"
    )

    class Meta:
        verbose_name = "Room"
        verbose_name_plural = "Rooms"
        unique_together = [['dormitory', 'room_number']]
        ordering = ['dormitory', 'room_number']

    def __str__(self):
        return f"{self.dormitory.name} - Room {self.room_number}"

    @property
    def current_occupants(self) -> int:
        """Returns count of current active residents"""
        return self.residents.filter(  # type: ignore[attr-defined]
            exit_date__isnull=True
        ).count()

    @property
    def available_capacity(self) -> int:
        """How many more residents can be added"""
        return max(0, self.capacity - self.current_occupants)

    @property
    def is_full(self) -> bool:
        """Check if room is at full capacity"""
        return self.current_occupants >= self.capacity

    @property
    def is_empty(self) -> bool:
        """Check if room has no residents"""
        return self.current_occupants == 0

    def get_current_residents(self):
        """Get list of current active residents"""
        return self.residents.filter(  # type: ignore[attr-defined]
            exit_date__isnull=True
        )
