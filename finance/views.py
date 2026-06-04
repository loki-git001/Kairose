from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import CreateView, FormView, ListView, DeleteView
from django.views import View
from django.http import JsonResponse
import json
from people.models import Supporter

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
class BatchDeleteView(AdminRequiredMixin, DeleteView):
    """
    Admin-only view to delete a statement import batch and its transactions.
    """
    model = StatementImportBatch
    success_url = reverse_lazy('people:admin_dashboard')

    def form_valid(self, form):
        messages.success(self.request, f"Batch #{self.object.id} and all its transactions have been successfully deleted.")
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


class CreateSupporterAjaxView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            first_name = data.get('first_name', '').strip()
            last_name = data.get('last_name', '').strip()
            email = data.get('email', '').strip()
            phone_number = data.get('phone_number', '').strip()
            address = data.get('address', '').strip()
            
            if not first_name:
                return JsonResponse({'success': False, 'error': 'First name is required'})
            
            supporter = Supporter.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email if email else None,
                phone_number=phone_number if phone_number else None,
                address=address,
                assigned_agent=request.user
            )
            
            return JsonResponse({
                'success': True, 
                'supporter_id': str(supporter.id),
                'name': str(supporter)
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})


class SupporterDetailsAjaxView(LoginRequiredMixin, View):
    def get(self, request, supporter_id, *args, **kwargs):
        try:
            supporter = Supporter.objects.get(id=supporter_id)
            data = {
                'first_name': supporter.first_name,
                'last_name': supporter.last_name,
                'email': supporter.email or '',
                'phone_number': supporter.phone_number or '',
                'address': supporter.address or '',
                'is_donor': supporter.is_donor,
                'is_subscriber': supporter.is_subscriber
            }
            return JsonResponse({'success': True, 'data': data})
        except Supporter.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Supporter not found'})

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
            txn.purpose = allocation.purpose
            txn.save()

            # 3. Update Supporter Donor/Subscriber Status
            supporter = allocation.supporter
            donation_count = BankTransaction.objects.filter(
                matched_supporter=supporter, purpose=BankTransaction.TransactionPurpose.DONATION
            ).count()
            subscription_count = BankTransaction.objects.filter(
                matched_supporter=supporter, purpose=BankTransaction.TransactionPurpose.SUBSCRIPTION
            ).count()

            if donation_count >= 1:
                supporter.is_donor = True
            if subscription_count >= 1:
                supporter.is_subscriber = True
            supporter.save()

            # 4. Write TransactionAuditLog
            TransactionAuditLog.objects.create(
                transaction=txn,
                actor=self.request.user,
                action=TransactionAuditLog.Action.MANUAL_MATCHED,
                notes=f"Manually matched to {allocation.supporter}"
            )
            
            messages.success(self.request, f"Transaction {txn.bank_reference} matched successfully.")

        return super().form_valid(form)
