from django import forms
from django.core.exceptions import ValidationError
from .models import CharityBankAccount, LedgerAllocation, BankTransaction
from people.models import Supporter

class StatementUploadForm(forms.Form):
    """
    Form for uploading bank statements. Only accessible by admins.
    """
    bank_account = forms.ModelChoiceField(
        queryset=CharityBankAccount.objects.filter(is_active=True),
        label="Bank Account",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    file = forms.FileField(
        label="Statement File (Excel)",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xls, .xlsx'})
    )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file and not file.name.endswith(('.xls', '.xlsx')):
            raise ValidationError("Security Error: Only strictly formatted .xls, .xlsx files are allowed.")
        return file


class TransactionMatchForm(forms.ModelForm):
    supporter = forms.ModelChoiceField(
        queryset=Supporter.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        label="Select Existing Supporter"
    )

    class Meta:
        model = LedgerAllocation
        fields = ['supporter']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.transaction = kwargs.pop('transaction', None)
        super().__init__(*args, **kwargs)

        # Base filter: never show deleted supporters
        qs = Supporter.objects.filter(is_deleted=False)

        # Scope by agent (allow admins/staff to see all)
        if self.user:
            if not (self.user.is_staff or self.user.is_superuser):
                qs = qs.filter(created_by=self.user)
                # Note: If agents should also see supporters assigned to them, use:
                # qs = qs.filter(Q(created_by=self.user) | Q(assigned_agent=self.user)).distinct()

        self.fields['supporter'].queryset = qs.order_by('first_name', 'last_name')