from django.core.management.base import BaseCommand
from django.db import transaction
from finance.models import BankTransaction, TransactionAuditLog
from people.models import Supporter

class Command(BaseCommand):
    help = 'Backfills handled_by and created_by for historical transactions to restore edit access.'

    def handle(self, *args, **options):
        # 1. Backfill BankTransaction.handled_by
        txns_to_update = BankTransaction.objects.filter(
            handled_by__isnull=True
        ).exclude(match_status=BankTransaction.MatchStatus.UNMATCHED).select_related('batch')
        
        updated_txns = 0
        with transaction.atomic():
            for txn in txns_to_update:
                # Try to get from Audit Log first
                log = TransactionAuditLog.objects.filter(
                    transaction=txn, 
                    action=TransactionAuditLog.Action.MATCHED
                ).order_by('-timestamp').first()
                
                if log and log.actor:
                    txn.handled_by = log.actor
                elif txn.batch and txn.batch.uploaded_by:
                    # Fallback to the person who uploaded the batch
                    txn.handled_by = txn.batch.uploaded_by
                    
                if txn.handled_by:
                    txn.save(update_fields=['handled_by'])
                    updated_txns += 1
                    
        # 2. Backfill Supporter.created_by
        supporters_to_update = Supporter.objects.filter(created_by__isnull=True)
        updated_supporters = 0
        
        with transaction.atomic():
            for supporter in supporters_to_update:
                if supporter.assigned_agent:
                    supporter.created_by = supporter.assigned_agent
                    supporter.save(update_fields=['created_by'])
                    updated_supporters += 1
                else:
                    # Look for the first person who matched a transaction to this supporter
                    first_txn = BankTransaction.objects.filter(
                        matched_supporter=supporter,
                        handled_by__isnull=False
                    ).first()
                    if first_txn:
                        supporter.created_by = first_txn.handled_by
                        supporter.save(update_fields=['created_by'])
                        updated_supporters += 1
                        
        self.stdout.write(self.style.SUCCESS(f"Successfully backfilled {updated_txns} transactions and {updated_supporters} supporters!"))
