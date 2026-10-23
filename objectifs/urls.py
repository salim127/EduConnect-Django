from django.urls import path
from . import views
from .intelligence_views import DisponibiliteView, ChargeView, RechercheSensView, BesoinsView
from .statistiques import StatistiquesView, ActiviteView

app_name = 'objectifs'
urlpatterns = [
    path('disponibilite/', DisponibiliteView.as_view(), name='disponibilite'),
    path('charge/', ChargeView.as_view(), name='charge'),
    path('recherche-intelligente/', RechercheSensView.as_view(), name='recherche_sens'),
    path('besoins/', BesoinsView.as_view(), name='besoins'),
    path('statistiques/', StatistiquesView.as_view(), name='statistiques'),
    path('taches/<int:pk>/activite/', ActiviteView.as_view(), name='activite'),
    path('taches/<int:pk>/travail/', views.TacheTravailView.as_view(), name='tache_travail'),
    path('taches/<int:pk>/validation/', views.TacheValidationView.as_view(), name='tache_validation'),
    path('taches/<int:pk>/avancement/', views.TacheTravailView.as_view(), name='tache_statut'),
    path('mes-objectifs/', views.ObjectifListView.as_view(), name='objectifs'),
    path('mes-taches/', views.TacheListView.as_view(), name='taches'),
    path('', views.ObjectifListView.as_view(), name='objectif_list'),
    path('ajouter/', views.ObjectifCreateView.as_view(), name='objectif_create'),
    path('<int:pk>/', views.ObjectifDetailView.as_view(), name='objectif_detail'),
    path('<int:pk>/modifier/', views.ObjectifUpdateView.as_view(), name='objectif_update'),
    path('<int:pk>/supprimer/', views.ObjectifDeleteView.as_view(), name='objectif_delete'),
    path('taches/', views.TacheListView.as_view(), name='tache_list'),
    path('taches/ajouter/', views.TacheCreateView.as_view(), name='tache_create'),
    path('taches/<int:pk>/', views.TacheDetailView.as_view(), name='tache_detail'),
    path('taches/<int:pk>/modifier/', views.TacheUpdateView.as_view(), name='tache_update'),
    path('taches/<int:pk>/supprimer/', views.TacheDeleteView.as_view(), name='tache_delete'),
]
