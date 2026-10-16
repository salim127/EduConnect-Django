from django.db import migrations


def assign_and_update_roles(apps, schema_editor):
    alias = schema_editor.connection.alias
    Goal = apps.get_model('objectifs', 'ObjectifApprentissage')
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    # Les anciens objectifs personnels des apprenants leur restent attribués.
    for goal in Goal.objects.using(alias).filter(apprenant__isnull=True, proprietaire__groups__name='Apprenant').distinct():
        goal.apprenant_id = goal.proprietaire_id
        goal.save(using=alias, update_fields=['apprenant'])
    ct, _ = ContentType.objects.using(alias).get_or_create(app_label='objectifs', model='tacheapprentissage')
    status, _ = Permission.objects.using(alias).get_or_create(content_type=ct, codename='update_statut_tacheapprentissage', defaults={'name': 'Mettre à jour le statut de ses tâches'})
    perms = Permission.objects.using(alias).filter(content_type__app_label='objectifs')
    for group in Group.objects.using(alias).filter(name='Apprenant'):
        group.permissions.remove(*perms)
        group.permissions.add(*perms.filter(codename__in=['view_objectifapprentissage', 'view_tacheapprentissage']), status)
    for group in Group.objects.using(alias).filter(name__in=['Administrateur', 'Enseignant / Coach']):
        group.permissions.add(*perms.exclude(pk=status.pk))


class Migration(migrations.Migration):
    dependencies = [('objectifs', '0003_alter_tacheapprentissage_options_and_more')]
    operations = [migrations.RunPython(assign_and_update_roles, migrations.RunPython.noop)]
