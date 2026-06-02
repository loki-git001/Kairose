from django.db import transaction
from django.db.utils import IntegrityError
from finance.parsers import get_parser_class
from finance.models import BankTransaction, StatementImportBatch, LedgerAllocation, TransactionAuditLog
from people.models import SupporterIdentifier


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

        # Trigger the Auto-Matcher immediately after ingestion
        matches_found = run_auto_matcher(batch.id)
        print(f"Batch {batch.id} processed. Auto-matched {matches_found} transactions.")
            
    except IntegrityError:
        batch.status = StatementImportBatch.Status.FAILED
        batch.save()
    except Exception as e:
        batch.status = StatementImportBatch.Status.FAILED
        batch.save()



# ====================================
# Auto Matcher
# ====================================

def run_auto_matcher(batch_id):
    """
    Scans a batch for unmatched transactions. If the extracted_identifier matches
    a VERIFIED SupporterIdentifier, it auto-allocates the funds and writes an audit log.
    """
    # 1. Get transactions that need matching and actually have an extracted identifier
    unmatched_txns = BankTransaction.objects.filter(
        batch_id=batch_id,
        match_status=BankTransaction.MatchStatus.UNMATCHED
    ).exclude(extracted_identifier__exact='')

    if not unmatched_txns.exists():
        return 0  # Nothing to match

    # 2. Extract unique identifiers to query the database efficiently (O(1) lookup prep)
    unique_identifiers = set(unmatched_txns.values_list('extracted_identifier', flat=True))

    # 3. Fetch ONLY verified identifiers from the database
    verified_qs = SupporterIdentifier.objects.filter(
        value__in=unique_identifiers,
        is_verified=True
    ).values('value', 'supporter_id')

    # 4. Build an in-memory hash map and detect AMBIGUOUS cases
    # If a husband and wife share a bank account, it will flag as ambiguous for agents to resolve.
    identifier_map = {}
    ambiguous_identifiers = set()

    for item in verified_qs:
        val = item['value']
        sup_id = item['supporter_id']
        
        if val in identifier_map and identifier_map[val] != sup_id:
            ambiguous_identifiers.add(val)
        else:
            identifier_map[val] = sup_id

    # Remove ambiguous identifiers from the safe map
    for ambig_val in ambiguous_identifiers:
        if ambig_val in identifier_map:
            del identifier_map[ambig_val]

    # 5. Prepare the data for bulk updates
    txns_to_update = []
    allocations_to_create = []
    logs_to_create = []

    for txn in unmatched_txns:
        ident = txn.extracted_identifier
        
        if ident in ambiguous_identifiers:
            # Flag for human review
            txn.match_status = BankTransaction.MatchStatus.AMBIGUOUS
            txns_to_update.append(txn)
            
        elif ident in identifier_map:
            # We have a strict, verified 1:1 match
            supporter_id = identifier_map[ident]
            
            # Update Transaction
            txn.match_status = BankTransaction.MatchStatus.AUTO_MATCHED
            txn.matched_supporter_id = supporter_id
            txns_to_update.append(txn)
            
            # Create Ledger Allocation (Default assumption: Auto-matches are straight Donations)
            allocations_to_create.append(
                LedgerAllocation(
                    transaction=txn,
                    supporter_id=supporter_id,
                    purpose=LedgerAllocation.Purpose.DONATION,
                    amount=txn.amount
                )
            )
            
            # Create Audit Log (Notice actor is None, representing the System)
            logs_to_create.append(
                TransactionAuditLog(
                    transaction=txn,
                    actor=None, 
                    action=TransactionAuditLog.Action.AUTO_MATCHED,
                    notes="System auto-matched based on verified identifier.",
                    new_supporter_id=supporter_id
                )
            )

    # 6. Execute all database changes atomically
    if txns_to_update:
        with transaction.atomic():
            # Update all transaction statuses in one trip
            BankTransaction.objects.bulk_update(
                txns_to_update, 
                ['match_status', 'matched_supporter_id']
            )
            # Create all ledger records in one trip
            LedgerAllocation.objects.bulk_create(allocations_to_create)
            # Create all audit logs in one trip
            TransactionAuditLog.objects.bulk_create(logs_to_create)

    # Return the number of successfully auto-matched records
    return len(allocations_to_create)