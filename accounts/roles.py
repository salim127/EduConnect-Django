from django.contrib.auth.models import Group, Permission

ADMIN = 'Administrateur'
TEACHER = 'Enseignant / Coach'
LEARNER = 'Apprenant'
SYSTEM_ROLES = (ADMIN, TEACHER, LEARNER)


def is_admin(user):
    return user.is_superuser or user.groups.filter(name=ADMIN).exists()


def _perms(models, actions):
    codes = [f'{a}_{m}' for m in models for a in actions]
    return Permission.objects.filter(codename__in=codes, content_type__app_label__in=['auth', 'pedagogie', 'objectifs'])


def ensure_system_roles():
    """Crée les 3 rôles système (une seule fois) avec leurs permissions par défaut."""
    crud = ('add', 'change', 'delete', 'view')
    defaults = {
        ADMIN: _perms(['user', 'group', 'cours', 'exercice', 'objectifapprentissage', 'tacheapprentissage'], crud),
        TEACHER: _perms(['cours', 'exercice', 'objectifapprentissage', 'tacheapprentissage'], crud),
        LEARNER: _perms(['cours', 'exercice'], ('view',)) | _perms(['objectifapprentissage', 'tacheapprentissage'], ('view',)) | Permission.objects.filter(content_type__app_label='objectifs', codename='update_statut_tacheapprentissage'),
    }
    for name, perms in defaults.items():
        group, created = Group.objects.get_or_create(name=name)
        if created:
            group.permissions.set(perms)
