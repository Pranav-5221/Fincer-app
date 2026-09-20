from rest_framework.response import Response
from rest_framework.decorators import api_view,permission_classes
from .serializers import RegisterSerializer,TransactionSerializer
from django.contrib.auth import authenticate
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