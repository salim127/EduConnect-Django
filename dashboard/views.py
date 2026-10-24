from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.models import Group, User
from django.db.models import Count
from django.shortcuts import redirect, render
from django.views.generic import TemplateView

from pedagogie.models import Cours, Exercice
from pedagogie.visibility import visible_courses, visible_exercises


@login_not_required
def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard:home')
    return render(request, 'dashboard/landing.html')


class HomeView(TemplateView):
    template_name = 'dashboard/home.html'

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        courses, exercises = visible_courses(self.request.user), visible_exercises(self.request.user)
        ctx['nb_cours'] = courses.count()
        ctx['nb_exercices'] = exercises.count()
        ctx['nb_users'] = User.objects.count()
        ctx['nb_roles'] = Group.objects.count()
        ctx['recent_cours'] = courses.select_related('enseignant')[:3]
        # Données réelles pour le graphique
        par_diff = dict(exercises.values_list('difficulte').annotate(n=Count('id')))
        ctx['chart_labels'] = [lbl for _, lbl in Exercice.DIFFICULTES]
        ctx['chart_data'] = [par_diff.get(k, 0) for k, _ in Exercice.DIFFICULTES]
        return ctx
