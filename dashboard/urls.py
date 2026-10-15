from django.urls import path

from . import views

app_name = 'dashboard'
urlpatterns = [
    path('', views.landing, name='landing'),
    path('tableau-de-bord/', views.HomeView.as_view(), name='home'),
]
