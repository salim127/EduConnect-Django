from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views as v

app_name = 'accounts'
urlpatterns = [
    path('connexion/', v.HubLoginView.as_view(), name='login'),
    path('deconnexion/', LogoutView.as_view(), name='logout'),
    path('inscription/', v.RegisterView.as_view(), name='register'),
    path('profil/', v.ProfileView.as_view(), name='profile'),
    path('profil/modifier/', v.ProfileEditView.as_view(), name='profile_edit'),
    path('profil/mot-de-passe/', v.PasswordView.as_view(), name='password'),
    path('utilisateurs/', v.UserListView.as_view(), name='user_list'),
    path('utilisateurs/ajouter/', v.UserCreateView.as_view(), name='user_create'),
    path('utilisateurs/<int:pk>/modifier/', v.UserUpdateView.as_view(), name='user_update'),
    path('utilisateurs/<int:pk>/statut/', v.UserToggleView.as_view(), name='user_toggle'),
    path('utilisateurs/<int:pk>/supprimer/', v.UserDeleteView.as_view(), name='user_delete'),
    path('roles/', v.RoleListView.as_view(), name='role_list'),
    path('roles/ajouter/', v.RoleCreateView.as_view(), name='role_create'),
    path('roles/<int:pk>/modifier/', v.RoleUpdateView.as_view(), name='role_update'),
    path('roles/<int:pk>/supprimer/', v.RoleDeleteView.as_view(), name='role_delete'),
]
