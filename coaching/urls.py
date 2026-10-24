from django.urls import path

from . import views

app_name = 'coaching'
urlpatterns = [
    path('tableau-de-bord/', views.CoachingDashboardView.as_view(), name='dashboard'),
    path('sessions/', views.SessionsView.as_view(), name='sessions'),
    path('conseils/', views.ConseilsView.as_view(), name='conseils'),
    path('', views.SessionListView.as_view(), name='session_list'),
    path('ajouter/', views.SessionCreateView.as_view(), name='session_create'),
    path('<int:pk>/', views.SessionDetailView.as_view(), name='session_detail'),
    path('<int:pk>/modifier/', views.SessionUpdateView.as_view(), name='session_update'),
    path('<int:pk>/supprimer/', views.SessionDeleteView.as_view(), name='session_delete'),
    path('<int:pk>/statut/', views.SessionStatusView.as_view(), name='session_status'),
    path('conseils/liste/', views.ConseilListView.as_view(), name='conseil_list'),
    path('conseils/ajouter/', views.ConseilCreateView.as_view(), name='conseil_create'),
    path('conseils/<int:pk>/', views.ConseilDetailView.as_view(), name='conseil_detail'),
    path('conseils/<int:pk>/modifier/', views.ConseilUpdateView.as_view(), name='conseil_update'),
    path('conseils/<int:pk>/supprimer/', views.ConseilDeleteView.as_view(), name='conseil_delete'),
]
