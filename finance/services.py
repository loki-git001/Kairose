from django.db import transaction
from django.db.utils import IntegrityError
from finance.parsers import get_parser_class
from finance.models import BankTransaction, StatementImportBatch, LedgerAllocation, TransactionAuditLog
from people.models import SupporterIdentifier
from decimal import Decimal


import re

def extract_phone_from_upi(text: str) -> str | None:
    """
    Extracts exactly 10 continuous digits from a string.
    Returns the 10-digit phone number if found, otherwise None.
    """
    if not text:
        return None
    match = re.search(r'(?<!\d)\d{10}(?!\d)', text)
    if match:
        return match.group(0)
    return None

# ====================================
# Statement Processor
# ====================================

class DuplicateStatementError(Exception):
    pass


def process_statement_batch(batch_id):
    batch = StatementImportBatch.objects.get(id=batch_id)
    ParserClass = get_parser_class(batch.bank_account.parser_type)
    parser = ParserClass(file_path=batch.file_reference.path)
    
    try:
        parsed_data = parser.parse()
        if not parsed_data:
            return {"skipped_count": 0, "inserted_count": 0}
            
        # Get date range to optimize DB query
        min_date = min(row['transaction_date'] for row in parsed_data)
        max_date = max(row['transaction_date'] for row in parsed_data)
        
        # Fetch existing fingerprints within the date range
        existing_txs = BankTransaction.objects.filter(
            transaction_date__range=[min_date, max_date]
        ).values_list('bank_reference', 'amount', 'transaction_date')
        
        existing_fingerprints = set(existing_txs)
        
        transactions_to_create = []
        skipped_count = 0
        
        for row in parsed_data:
            # Convert float to Decimal with 2 places to perfectly match database types
            amount_decimal = Decimal(f"{row['amount']:.2f}")
            fingerprint = (row['bank_reference'], amount_decimal, row['transaction_date'])
            
            if fingerprint in existing_fingerprints:
                skipped_count += 1
            else:
                transactions_to_create.append(
                    BankTransaction(
                        batch=batch,
                        transaction_date=row['transaction_date'],
                        amount=row['amount'],
                        bank_reference=row['bank_reference'],
                        raw_narration=row.get('raw_narration', ''),
                        transaction_mode=row.get('transaction_mode', BankTransaction.TransactionMode.UNKNOWN),
                        extracted_identifier=row.get('extracted_identifier', ''),
                        extracted_name=row.get('extracted_name', ''),
                        match_status=BankTransaction.MatchStatus.UNMATCHED 
                    )
                )
                # Add to set to prevent duplicates within the same parsed file
                existing_fingerprints.add(fingerprint)
                
        if skipped_count > 0 and skipped_count == len(parsed_data):
            raise DuplicateStatementError("Cannot upload duplicate statement.")
            
        with transaction.atomic():
            if transactions_to_create:
                # Hit the database exactly ONE time
                BankTransaction.objects.bulk_create(transactions_to_create)
                
            batch.status = StatementImportBatch.Status.PROCESSED
            batch.total_rows = len(transactions_to_create)
            batch.save()

        # No longer triggering auto-matcher here since it is now a UI-based suggestion
        print(f"Batch {batch.id} processed.")
        return {"skipped_count": skipped_count, "inserted_count": len(transactions_to_create)}
            
    except DuplicateStatementError as e:
        batch.delete()
        raise e
    except IntegrityError as e:
        print(f"IntegrityError in batch {batch.id}: {e}")
        batch.delete()
        raise e
    except Exception as e:
        import traceback
        traceback.print_exc()
        batch.delete()
        raise e


