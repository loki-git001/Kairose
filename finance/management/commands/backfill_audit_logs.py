from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from finance.models import BankTransaction, TransactionAuditLog

class Command(BaseCommand):
    help = 'Backfills TransactionAuditLogs for transactions that have handled_by but no corresponding log.'

    def handle(self, *args, **options):
        # Find transactions that have handled_by
        handled_txns = BankTransaction.objects.filter(handled_by__isnull=False)
        
        created_count = 0
        with transaction.atomic():
            for txn in handled_txns:
                # Check if an audit log exists for this action
                if txn.match_status == BankTransaction.MatchStatus.MATCHED:
                    action_type = TransactionAuditLog.Action.MATCHED
                elif txn.match_status == BankTransaction.MatchStatus.IGNORED:
                    action_type = TransactionAuditLog.Action.IGNORED
                else:
                    continue # UNMATCHED shouldn't have handled_by, but if it does, ignore for backfill
                    
                has_log = TransactionAuditLog.objects.filter(
                    transaction=txn,
                    actor=txn.handled_by,
                    action=action_type
                ).exists()
                
                if not has_log:
                    TransactionAuditLog.objects.create(
                        transaction=txn,
                        actor=txn.handled_by,
                        action=action_type,
                        notes=f"System backfill: {action_type.label}"
                    )
                    # We can't strictly control auto_now_add for historical accuracy easily without updating the DB directly,
                    # but since this is for recent data, current timestamp is acceptable.
                    created_count += 1
                    
        self.stdout.write(self.style.SUCCESS(f"Successfully created {created_count} missing audit logs."))
