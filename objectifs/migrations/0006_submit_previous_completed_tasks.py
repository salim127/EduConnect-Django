from django.db import migrations


def submit_completed(apps, schema_editor):
    Task = apps.get_model('objectifs', 'TacheApprentissage')
    Task.objects.using(schema_editor.connection.alias).filter(statut='terminee').update(statut='soumise')


def restore_completed(apps, schema_editor):
    Task = apps.get_model('objectifs', 'TacheApprentissage')
    Task.objects.using(schema_editor.connection.alias).filter(statut__in=['soumise', 'validee', 'a_reprendre']).update(statut='terminee')


class Migration(migrations.Migration):
    dependencies = [('objectifs', '0005_objectifapprentissage_critere_reussite_and_more')]
    operations = [migrations.RunPython(submit_completed, restore_completed)]
