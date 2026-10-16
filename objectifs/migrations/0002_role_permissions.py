from django.db import migrations


def grant_permissions(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')
    for model in ['objectifapprentissage', 'tacheapprentissage']:
        ct, _ = ContentType.objects.using(alias).get_or_create(app_label='objectifs', model=model)
        for action in ['add', 'view', 'change', 'delete']:
            perm, _ = Permission.objects.using(alias).get_or_create(content_type=ct, codename=f'{action}_{model}', defaults={'name': f'Can {action} {model}'})
            for group in Group.objects.using(alias).filter(name__in=['Administrateur', 'Enseignant / Coach', 'Apprenant']):
                group.permissions.add(perm)


class Migration(migrations.Migration):
    dependencies = [('objectifs', '0001_initial'), ('auth', '0012_alter_user_first_name_max_length')]
    operations = [migrations.RunPython(grant_permissions, migrations.RunPython.noop)]
