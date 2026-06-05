from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('upload/', views.StatementUploadView.as_view(), name='upload_statement'),
    path('batch/<str:batch_number>/delete/', views.BatchDeleteView.as_view(), name='delete_batch'),
    path('batch/<str:batch_number>/', views.BatchDetailView.as_view(), name='batch_detail'),
    path('transaction/', views.AgentTransactionsView.as_view(), name='transactions'),
    path('match/<uuid:transaction_id>/', views.TransactionMatchView.as_view(), name='transaction_match'),
    path('api/supporter/create/', views.CreateSupporterAjaxView.as_view(), name='api_create_supporter'),
    path('api/supporter/<uuid:supporter_id>/details/', views.SupporterDetailsAjaxView.as_view(), name='api_supporter_details'),
    path('api/check-phone/', views.CheckPhoneExistsAjaxView.as_view(), name='api_check_phone'),
]
