from django.urls import path
from .views import signup, logout_view, LoginView

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),
    path("signup/", signup, name="signup"),
]