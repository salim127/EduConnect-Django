from django.urls import path

from . import views as v

app_name = 'pedagogie'
urlpatterns = [
    path('cours/', v.CoursListView.as_view(), name='cours_list'),
    path('cours/ajouter/', v.CoursCreateView.as_view(), name='cours_create'),
    path('cours/<int:pk>/', v.CoursDetailView.as_view(), name='cours_detail'),
    path('cours/<int:pk>/modifier/', v.CoursUpdateView.as_view(), name='cours_update'),
    path('cours/<int:pk>/supprimer/', v.CoursDeleteView.as_view(), name='cours_delete'),
    path('exercices/', v.ExerciceListView.as_view(), name='exercice_list'),
    path('exercices/ajouter/', v.ExerciceCreateView.as_view(), name='exercice_create'),
    path('exercices/<int:pk>/', v.ExerciceDetailView.as_view(), name='exercice_detail'),
    path('exercices/<int:pk>/modifier/', v.ExerciceUpdateView.as_view(), name='exercice_update'),
    path('exercices/<int:pk>/supprimer/', v.ExerciceDeleteView.as_view(), name='exercice_delete'),
]
