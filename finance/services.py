from django.db import transaction
from django.db.utils import IntegrityError
from finance.parsers import get_parser_class
from finance.models import BankTransaction, StatementImportBatch, LedgerAllocation, TransactionAuditLog
from people.models import SupporterIdentifier


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

def process_statement_batch(batch_id):
    batch = StatementImportBatch.objects.get(id=batch_id)
    ParserClass = get_parser_class(batch.bank_account.parser_type)
    parser = ParserClass(file_path=batch.file_reference.path)
    
    try:
        parsed_data = parser.parse()
        transactions_to_create = []
        
        for row in parsed_data:
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
                    
                    # Default to UNMATCHED upon initial creation
                    match_status=BankTransaction.MatchStatus.UNMATCHED 
                )
            )
            
        with transaction.atomic():
            # Hit the database exactly ONE time
            BankTransaction.objects.bulk_create(transactions_to_create)
            
            batch.status = StatementImportBatch.Status.PROCESSED
            batch.total_rows = len(transactions_to_create)
            batch.save()

        # No longer triggering auto-matcher here since it is now a UI-based suggestion
        print(f"Batch {batch.id} processed.")
            
    except IntegrityError:
        batch.status = StatementImportBatch.Status.FAILED
        batch.save()
    except Exception as e:
        batch.status = StatementImportBatch.Status.FAILED
        batch.save()


