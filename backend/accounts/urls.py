from django.urls import path
from .views import health_check,register,user_login,me,transactions

urlpatterns = [
    path("health/", health_check),
    path("register/",register),
    path("login/",user_login),
    path("me/",me),
    path("transactions/", transactions),
]