from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Transaction


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["username", "email", "password"]

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"]
        )
        return user


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "id", "amount", "transaction_type", "bank",
            "merchant", "category", "transaction_at", "original_sms",
        ]
        read_only_fields = ["id"]


class TransactionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "amount",
            "transaction_type",
            "bank",
            "merchant",
            "category",
        ]