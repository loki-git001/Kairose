from django.views.generic import ListView, DetailView, TemplateView, UpdateView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum, Min, Max
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
import json
from .models import Supporter, CanvassInteraction
from finance.models import BankTransaction, TransactionAuditLog, StatementImportBatch

@method_decorator(never_cache, name='dispatch')
class AgentDashboardView(LoginRequiredMixin, ListView):
    """
    Dashboard showing the agent's assigned supporters and task metrics.
    """
    model = Supporter
    template_name = 'people/agent_dashboard.html'
    context_object_name = 'supporters'

    def get_queryset(self):
        # Supporter Scoping: Field Agents can only view Supporter profiles assigned to them.
        # Ordered by recently updated as per "My Portfolio" requirement.
        return Supporter.objects.filter(assigned_agent=self.request.user).order_by('-updated_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # To-Do Pipeline: Count of unmatched transactions
        context['unmatched_count'] = BankTransaction.objects.filter(
            match_status__in=[BankTransaction.MatchStatus.UNMATCHED]
        ).count()
        
        # Recent Successes: Feed of the agent's recently matched transactions
        context['recent_successes'] = TransactionAuditLog.objects.filter(
            actor=self.request.user,
            action=TransactionAuditLog.Action.MATCHED
        ).select_related('transaction').order_by('-timestamp')[:5]
        
        return context


@method_decorator(never_cache, name='dispatch')
class SupporterDetailView(LoginRequiredMixin, DetailView):
    """
    Detailed view for a specific assigned supporter.
    """
    model = Supporter
    template_name = 'people/supporter_detail.html'
    context_object_name = 'supporter'
    pk_url_kwarg = 'supporter_id'

from django.shortcuts import redirect
from django.contrib import messages
from .models import SupporterIdentifier

@method_decorator(never_cache, name='dispatch')
class SupporterEditAPIView(LoginRequiredMixin, View):
    """
    Handles form submission from the Supporter Edit Modal.
    """
    def post(self, request, supporter_id):
        supporter = get_object_or_404(Supporter, id=supporter_id)
        if not (request.user.is_staff or request.user.is_superuser or supporter.assigned_agent == request.user):
            messages.error(request, "Permission denied.")
            return redirect('people:supporter_detail', supporter_id=supporter.id)

        supporter.first_name = request.POST.get('first_name', supporter.first_name)
        supporter.last_name = request.POST.get('last_name', supporter.last_name)
        supporter.email = request.POST.get('email', '')
        supporter.phone_number = request.POST.get('phone_number', '')
        supporter.address = request.POST.get('address', '')
        
        try:
            supporter.save()
            messages.success(request, "Profile updated successfully.")
        except Exception as e:
            messages.error(request, f"Error updating profile: {str(e)}")
            
        return redirect('people:supporter_detail', supporter_id=supporter.id)

@method_decorator(never_cache, name='dispatch')
class IdentifierDeleteAPIView(LoginRequiredMixin, View):
    """
    Handles deletion of a SupporterIdentifier.
    """
    def post(self, request, identifier_id):
        identifier = get_object_or_404(SupporterIdentifier, id=identifier_id)
        supporter = identifier.supporter
        
        if not (request.user.is_staff or request.user.is_superuser or supporter.assigned_agent == request.user):
            messages.error(request, "Permission denied.")
            return redirect('people:supporter_detail', supporter_id=supporter.id)

        try:
            identifier.delete()
            messages.success(request, "Identifier removed successfully.")
        except Exception as e:
            messages.error(request, f"Error removing identifier: {str(e)}")
            
        return redirect('people:supporter_detail', supporter_id=supporter.id)

@method_decorator(never_cache, name='dispatch')
class IdentifierAddAPIView(LoginRequiredMixin, View):
    """
    Handles addition of a new SupporterIdentifier.
    """
    def post(self, request, supporter_id):
        supporter = get_object_or_404(Supporter, id=supporter_id)
        if not (request.user.is_staff or request.user.is_superuser or supporter.assigned_agent == request.user):
            messages.error(request, "Permission denied.")
            return redirect('people:supporter_detail', supporter_id=supporter.id)

        identifier_type = request.POST.get('identifier_type')
        value = request.POST.get('value')
        
        if not identifier_type or not value:
            messages.error(request, "Type and Value are required.")
            return redirect('people:supporter_detail', supporter_id=supporter.id)
            
        try:
            SupporterIdentifier.objects.create(
                supporter=supporter,
                identifier_type=identifier_type,
                value=value.strip()
            )
            messages.success(request, "Identifier added successfully.")
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                messages.error(request, "This exact identifier is already registered.")
            else:
                messages.error(request, f"Error adding identifier: {str(e)}")
                
        return redirect('people:supporter_detail', supporter_id=supporter.id)


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_active and (self.request.user.is_staff or self.request.user.is_superuser)


@method_decorator(never_cache, name='dispatch')
class AdminDashboardView(AdminRequiredMixin, TemplateView):
    """
    The Command Center for Admins.
    """
    template_name = 'people/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Batch Health: Recent StatementImportBatch records
        context['recent_batches'] = StatementImportBatch.objects.annotate(
            start_date=Min('transactions__transaction_date'),
            end_date=Max('transactions__transaction_date')
        ).order_by('-uploaded_at')[:5]
        
        # Financial Bottlenecks: Total value of all UNMATCHED transactions
        bottleneck_aggr = BankTransaction.objects.filter(
            match_status=BankTransaction.MatchStatus.UNMATCHED
        ).aggregate(total_amount=Sum('amount'))
        context['financial_bottleneck'] = bottleneck_aggr['total_amount'] or 0
        
        # Recent Audits: Live feed of system activity
        context['recent_audits'] = TransactionAuditLog.objects.select_related(
            'actor', 'transaction'
        ).order_by('-timestamp')[:10]
        
        return context


@method_decorator(never_cache, name='dispatch')
class LogInteractionAPIView(LoginRequiredMixin, View):
    """
    API endpoint for logging an interaction with a supporter.
    """
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            supporter_id = data.get('supporter_id')
            notes = data.get('notes')

            if not supporter_id or not notes:
                return JsonResponse({'success': False, 'error': 'Supporter and notes are required.'}, status=400)

            # Ensure the supporter is assigned to the current user
            supporter = get_object_or_404(Supporter, id=supporter_id, assigned_agent=request.user)

            CanvassInteraction.objects.create(
                supporter=supporter,
                agent=request.user,
                notes=notes
            )

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
