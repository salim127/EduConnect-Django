from uuid import uuid4
from django.db import migrations


def identify_chapters(apps, schema_editor):
    Cours = apps.get_model('pedagogie', 'Cours')
    for course in Cours.objects.all().iterator():
        for chapter in course.chapitres:
            chapter.setdefault('id', str(uuid4()))
        course.save(update_fields=['chapitres'])


class Migration(migrations.Migration):
    dependencies = [('pedagogie', '0004_exercice_chapitre_id_supportcours')]
    operations = [migrations.RunPython(identify_chapters, migrations.RunPython.noop)]
