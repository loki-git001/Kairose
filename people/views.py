from django.views.generic import ListView, DetailView, TemplateView, UpdateView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum, Min, Max, Q
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
    model = BankTransaction
    template_name = 'people/agent_dashboard.html'
    context_object_name = 'transactions'

    def get_queryset(self):
        from django.db.models import Subquery, OuterRef
        
        # Method C: Subquery annotation for perfect chronological sorting by action time
        latest_action = TransactionAuditLog.objects.filter(
            transaction=OuterRef('pk'),
            actor=self.request.user
        ).order_by('-timestamp')
        
        return BankTransaction.objects.filter(handled_by=self.request.user).annotate(
            last_acted_at=Subquery(latest_action.values('timestamp')[:1])
        ).filter(last_acted_at__isnull=False).select_related('matched_supporter').order_by('-last_acted_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # To-Do Pipeline: Count of unmatched transactions
        context['unmatched_count'] = BankTransaction.objects.filter(
            match_status__in=[BankTransaction.MatchStatus.UNMATCHED]
        ).count()
        
        # Total deposits from supporters created by this agent
        total_deposits = BankTransaction.objects.filter(
            match_status=BankTransaction.MatchStatus.MATCHED,
            matched_supporter__created_by=self.request.user
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        context['my_supporters_total_deposits'] = total_deposits
        context['supporters'] = Supporter.objects.filter(
            Q(created_by=self.request.user) | Q(assigned_agent=self.request.user),
            is_deleted=False
            ).only('id', 'first_name', 'last_name').order_by('first_name', 'last_name')
        
        return context


@method_decorator(never_cache, name='dispatch')
class MySupportersListView(LoginRequiredMixin, ListView):
    """
    Shows a list of Supporters created by the current agent.
    """
    model = Supporter
    template_name = 'people/my_supporters_list.html'
    context_object_name = 'supporters'

    def get_queryset(self):
        from django.db.models import Q
        qs = Supporter.objects.filter(created_by=self.request.user, is_deleted=False)
        
        q = self.request.GET.get('q')
        if q:
            q = q.strip()
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(phone_number__icontains=q) |
                Q(identifiers__value__icontains=q)
            ).distinct()
            
        return qs.order_by('-created_at')

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            self.template_name = 'people/partials/_supporter_table_rows.html'
        return super().render_to_response(context, **response_kwargs)


@method_decorator(never_cache, name='dispatch')
class AgentInteractionsListView(LoginRequiredMixin, ListView):
    """
    Shows a list of CanvassInteractions created by the current agent.
    """
    model = CanvassInteraction
    template_name = 'people/interactions_list.html'
    context_object_name = 'interactions'

    def get_queryset(self):
        return CanvassInteraction.objects.filter(agent=self.request.user).select_related('supporter').order_by('-interaction_date')


@method_decorator(never_cache, name='dispatch')
class SupporterDetailView(LoginRequiredMixin, DetailView):
    """
    Detailed view for a specific assigned supporter.
    """
    model = Supporter
    template_name = 'people/supporter_detail.html'
    context_object_name = 'supporter'
    pk_url_kwarg = 'supporter_id'

    def get_queryset(self):
        return Supporter.objects.filter(is_deleted=False)

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
class SupporterSoftDeleteView(LoginRequiredMixin, View):
    """
    Handles soft deletion of a Supporter.
    """
    def post(self, request, supporter_id):
        supporter = get_object_or_404(Supporter, id=supporter_id, is_deleted=False)
        
        # Check permissions: only admin or the agent who created/is assigned can delete
        if not (request.user.is_staff or request.user.is_superuser or supporter.assigned_agent == request.user or supporter.created_by == request.user):
            messages.error(request, "Permission denied. You cannot delete this supporter.")
            return redirect('people:supporter_detail', supporter_id=supporter.id)
            
        supporter.is_deleted = True
        supporter.save()
        messages.success(request, f"Supporter {supporter} has been deleted.")
        return redirect('people:my_supporters')

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
        
        # Financial Bottlenecks: Unmatched deposits and withdrawals
        unmatched_txns = BankTransaction.objects.filter(
            match_status=BankTransaction.MatchStatus.UNMATCHED
        )
        bottleneck_aggr = unmatched_txns.aggregate(
            deposits=Sum('amount', filter=Q(amount__gt=0)),
            withdrawals=Sum('amount', filter=Q(amount__lt=0))
        )
        context['unmatched_deposits'] = bottleneck_aggr['deposits'] or 0
        context['unmatched_withdrawals'] = abs(bottleneck_aggr['withdrawals'] or 0)
        
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

            if len(notes.strip()) < 10:
                return JsonResponse({'success': False, 'error': 'Interaction notes must be at least 10 characters long.'}, status=400)

            # Ensure the supporter is assigned to the current user
            supporter = get_object_or_404(
                Supporter,
                Q(created_by=request.user) | Q(assigned_agent=request.user),
                id=supporter_id,
                is_deleted=False
            )
            CanvassInteraction.objects.create(
                supporter=supporter,
                agent=request.user,
                notes=notes
            )

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)