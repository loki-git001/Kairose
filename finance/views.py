from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import CreateView, FormView, ListView

from .forms import StatementUploadForm, TransactionMatchForm
from .models import (
    BankTransaction,
    LedgerAllocation,
    StatementImportBatch,
    TransactionAuditLog,
)
from .services import process_statement_batch


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_active and (self.request.user.is_staff or self.request.user.is_superuser)



@method_decorator(never_cache, name='dispatch')
class StatementUploadView(AdminRequiredMixin, FormView):
    """
    Admin-only view to upload bank statements.
    """
    template_name = 'finance/upload_statement.html'
    form_class = StatementUploadForm
    success_url = reverse_lazy('finance:upload_statement')

    def form_valid(self, form):
        bank_account = form.cleaned_data['bank_account']
        file = form.cleaned_data['file']
        
        # 1. Create the initial batch record
        batch = StatementImportBatch.objects.create(
            uploaded_by=self.request.user,
            bank_account=bank_account,
            file_reference=file,
            status=StatementImportBatch.Status.PENDING
        )
        
        # 2. TRIGGER THE SERVICE LAYER
        # This will parse, ingest, auto-match, and update the batch status.
        process_statement_batch(batch.id)
        
        # 3. Smart Feedback
        # Refresh the batch from the database to see what the service did to it
        batch.refresh_from_db()
        
        if batch.status == StatementImportBatch.Status.PROCESSED:
            messages.success(
                self.request, 
                f"Success! Batch #{batch.id} processed. {batch.total_rows} transactions imported and auto-matched where possible."
            )
        else:
            messages.error(
                self.request, 
                f"Batch #{batch.id} failed to process. Please verify the Excel sheet matches the {bank_account.get_parser_type_display()} format."
            )

        return super().form_valid(form)


@method_decorator(never_cache, name='dispatch')
class AgentPendingTransactionsView(LoginRequiredMixin, ListView):
    """
    Agents view all system-wide transactions that are unmatched or ambiguous.
    """
    model = BankTransaction
    template_name = 'finance/pending_transactions.html'
    context_object_name = 'transactions'

    def get_queryset(self):
        # Global Ledger Visibility: Agents can see all unmatched transactions system-wide
        return BankTransaction.objects.filter(
            match_status__in=[BankTransaction.MatchStatus.UNMATCHED, BankTransaction.MatchStatus.AMBIGUOUS]
        ).select_related('batch__bank_account')


@method_decorator(never_cache, name='dispatch')
class TransactionMatchView(LoginRequiredMixin, CreateView):
    """
    View for agents to manually match a transaction to one of their assigned supporters.
    """
    model = LedgerAllocation
    form_class = TransactionMatchForm
    template_name = 'finance/transaction_match.html'
    success_url = reverse_lazy('finance:pending_transactions')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transaction'] = get_object_or_404(BankTransaction, pk=self.kwargs['transaction_id'])
        return context

    def get_initial(self):
        initial = super().get_initial()
        # Default the amount to the transaction amount
        txn = get_object_or_404(BankTransaction, pk=self.kwargs['transaction_id'])
        initial['amount'] = txn.amount
        return initial

    def form_valid(self, form):
        txn = get_object_or_404(BankTransaction, pk=self.kwargs['transaction_id'])
        
        with transaction.atomic():
            # 1. Create the LedgerAllocation
            allocation = form.save(commit=False)
            allocation.transaction = txn
            allocation.save()

            # 2. Update BankTransaction
            txn.match_status = BankTransaction.MatchStatus.MANUAL_MATCHED
            txn.matched_supporter = allocation.supporter
            txn.save()

            # 3. Write TransactionAuditLog
            TransactionAuditLog.objects.create(
                transaction=txn,
                actor=self.request.user,
                action=TransactionAuditLog.Action.MANUAL_MATCHED,
                notes=f"Manually matched to {allocation.supporter}"
            )
            
            messages.success(self.request, f"Transaction {txn.bank_reference} matched successfully.")

        return super().form_valid(form)
