from rest_framework.response import Response
from rest_framework.decorators import api_view,permission_classes
from .serializers import RegisterSerializer,TransactionSerializer,TransactionUpdateSerializer
from .parser import parse_sms
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated

@api_view(["GET"])
def health_check(request):
    return Response({
        "status": "ok"
    })

@api_view(["POST"])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user=serializer.save()
        return Response(RegisterSerializer(user).data,status=201)
    else:
        return Response(serializer.errors)

@api_view(["POST"])
def user_login(request):
    username = request.data.get("username")
    password = request.data.get("password")
    user = authenticate(
    username=username,
    password=password
    )
    if user:
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        return Response({
            "refresh": str(refresh),
            "access": str(access)
        })
    else:
        return Response({"error": "Invalid username or password"})

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    info=request.user
    return Response({
        "id": info.id,
        "name": info.username,
        "email": info.email
    })

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def transactions(request):

    if request.method == "POST":
        serializer = TransactionSerializer(data=request.data)

        if serializer.is_valid():
            transaction = serializer.save(user=request.user)

            return Response(
                TransactionSerializer(transaction).data,
                status=201
            )

        return Response(serializer.errors)

    transactions = request.user.transactions.all()
    serializer = TransactionSerializer(transactions, many=True)

    return Response(serializer.data)

@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def transaction_detail(request, transaction_id):
    transaction = get_object_or_404(
        request.user.transactions,
        id=transaction_id
    )

    if request.method == "GET":
        serializer = TransactionSerializer(transaction)
        return Response(serializer.data)

    if request.method == "PATCH":
        serializer = TransactionUpdateSerializer(
            transaction,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)

    if request.method == "DELETE":
        transaction.delete()
        return Response(status=204)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def parse_and_create(request):
    sms = request.data.get("sms")

    if not sms:
        return Response(
            {"error": "SMS text is required"},
            status=400
        )

    parsed = parse_sms(sms)

    if parsed is None:
        return Response(
            {"error": "Could not parse transaction from SMS"},
            status=400
        )

    # Date fallback: parsed date → client received_at → server time
    transaction_at = parsed["transaction_at"]

    if transaction_at is None:
        received_at = request.data.get("received_at")
        if received_at:
            try:
                from datetime import datetime
                transaction_at = datetime.fromisoformat(received_at)
            except (ValueError, TypeError):
                transaction_at = timezone.now()
        else:
            transaction_at = timezone.now()

    # Make naive datetimes timezone-aware
    if timezone.is_naive(transaction_at):
        transaction_at = timezone.make_aware(transaction_at)

    serializer = TransactionSerializer(data={
        "amount": str(parsed["amount"]),
        "transaction_type": parsed["transaction_type"],
        "bank": parsed["bank"],
        "merchant": parsed["merchant"],
        "category": parsed["category"],
        "transaction_at": transaction_at.isoformat(),
        "original_sms": sms,
    })

    if serializer.is_valid():
        transaction = serializer.save(user=request.user)
        return Response(
            TransactionSerializer(transaction).data,
            status=201
        )

    return Response(serializer.errors, status=400)