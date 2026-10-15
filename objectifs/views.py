from django.views.generic import TemplateView

from . import demo


class ObjectifsView(TemplateView):
    template_name = 'objectifs/objectifs.html'
    extra_context = {'objectifs': demo.OBJECTIFS}


class TachesView(TemplateView):
    template_name = 'objectifs/taches.html'
    extra_context = {'groupes': demo.TACHES}
