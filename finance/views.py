from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import CreateView, FormView, ListView, DeleteView
from django.views import View
from django.http import JsonResponse, HttpResponseRedirect
import json
from people.models import Supporter, SupporterIdentifier

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
class AgentTransactionsView(LoginRequiredMixin, ListView):
    """
    Agents view all system-wide transactions with a status filter.
    """
    model = BankTransaction
    template_name = 'finance/transactions.html'
    context_object_name = 'transactions'

    def get_queryset(self):
        qs = BankTransaction.objects.select_related('batch__bank_account')
        statuses = self.request.GET.getlist('status')
        if statuses:
            qs = qs.filter(match_status__in=statuses)
        return qs
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = BankTransaction.MatchStatus.choices
        context['selected_statuses'] = self.request.GET.getlist('status')
        return context


@method_decorator(never_cache, name='dispatch')
class TransactionMatchView(LoginRequiredMixin, CreateView):
    """
    View for agents to manually match a transaction to one of their assigned supporters.
    """
    model = LedgerAllocation
    form_class = TransactionMatchForm
    template_name = 'finance/transaction_match.html'
    success_url = reverse_lazy('finance:transactions')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['transaction'] = get_object_or_404(BankTransaction, pk=self.kwargs['transaction_id'])
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        txn = get_object_or_404(BankTransaction, pk=self.kwargs['transaction_id'])
        context['transaction'] = txn
        
        is_new = False
        suggested_supporter_id = None
        
        if txn.extracted_identifier:
            is_new = not SupporterIdentifier.objects.filter(value=txn.extracted_identifier).exists()
            if not is_new:
                # Find the existing supporter
                sid = SupporterIdentifier.objects.filter(value=txn.extracted_identifier).first()
                if sid:
                    suggested_supporter_id = sid.supporter_id
        context['is_new_identifier'] = is_new

        from .services import extract_phone_from_upi
        if txn.transaction_mode == BankTransaction.TransactionMode.UPI:
            text_to_search = f"{txn.extracted_identifier} {txn.raw_narration}"
            expected_phone = extract_phone_from_upi(text_to_search)
            if expected_phone:
                context['expected_phone'] = expected_phone
                if not suggested_supporter_id:
                    sid = SupporterIdentifier.objects.filter(identifier_type=SupporterIdentifier.IdentifierType.PHONE_NUMBER, value=expected_phone).first()
                    if sid:
                        suggested_supporter_id = sid.supporter_id
                        
        context['suggested_supporter_id'] = suggested_supporter_id
        
        # Get distinct purposes for the dropdown
        existing_purposes = list(LedgerAllocation.objects.values_list('purpose', flat=True).distinct())
        default_purposes = ["Charity Donation", "Magazine Subscription", "Other"]
        all_purposes = list(set(existing_purposes + default_purposes))
        context['purposes'] = sorted(all_purposes)

        # Get existing splits if any (for edit mode)
        context['existing_splits'] = txn.allocations.all()

        return context

    def get_initial(self):
        return super().get_initial()

    def form_valid(self, form):
        from decimal import Decimal
        txn = get_object_or_404(BankTransaction, pk=self.kwargs['transaction_id'])
        
        purposes = self.request.POST.getlist('purpose[]')
        amounts = self.request.POST.getlist('amount[]')
        
        if not purposes or not amounts or len(purposes) != len(amounts):
            messages.error(self.request, "Invalid splits submitted.")
            return self.form_invalid(form)
            
        try:
            decimal_amounts = [Decimal(a) for a in amounts]
            total_split = sum(decimal_amounts)
        except:
            messages.error(self.request, "Invalid amount values.")
            return self.form_invalid(form)
            
        if total_split != txn.amount:
            messages.error(self.request, f"Split amounts must exactly equal {txn.amount}")
            return self.form_invalid(form)
        
        with transaction.atomic():
            supporter = form.cleaned_data['supporter']
            
            # 1. Delete existing allocations (clean slate for editing)
            LedgerAllocation.objects.filter(transaction=txn).delete()
            
            # 2. Create the LedgerAllocations
            allocations_to_create = []
            has_donation = False
            has_subscription = False
            
            for p, a in zip(purposes, decimal_amounts):
                p = p.strip()
                if not p or a <= 0:
                    continue
                    
                allocations_to_create.append(
                    LedgerAllocation(
                        transaction=txn,
                        supporter=supporter,
                        purpose=p,
                        amount=a
                    )
                )
                if 'donation' in p.lower():
                    has_donation = True
                if 'subscription' in p.lower():
                    has_subscription = True
                    
            if not allocations_to_create:
                messages.error(self.request, "No valid splits were provided.")
                return self.form_invalid(form)
                
            LedgerAllocation.objects.bulk_create(allocations_to_create)

            # 3. Update BankTransaction
            txn.match_status = BankTransaction.MatchStatus.MATCHED
            txn.matched_supporter = supporter
            txn.save()

            # 4. Update Supporter Donor/Subscriber Status
            if has_donation:
                supporter.is_donor = True
            if has_subscription:
                supporter.is_subscriber = True
            if has_donation or has_subscription:
                supporter.save()

            # 5. Write TransactionAuditLog
            TransactionAuditLog.objects.create(
                transaction=txn,
                actor=self.request.user,
                action=TransactionAuditLog.Action.MATCHED,
                notes=f"Matched to {supporter} with {len(purposes)} split(s)."
            )
            
            link_upi_id = self.request.POST.get('link_upi_id')
            if link_upi_id and link_upi_id.strip():
                val = link_upi_id.strip()
                if not SupporterIdentifier.objects.filter(value=val).exists():
                    SupporterIdentifier.objects.create(
                        supporter=supporter,
                        identifier_type=SupporterIdentifier.IdentifierType.UPI_ID,
                        value=val,
                        is_verified=True
                    )
            link_phone_number = self.request.POST.get('link_phone_number')
            if link_phone_number and link_phone_number.strip():
                phone_val = link_phone_number.strip()
                if not SupporterIdentifier.objects.filter(identifier_type=SupporterIdentifier.IdentifierType.PHONE_NUMBER, value=phone_val).exists():
                    SupporterIdentifier.objects.create(
                        supporter=supporter,
                        identifier_type=SupporterIdentifier.IdentifierType.PHONE_NUMBER,
                        value=phone_val,
                        is_verified=True
                    )
            
            messages.success(self.request, f"Transaction {txn.bank_reference} matched successfully.")
        self.object = allocations_to_create[0] if allocations_to_create else None
        return HttpResponseRedirect(self.get_success_url())


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
            
            if phone_number and not SupporterIdentifier.objects.filter(identifier_type=SupporterIdentifier.IdentifierType.PHONE_NUMBER, value=phone_number).exists():
                SupporterIdentifier.objects.create(
                    supporter=supporter,
                    identifier_type=SupporterIdentifier.IdentifierType.PHONE_NUMBER,
                    value=phone_number,
                    is_verified=True
                )
                
            if email and not SupporterIdentifier.objects.filter(value=email).exists():
                SupporterIdentifier.objects.create(
                    supporter=supporter,
                    identifier_type=SupporterIdentifier.IdentifierType.EMAIL,
                    value=email,
                    is_verified=True
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
            phone_identifiers = list(
                SupporterIdentifier.objects.filter(
                    supporter=supporter, 
                    identifier_type=SupporterIdentifier.IdentifierType.PHONE_NUMBER
                ).values_list('value', flat=True)
            )
            data = {
                'first_name': supporter.first_name,
                'last_name': supporter.last_name,
                'email': supporter.email or '',
                'phone_number': supporter.phone_number or '',
                'address': supporter.address or '',
                'is_donor': supporter.is_donor,
                'is_subscriber': supporter.is_subscriber,
                'phone_identifiers': phone_identifiers
            }
            return JsonResponse({'success': True, 'data': data})
        except Supporter.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Supporter not found'})


class CheckPhoneExistsAjaxView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        phone_number = request.GET.get('phone_number', '').strip()
        if not phone_number:
            return JsonResponse({'exists': False})
            
        ident = SupporterIdentifier.objects.filter(
            identifier_type=SupporterIdentifier.IdentifierType.PHONE_NUMBER, 
            value=phone_number
        ).select_related('supporter').first()
        
        if ident:
            return JsonResponse({'exists': True, 'supporter_name': str(ident.supporter)})
        return JsonResponse({'exists': False})
