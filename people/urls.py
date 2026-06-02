from django.urls import path
from . import views

app_name = 'people'

urlpatterns = [
    path('dashboard/', views.AgentDashboardView.as_view(), name='agent_dashboard'),
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('supporter/<uuid:supporter_id>/', views.SupporterDetailView.as_view(), name='supporter_detail'),
]
