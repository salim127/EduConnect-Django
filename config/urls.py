from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('', include('dashboard.urls')),
    path('comptes/', include('accounts.urls')),
    path('pedagogie/', include('pedagogie.urls')),
    path('coaching/', include('coaching.urls')),
    path('ressources/', include('ressources.urls')),
    path('objectifs/', include('objectifs.urls')),
    path('admin/', admin.site.urls),
]
