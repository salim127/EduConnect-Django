from django.urls import path

from . import views as v
from . import ai_views as ai
from . import learning_views as learning
from . import grade_views as grades

app_name = 'pedagogie'
urlpatterns = [
    path('mes-notes/', grades.MyGradesView.as_view(), name='my_grades'),
    path('resultats/', grades.GradebookView.as_view(), name='gradebook'),
    path('tentatives/<int:pk>/', grades.AttemptResultView.as_view(), name='attempt_result'),
    path('tentatives/<int:pk>/autorisation/', grades.RetakePermissionView.as_view(), name='retake_permission'),
    path('cours/', v.CoursListView.as_view(), name='cours_list'),
    path('cours/ajouter/', v.CoursCreateView.as_view(), name='cours_create'),
    path('cours/importer/', v.CoursImportView.as_view(), name='cours_import'),
    path('cours/<int:pk>/chapitres/', v.ChapitresChoicesView.as_view(), name='chapitres_choices'),
    path('cours/<int:pk>/chapitres/<uuid:chapter_id>/revision/', learning.ChapterStudyView.as_view(), name='chapter_study'),
    path('cours/<int:pk>/chapitres/<uuid:chapter_id>/entrainement/', learning.ChapterPracticeView.as_view(), name='chapter_practice'),
    path('cours/<int:pk>/chapitres/<uuid:chapter_id>/generer-exercices/', ai.GenerateChapterExercisesView.as_view(), name='ai_generate'),
    path('cours/<int:pk>/chapitres/<uuid:chapter_id>/assistant/', ai.ChapterAssistantView.as_view(), name='chapter_assistant'),
    path('cours/<int:pk>/exporter/<str:kind>/', v.CoursExportView.as_view(), name='cours_export'),
    path('supports/<int:pk>/telecharger/', v.SupportDownloadView.as_view(), name='support_download'),
    path('cours/<int:pk>/', v.CoursDetailView.as_view(), name='cours_detail'),
    path('cours/<int:pk>/modifier/', v.CoursUpdateView.as_view(), name='cours_update'),
    path('cours/<int:pk>/supprimer/', v.CoursDeleteView.as_view(), name='cours_delete'),
    path('exercices/', v.ExerciceListView.as_view(), name='exercice_list'),
    path('exercices/ajouter/', v.ExerciceCreateView.as_view(), name='exercice_create'),
    path('exercices/<int:pk>/', v.ExerciceDetailView.as_view(), name='exercice_detail'),
    path('exercices/<int:pk>/aide/', learning.ExerciseHelpView.as_view(), name='exercise_help'),
    path('exercices/<int:pk>/modifier/', v.ExerciceUpdateView.as_view(), name='exercice_update'),
    path('exercices/<int:pk>/supprimer/', v.ExerciceDeleteView.as_view(), name='exercice_delete'),
]
