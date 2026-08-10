from django.conf import settings
from django.db import models


class TransactionType(models.IntegerChoices):
    EXPENSE = 1, "Expense"
    INCOME = 0, "Income"


class Category(models.IntegerChoices):
    OTHER = 0, "Other"
    FOOD = 1, "Food"
    SHOPPING = 2, "Shopping"
    TRAVEL = 3, "Travel"
class Transaction(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )
    transaction_type = models.IntegerField(
        choices=TransactionType.choices
    )
    bank = models.CharField(max_length=100)
    merchant = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )
    category = models.IntegerField(
        choices=Category.choices,
        default=Category.OTHER
    )
    transaction_at = models.DateTimeField()
    original_sms = models.TextField()
    def __str__(self):
        return f"{self.transaction_type} - {self.amount} - {self.merchant}"