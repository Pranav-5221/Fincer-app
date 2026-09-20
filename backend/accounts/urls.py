from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import health_check, register, user_login, me, transactions, transaction_detail, parse_and_create

urlpatterns = [
    path("health/", health_check),
    path("register/", register),
    path("login/", user_login),
    path("token/refresh/", TokenRefreshView.as_view()),
    path("me/", me),
    path("transactions/", transactions),
    path("transactions/parse/", parse_and_create),
    path("transactions/<int:transaction_id>/", transaction_detail),
]