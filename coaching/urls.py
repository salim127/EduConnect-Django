from django.urls import path

from . import views

app_name = 'coaching'
urlpatterns = [
    path('sessions/', views.SessionsView.as_view(), name='sessions'),
    path('conseils/', views.ConseilsView.as_view(), name='conseils'),
]
