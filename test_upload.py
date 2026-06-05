import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from finance.models import StatementImportBatch, CharityBankAccount
from django.core.files.uploadedfile import SimpleUploadedFile
from finance.services import process_statement_batch

# Find the bank account
account = CharityBankAccount.objects.first()

# Create a mock batch
try:
    batch = StatementImportBatch.objects.create(
        bank_account=account,
        file_reference="bank_statements/2026/06/CustomAccountStatement03-06-2026_NTcC9aO.xls", # The file they tried to upload
    )
    print(f"Batch created with number: {batch.batch_number}")
    process_statement_batch(batch.id)
    print(f"Batch status after processing: {batch.status}")
except Exception as e:
    import traceback
    traceback.print_exc()
