# finance/models.py
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import uuid

# Cross-app imports
from people.models import Supporter


class CharityBankAccount(models.Model):
    class ParserType(models.TextChoices):
        FEDERAL_BANK = "FEDERAL", _("Federal Bank")
        PAYPAL = "PAYPAL", _("PayPal")
        VANCO = "VANCO", _("Vanco")
        BANK_OF_AMERICA = "BOA", _("Bank of America")
        NRI = "NRI", _("NRI Account")

    name = models.CharField(max_length=100)  # e.g., "Federal Bank Savings"
    account_number = models.CharField(max_length=50, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    parser_type = models.CharField(max_length=50, choices=ParserType.choices)
    is_active = models.BooleanField(
        default=True,
        help_text=_("Uncheck to hide closed accounts from the upload menu."),
    )

    @property
    def get_auto_prefix(self):
        ptype = self.parser_type
        name_lower = self.name.lower()
        if ptype == self.ParserType.FEDERAL_BANK:
            if 'current' in name_lower:
                return 'FBC'
            elif 'saving' in name_lower:
                return 'FBS'
            return 'FBD' # Default Federal Bank
        elif ptype == self.ParserType.BANK_OF_AMERICA:
            return 'BOA'
        elif ptype == self.ParserType.NRI:
            return 'NRI'
        elif ptype == self.ParserType.PAYPAL:
            return 'PPL'
        elif ptype == self.ParserType.VANCO:
            return 'VCO'
        raise ValueError("Invalid parser type") # Global fallback

    def __str__(self):
        return f"{self.name} - {self.account_number} ({self.currency})"


class StatementImportBatch(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending Processing")
        PROCESSED = "PROCESSED", _("Processed Successfully")

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    bank_account = models.ForeignKey(
        CharityBankAccount,
        on_delete=models.PROTECT,
        related_name="import_batches",
        null=True,
        blank=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_reference = models.FileField(upload_to="bank_statements/%Y/%m/")
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.PENDING
    )
    total_rows = models.IntegerField(default=0)
    skipped_rows = models.IntegerField(default=0)
    batch_number = models.CharField(max_length=20, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.batch_number and self.bank_account:
            prefix = self.bank_account.get_auto_prefix
                
            count = StatementImportBatch.objects.filter(bank_account=self.bank_account).count()
            
            letter_idx = count // 999
            if letter_idx < 26:
                letter = chr(ord('A') + letter_idx)
            else:
                letter = "Z" # Fallback for extremely large numbers
            
            number = (count % 999) + 1
            self.batch_number = f"{prefix}{letter}{number:03d}"
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Batch {self.batch_number or self.id} - {self.uploaded_at.strftime('%Y-%m-%d')}"


class BankTransaction(models.Model):
    class TransactionMode(models.TextChoices):
        UPI = "UPI", _("UPI")
        NEFT = "NEFT", _("NEFT")
        RTGS = "RTGS", _("RTGS")
        IMPS = "IMPS", _("IMPS")
        MB = "MB", _("Mobile Banking")
        IB = "IB", _("Internet Banking")
        CASH = "CASH", _("Cash Deposit")
        CHEQUE = "CHEQUE", _("Cheque")
        UNKNOWN = "UNKNOWN", _("Unknown")

    class MatchStatus(models.TextChoices):
        UNMATCHED = "UNMATCHED", _("Unmatched")
        MATCHED = "MATCHED", _("Matched")
        IGNORED = "IGNORED", _("Ignored")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        StatementImportBatch, on_delete=models.CASCADE, related_name="transactions"
    )
    bank_account = models.ForeignKey(
        CharityBankAccount,
        on_delete=models.CASCADE,
        related_name="bank_transactions",
        null=True,
        blank=True,
    )

    transaction_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    bank_reference = models.CharField(max_length=100, db_index=True)
    raw_narration = models.TextField()

    transaction_mode = models.CharField(
        max_length=10, choices=TransactionMode.choices, default=TransactionMode.UNKNOWN
    )
    extracted_identifier = models.CharField(max_length=255, blank=True, default="")
    extracted_name = models.CharField(max_length=255, blank=True, default="")

    match_status = models.CharField(
        max_length=15, choices=MatchStatus.choices, default=MatchStatus.UNMATCHED
    )
    matched_supporter = models.ForeignKey(
        Supporter,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="bank_transactions",
    )
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handled_transactions",
        help_text=_("The agent who matched or ignored this transaction."),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-transaction_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["bank_account", "bank_reference", "amount", "transaction_date"],
                name="unique_bank_transaction",
            )
        ]
        indexes = [
            models.Index(fields=["match_status"]),
            models.Index(fields=["extracted_identifier"]),
        ]

    def __str__(self):
        return f"{self.transaction_date} - {self.bank_reference} - {self.amount}"


class LedgerAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(
        BankTransaction, on_delete=models.CASCADE, related_name="allocations"
    )
    supporter = models.ForeignKey(
        Supporter, on_delete=models.PROTECT, related_name="allocations"
    )

    purpose = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


class TransactionAuditLog(models.Model):
    class Action(models.TextChoices):
        IMPORTED = "IMPORTED", _("Statement Imported")
        MATCHED = "MATCHED", _("Transaction Matched")
        UNMATCHED = "UNMATCHED", _("Agent Unmatched")
        IGNORED = "IGNORED", _("Agent Ignored")
        ALLOCATION_CHANGED = "ALLOC_CHANGED", _("Allocation Changed")

    transaction = models.ForeignKey(
        BankTransaction, on_delete=models.CASCADE, related_name="audit_logs"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default="")

    previous_supporter_id = models.UUIDField(null=True, blank=True)
    new_supporter_id = models.UUIDField(null=True, blank=True)
