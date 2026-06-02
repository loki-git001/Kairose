from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum
from .models import Supporter
from finance.models import BankTransaction, TransactionAuditLog, StatementImportBatch

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
        
        # To-Do Pipeline: Count of unmatched or ambiguous transactions
        context['unmatched_count'] = BankTransaction.objects.filter(
            match_status__in=[BankTransaction.MatchStatus.UNMATCHED, BankTransaction.MatchStatus.AMBIGUOUS]
        ).count()
        
        # Recent Successes: Feed of the agent's recently matched transactions
        context['recent_successes'] = TransactionAuditLog.objects.filter(
            actor=self.request.user,
            action=TransactionAuditLog.Action.MANUAL_MATCHED
        ).select_related('transaction').order_by('-timestamp')[:5]
        
        return context


class SupporterDetailView(LoginRequiredMixin, DetailView):
    """
    Detailed view for a specific assigned supporter.
    """
    model = Supporter
    template_name = 'people/supporter_detail.html'
    context_object_name = 'supporter'
    pk_url_kwarg = 'supporter_id'

    def get_queryset(self):
        # Additional safety check to only allow agents to view their own supporters.
        return Supporter.objects.filter(assigned_agent=self.request.user)


class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_active and (self.request.user.is_staff or self.request.user.is_superuser)


class AdminDashboardView(AdminRequiredMixin, TemplateView):
    """
    The Command Center for Admins.
    """
    template_name = 'people/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Batch Health: Recent StatementImportBatch records
        context['recent_batches'] = StatementImportBatch.objects.all().order_by('-uploaded_at')[:5]
        
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
