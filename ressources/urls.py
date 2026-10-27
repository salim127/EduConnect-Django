from django.urls import path
from . import views
from . import ai_views

app_name = 'ressources'

urlpatterns = [
    # Bibliothèque (Ressources)
    path('bibliotheque/', views.BibliothequeView.as_view(), name='bibliotheque'),
    path('bibliotheque/ajouter/', views.RessourceCreateView.as_view(), name='ressource_create'),
    path('bibliotheque/assistant-ia/', ai_views.AssistantRessourceView.as_view(), name='assistant_ia'),
    path('bibliotheque/<int:pk>/', views.RessourceDetailView.as_view(), name='ressource_detail'),
    path('bibliotheque/<int:pk>/modifier/', views.RessourceUpdateView.as_view(), name='ressource_update'),
    path('bibliotheque/<int:pk>/supprimer/', views.RessourceDeleteView.as_view(), name='ressource_delete'),
    path('bibliotheque/<int:pk>/fiche-ia/', ai_views.FichePedagogiqueView.as_view(), name='fiche_ia'),

    # Catégories
    path('categories/', views.CategoriesView.as_view(), name='categories'),
    path('categories/ajouter/', views.CategorieCreateView.as_view(), name='categorie_create'),
    path('categories/<int:pk>/modifier/', views.CategorieUpdateView.as_view(), name='categorie_update'),
    path('categories/<int:pk>/supprimer/', views.CategorieDeleteView.as_view(), name='categorie_delete'),
]

