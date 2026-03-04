from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView as DjangoLoginView, LogoutView as DjangoLogoutView
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.views.decorators.http import require_POST

class LoginView(DjangoLoginView):
    template_name = "accounts/login.html"

class LogoutView(DjangoLogoutView):
    pass

def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("/q/")
    else:
        form = UserCreationForm()
    return render(request, "accounts/signup.html", {"form": form})

@require_POST
def logout_view(request):
    logout(request)
    return redirect("/accounts/login/")