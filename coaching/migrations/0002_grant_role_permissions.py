from django.db import migrations


def grant_coaching_permissions(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    permissions = Permission.objects.using(schema_editor.connection.alias).filter(content_type__app_label='coaching')
    models = ('sessioncoaching', 'conseilpedagogique')
    for group in Group.objects.using(schema_editor.connection.alias).filter(name='Apprenant'):
        group.permissions.add(*permissions.filter(content_type__model__in=models, codename__startswith='view_'))
    for group in Group.objects.using(schema_editor.connection.alias).filter(name__in=['Administrateur', 'Enseignant / Coach']):
        group.permissions.add(*permissions.filter(content_type__model__in=models))


class Migration(migrations.Migration):
    dependencies = [('coaching', '0001_initial')]
    operations = [migrations.RunPython(grant_coaching_permissions, migrations.RunPython.noop)]
