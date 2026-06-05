from django.urls import path
from . import views

app_name = 'people'

urlpatterns = [
    path('dashboard/', views.AgentDashboardView.as_view(), name='agent_dashboard'),
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('supporter/<uuid:supporter_id>/', views.SupporterDetailView.as_view(), name='supporter_detail'),
    path('supporter/<uuid:supporter_id>/edit/', views.SupporterEditAPIView.as_view(), name='supporter_edit'),
    path('supporter/<uuid:supporter_id>/identifier/add/', views.IdentifierAddAPIView.as_view(), name='identifier_add'),
    path('identifier/<int:identifier_id>/delete/', views.IdentifierDeleteAPIView.as_view(), name='identifier_delete'),
    path('api/log-interaction/', views.LogInteractionAPIView.as_view(), name='api_log_interaction'),
]
