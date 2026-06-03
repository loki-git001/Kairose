from django.contrib import admin
from .models import (
    Supporter,
    SupporterIdentifier,
    CanvassInteraction,
    MagazineSubscription,
)

# ==========================================
# INLINES (Child tables shown on the Parent page)
# ==========================================


class SupporterIdentifierInline(admin.TabularInline):
    model = SupporterIdentifier
    extra = 1
    fields = ("identifier_type", "value", "is_verified")


class MagazineSubscriptionInline(admin.TabularInline):
    model = MagazineSubscription
    extra = 0
    fields = ("start_date", "end_date", "status", "delivery_address")


class CanvassInteractionInline(admin.TabularInline):
    model = CanvassInteraction
    extra = 0
    readonly_fields = ("interaction_date",)
    fields = ("agent", "notes", "interaction_date")


# ==========================================
# MODEL ADMINS
# ==========================================


@admin.register(Supporter)
class SupporterAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "is_donor",
        "is_subscriber",
    )
    list_filter = ("is_donor", "is_subscriber", "created_at")
    search_fields = ("first_name", "last_name", "email", "phone_number")
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (
            "Personal Info",
            {
                "fields": (
                    "id",
                    "first_name",
                    "last_name",
                    "email",
                    "phone_number",
                    "address",
                )
            },
        ),
        ("Classification", {"fields": ("is_donor", "is_subscriber")}),
        (
            "Management",
            {
                "fields": (
                    "assigned_agent",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    inlines = [
        SupporterIdentifierInline,
        MagazineSubscriptionInline,
        CanvassInteractionInline,
    ]


@admin.register(SupporterIdentifier)
class SupporterIdentifierAdmin(admin.ModelAdmin):
    list_display = ("supporter", "identifier_type", "value", "is_verified")
    list_filter = ("identifier_type", "is_verified")
    search_fields = ("value", "supporter__first_name", "supporter__last_name")
    raw_id_fields = (
        "supporter",
    )  # Prevents loading a massive dropdown of all supporters
