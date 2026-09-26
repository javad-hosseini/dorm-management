from django.core.management.base import BaseCommand
from apps.dormitory.models import Resident


class Command(BaseCommand):
    help = "Provision and link Django User accounts for all dormitory residents who do not have one"

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-passwords',
            action='store_true',
            help='Reset passwords of existing accounts to their national_code/phone_number',
        )

    def handle(self, *args, **options):
        reset_passwords = options.get('reset_passwords', False)
        residents = Resident.objects.all()

        linked_count = 0
        created_count = 0
        skipped_count = 0

        self.stdout.write(f"Checking accounts for {residents.count()} residents...")

        for res in residents:
            username = (res.national_code or res.phone_number or "").strip()
            if not username:
                skipped_count += 1
                continue

            if not res.user:
                try:
                    user = res.ensure_user_account()
                    if user:
                        created_count += 1
                except Exception as e:
                    self.stderr.write(f"Error provisioning user for resident #{res.id}: {e}")
            else:
                linked_count += 1
                if reset_passwords:
                    res.user.set_password(username)
                    res.user.save()

        self.stdout.write(
            f"Finished! Created/Linked: {created_count}, Already had accounts: {linked_count}, Skipped: {skipped_count}."
        )
