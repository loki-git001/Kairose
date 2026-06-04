from django.contrib import admin
from .models import (
    StatementImportBatch,
    BankTransaction,
    LedgerAllocation,
    TransactionAuditLog,
    CharityBankAccount
)

# ==========================================
# INLINES
# ==========================================


class LedgerAllocationInline(admin.TabularInline):
    model = LedgerAllocation
    extra = 0
    raw_id_fields = ("supporter",)


class TransactionAuditLogInline(admin.TabularInline):
    model = TransactionAuditLog
    extra = 0
    can_delete = False
    readonly_fields = (
        "actor",
        "action",
        "timestamp",
        "notes",
        "previous_supporter_id",
        "new_supporter_id",
    )

    # Prevent adding audit logs manually via the inline
    def has_add_permission(self, request, obj=None):
        return False


# ==========================================
# MODEL ADMINS
# ==========================================


@admin.register(CharityBankAccount)
class CharityBankAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "account_number", "currency", "parser_type", "is_active")
    list_filter = ("parser_type", "currency", "is_active")
    search_fields = ("name", "account_number")
    list_editable = ("is_active",)


@admin.register(StatementImportBatch)
class StatementImportBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'bank_account', 'uploaded_by', 'uploaded_at', 'status', 'total_rows')
    list_filter = ('status', 'bank_account', 'uploaded_at')
    readonly_fields = ('uploaded_at',)


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "bank_reference",
        "transaction_date",
        "amount",
        "transaction_mode",
        "match_status",
        "matched_supporter",
    )
    list_filter = ("match_status", "transaction_mode", "transaction_date")
    search_fields = (
        "bank_reference",
        "raw_narration",
        "extracted_identifier",
        "matched_supporter__first_name",
    )
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("matched_supporter", "batch")

    fieldsets = (
        (
            "Bank Record (Immutable)",
            {
                "fields": (
                    "id",
                    "batch",
                    "transaction_date",
                    "amount",
                    "bank_reference",
                    "raw_narration",
                )
            },
        ),
        (
            "Extraction Data",
            {"fields": ("transaction_mode", "extracted_identifier", "extracted_name")},
        ),
        (
            "Matching State",
            {"fields": ("match_status", "matched_supporter", "created_at")},
        ),
    )
    inlines = [LedgerAllocationInline, TransactionAuditLogInline]


@admin.register(LedgerAllocation)
class LedgerAllocationAdmin(admin.ModelAdmin):
    list_display = ("id", "transaction", "supporter", "purpose", "amount")
    list_filter = ("purpose", "created_at")
    search_fields = (
        "transaction__bank_reference",
        "supporter__first_name",
        "supporter__last_name",
    )
    raw_id_fields = ("transaction", "supporter")
    readonly_fields = ("id", "created_at")


@admin.register(TransactionAuditLog)
class TransactionAuditLogAdmin(admin.ModelAdmin):
    list_display = ("transaction", "actor", "action", "timestamp")
    list_filter = ("action", "timestamp")
    search_fields = ("transaction__bank_reference", "actor__username")

    # SECURITY: Make the Audit Log strictly read-only in the Admin
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
