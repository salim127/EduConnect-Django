from django.urls import path

from . import views

app_name = 'objectifs'
urlpatterns = [
    path('mes-objectifs/', views.ObjectifsView.as_view(), name='objectifs'),
    path('mes-taches/', views.TachesView.as_view(), name='taches'),
]
