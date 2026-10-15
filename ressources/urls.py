from django.urls import path

from . import views

app_name = 'ressources'
urlpatterns = [
    path('bibliotheque/', views.BibliothequeView.as_view(), name='bibliotheque'),
    path('categories/', views.CategoriesView.as_view(), name='categories'),
]
