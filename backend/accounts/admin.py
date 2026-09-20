from django.contrib import admin
from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "amount",
        "transaction_type",
        "bank",
        "merchant",
        "category",
        "transaction_at",
    ]
    list_filter = ["transaction_type", "bank", "category"]
    search_fields = ["merchant", "bank", "original_sms"]
