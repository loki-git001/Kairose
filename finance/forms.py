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
    """
    Form for manually matching a transaction.
    Agents can select a supporter assigned to them OR create a new supporter via popup.
    """
    supporter = forms.ModelChoiceField(
        queryset=Supporter.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        label="Select Existing Supporter"
    )

    class Meta:
        model = LedgerAllocation
        fields = ['supporter', 'purpose', 'amount']
        widgets = {
            'purpose': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        # Pass the specific bank transaction into the form
        self.transaction = kwargs.pop('transaction', None) 
        
        super().__init__(*args, **kwargs)
        
        if self.user:
            self.fields['supporter'].queryset = Supporter.objects.filter(assigned_agent=self.user)
            
        # Default the amount field to the exact amount of the bank transaction
        if self.transaction and not self.is_bound:
            self.fields['amount'].initial = self.transaction.amount

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')

        # 2. Financial Integrity Logic
        if self.transaction and amount:
            if amount > self.transaction.amount:
                raise ValidationError(f"You cannot allocate more than the transaction total (₹{self.transaction.amount}).")
            if amount <= 0:
                raise ValidationError("Allocation amount must be greater than zero.")
                
        return cleaned_data