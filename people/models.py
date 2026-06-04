# people/models.py
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import uuid


class Supporter(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True, default="")
    email = models.EmailField(blank=True, null=True, unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    address = models.TextField(blank=True, default="")

    is_donor = models.BooleanField(default=False)
    is_subscriber = models.BooleanField(default=False)

    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_supporters",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Supporter")
        verbose_name_plural = _("Supporters")
        indexes = [models.Index(fields=["last_name", "first_name"])]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()


class SupporterIdentifier(models.Model):
    class IdentifierType(models.TextChoices):
        UPI_ID = "UPI", _("UPI ID")
        BANK_ACCOUNT = "BANK_ACC", _("Bank Account Number")
        PHONE_NUMBER = "PHONE", _("Phone Number")
        EMAIL = "EMAIL", _("Email Address")
        CUSTOM_REF = "CUSTOM", _("Custom Reference")

    supporter = models.ForeignKey(
        Supporter, on_delete=models.CASCADE, related_name="identifiers"
    )
    identifier_type = models.CharField(max_length=10, choices=IdentifierType.choices)
    value = models.CharField(max_length=255)
    is_verified = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["identifier_type", "value"], name="unique_identifier_value"
            )
        ]
        indexes = [models.Index(fields=["value", "identifier_type"])]

    def __str__(self):
        return f"{self.get_identifier_type_display()}: {self.value}"


class CanvassInteraction(models.Model):
    supporter = models.ForeignKey(
        Supporter, on_delete=models.CASCADE, related_name="interactions"
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    interaction_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField()

    class Meta:
        ordering = ["-interaction_date"]

