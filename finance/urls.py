from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('upload/', views.StatementUploadView.as_view(), name='upload_statement'),
    path('pending/', views.AgentPendingTransactionsView.as_view(), name='pending_transactions'),
    path('match/<uuid:transaction_id>/', views.TransactionMatchView.as_view(), name='transaction_match'),
]
