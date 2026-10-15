from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _create_roles(sender, **kwargs):
    from django.apps import apps
    from django.contrib.auth.management import create_permissions

    for label in ('auth', 'pedagogie'):
        create_permissions(apps.get_app_config(label), verbosity=0)
    from .roles import ensure_system_roles
    ensure_system_roles()


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        post_migrate.connect(_create_roles, sender=self)
