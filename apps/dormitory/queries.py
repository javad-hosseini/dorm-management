# queries.py - Useful queries for reports
from apps.dormitory.models import Transaction


class ReportQueries:
    """Collection of common report queries"""

    @staticmethod
    def get_total_income(start_date, end_date):
        """Total income in any date range"""
        return Transaction.objects.filter(
            payment_date__gte=start_date,
            payment_date__lte=end_date
        ).aggregate(
            total=Sum('amount')
        )['total'] or 0

    @staticmethod
    def get_income_by_dormitory(start_date, end_date):
        """Total income grouped by dormitory"""
        return Transaction.objects.filter(
            payment_date__gte=start_date,
            payment_date__lte=end_date
        ).values(
            'dormitory__name'
        ).annotate(
            total_income=Sum('amount')
        ).order_by('-total_income')

    @staticmethod
    def get_income_by_resident(start_date, end_date):
        """Total income grouped by resident"""
        return Transaction.objects.filter(
            payment_date__gte=start_date,
            payment_date__lte=end_date
        ).values(
            'resident__first_name',
            'resident__last_name'
        ).annotate(
            total_paid=Sum('amount')
        ).order_by('-total_paid')

    @staticmethod
    def get_residents_not_paid_recently(days=30):
        """Residents who haven't paid in the last N days"""
        recent_date = date.today() - timedelta(days=days)
        paid_residents = Transaction.objects.filter(
            payment_date__gte=recent_date,
            transaction_type='RENT'
        ).values_list('resident_id', flat=True)

        return Resident.objects.filter(
            status=Resident.Status.ACTIVE
        ).exclude(
            id__in=paid_residents
        )

    @staticmethod
    def get_occupied_rooms():
        """Get all rooms that have residents"""
        return Room.objects.filter(
            residents__exit_date__isnull=True
        ).distinct()

    @staticmethod
    def get_empty_rooms():
        """Get all completely empty rooms"""
        return Room.objects.exclude(
            residents__exit_date__isnull=True
        )

    @staticmethod
    def get_room_occupancy_summary():
        """Summary of room occupancy"""
        return Room.objects.annotate(
            occupant_count=Count(
                'residents',
                filter=Q(residents__exit_date__isnull=True)
            )
        ).values(
            'id', 'dormitory__name', 'room_number', 'capacity', 'occupant_count'
        )