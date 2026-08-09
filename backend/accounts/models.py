from django.conf import settings
from django.db import models


class AccountType(models.IntegerChoices):
    OTHER = 0, "Other"
    BANK = 1, "Bank"
    CASH = 2, "Cash"
    CREDIT_CARD = 3, "Credit Card"


class FinancialAccount(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accounts",
    )

    name = models.CharField(max_length=100)

    account_type = models.IntegerField(
        choices=AccountType.choices,
        default=AccountType.OTHER
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.user})"