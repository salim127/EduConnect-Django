from django import forms

from accounts.roles import is_admin
from config.forms import BootstrapFormMixin

from .models import Cours, Exercice
from .richtext import clean_content
from .office import read_office, validate_support
from .learning import parse_rubric


RUBRIC_HELP = 'Questions ouvertes uniquement. Une ligne par critère : Description | points. Exemple : Définition correcte | 2'


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        if len(files) > 10:
            raise forms.ValidationError('Sélectionnez au maximum 10 fichiers par envoi.')
        if not files:
            if self.required:
                raise forms.ValidationError('Sélectionnez au moins un fichier.')
            return []
        if sum(f.size for f in files) > 50 * 1024 * 1024:
            raise forms.ValidationError('L’ensemble des fichiers ne doit pas dépasser 50 Mo.')
        return [super(MultipleFileField, self).clean(f, initial) for f in files]


class CourseRichTextarea(forms.Textarea):
    def format_value(self, value):
        return clean_content(value) if value else ''


class CoursForm(BootstrapFormMixin, forms.ModelForm):
    fichiers = MultipleFileField(required=False, label='Supports PDF, Word ou PowerPoint',
        widget=MultipleFileInput(attrs={'accept': '.pdf,.docx,.pptx'}),
        help_text='Pièces jointes téléchargeables. 10 fichiers maximum, 15 Mo par fichier.')
    class Meta:
        model = Cours
        fields = ('titre', 'description', 'matiere', 'niveau', 'contenu', 'masque')
        widgets = {'description': forms.Textarea(attrs={'rows': 3}), 'contenu': CourseRichTextarea(attrs={'rows': 10, 'data-rich-editor': ''})}


    def clean_contenu(self):
        return clean_content(self.cleaned_data['contenu'])

    def clean_fichiers(self):
        files = self.cleaned_data['fichiers']
        for upload in files:
            validate_support(upload)
        return files


class ImportCoursForm(BootstrapFormMixin, forms.Form):
    fichiers = MultipleFileField(label='Fichiers de cours',
        widget=MultipleFileInput(attrs={'accept': '.docx,.pptx'}))
    matiere = forms.CharField(label='Matière', max_length=100)
    niveau = forms.ChoiceField(choices=Cours.NIVEAUX)

    def clean_fichiers(self):
        files = self.cleaned_data['fichiers']
        self.documents = []
        for upload in files:
            try:
                self.documents.append((upload, *read_office(upload)))
            except forms.ValidationError as exc:
                raise forms.ValidationError(f'{upload.name} : {" ".join(exc.messages)}') from exc
        return files


class ChapitreForm(BootstrapFormMixin, forms.Form):
    id = forms.UUIDField(required=False, widget=forms.HiddenInput())
    titre = forms.CharField(max_length=200)
    masque = forms.BooleanField(required=False, label='Masquer ce chapitre aux étudiants')
    contenu = forms.CharField(required=False, widget=CourseRichTextarea(attrs={'rows': 8, 'data-rich-editor': ''}))
    fichiers = MultipleFileField(required=False, label='Documents de ce chapitre',
        widget=MultipleFileInput(attrs={'accept': '.pdf,.docx'}),
        help_text='PDF ou Word (.docx), plusieurs fichiers possibles. 15 Mo par fichier, 10 fichiers maximum.')

    def clean_fichiers(self):
        files = self.cleaned_data['fichiers']
        from pathlib import Path
        for upload in files:
            if Path(upload.name).suffix.lower() not in ('.pdf', '.docx'):
                raise forms.ValidationError('Pour un chapitre, choisissez un document PDF ou Word (.docx).')
            validate_support(upload)
        return files

    def clean_contenu(self):
        return clean_content(self.cleaned_data['contenu'])

    def clean(self):
        data = super().clean()
        from django.utils.html import strip_tags
        content = data.get('contenu', '')
        if not strip_tags(content).strip() and '<img ' not in content and not data.get('fichiers') and not getattr(self, 'supports_existants', []):
            self.add_error('contenu', 'Rédigez le contenu ou ajoutez un document PDF / Word.')
        return data


ChapitreFormSet = forms.formset_factory(ChapitreForm, extra=0, can_delete=True, max_num=100, validate_max=True)


class ExerciceForm(BootstrapFormMixin, forms.ModelForm):
    chapitre_id = forms.ChoiceField(label='Chapitre', required=False)
    class Meta:
        model = Exercice
        fields = ('titre', 'cours', 'chapitre_id', 'type_exercice', 'difficulte', 'question', 'propositions', 'bonne_reponse', 'explication', 'bareme')
        widgets = {
            'question': forms.Textarea(attrs={'rows': 3}),
            'propositions': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Choix A\nChoix B\nChoix C'}),
            'bonne_reponse': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Cours.objects.all() if is_admin(user) else Cours.objects.filter(enseignant=user)
        self.fields['cours'].queryset = qs
        self.fields['bareme'].help_text = RUBRIC_HELP
        self.fields['bareme'].widget = forms.Textarea(attrs={'rows': 3, 'class': 'form-control'})
        cid = self.data.get('cours') if self.is_bound else self.initial.get('cours', self.instance.cours_id)
        course = qs.filter(pk=cid).first() if str(cid).isdigit() else None
        self.fields['chapitre_id'].choices = [('', 'Exercice général du cours')] + [
            (c['id'], f'{i}. {c["titre"]}') for i, c in enumerate(course.chapitres, 1)] if course else [('', 'Choisir un cours d’abord')]

    def clean_bareme(self):
        value = self.cleaned_data.get('bareme', '') if self.data.get('type_exercice') == 'ouverte' else ''
        parse_rubric(value)
        return value


class QuestionQCMForm(BootstrapFormMixin, forms.Form):
    question = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}))
    propositions = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), help_text='Une proposition par ligne.')
    bonne_reponse = forms.CharField(label='Bonne réponse', help_text='Recopiez une des propositions.')
    explication = forms.CharField(required=False, label='Explication de la réponse', widget=forms.Textarea(attrs={'rows': 2}),
        help_text='Affichée après la vérification de la réponse.')
    bareme = forms.CharField(required=False, max_length=3000, label='Barème de correction',
        widget=forms.Textarea(attrs={'rows': 3}), help_text=RUBRIC_HELP)

    def __init__(self, *args, type_exercice='qcm', **kwargs):
        super().__init__(*args, **kwargs)
        self.type_exercice = type_exercice
        if type_exercice != 'qcm':
            self.fields['propositions'].required = False
            if type_exercice == 'vf':
                self.fields['bonne_reponse'] = forms.ChoiceField(
                    label='Bonne réponse', choices=[('', 'Choisir'), ('Vrai', 'Vrai'), ('Faux', 'Faux')],
                    widget=forms.Select(attrs={'class': 'form-select'}))
            else:
                self.fields['bonne_reponse'].widget = forms.Textarea(attrs={'rows': 3, 'class': 'form-control'})
                self.fields['bonne_reponse'].help_text = 'Réponse attendue (modèle de correction).'

    def clean(self):
        data = super().clean()
        if self.type_exercice == 'ouverte':
            try:
                parse_rubric(data.get('bareme', ''))
            except forms.ValidationError as error:
                self.add_error('bareme', error)
        else:
            data['bareme'] = ''
        if self.type_exercice != 'qcm':
            data['propositions'] = ''
            return data
        props = [p.strip() for p in data.get('propositions', '').splitlines() if p.strip()]
        if len(props) < 2:
            self.add_error('propositions', 'Ajoutez au moins deux propositions.')
        answer = data.get('bonne_reponse', '').strip()
        match = next((p for p in props if p.casefold() == answer.casefold()), None)
        if match is None:
            self.add_error('bonne_reponse', 'La réponse doit correspondre à une proposition.')
        else:
            data['bonne_reponse'] = match
        data['propositions'] = '\n'.join(props)
        return data


QuestionQCMFormSet = forms.formset_factory(QuestionQCMForm, extra=0, can_delete=True, max_num=100, validate_max=True)


class AIGenerateForm(BootstrapFormMixin, forms.Form):
    nombre = forms.IntegerField(label='Nombre de questions', min_value=1, max_value=10, initial=5)
    type_exercice = forms.ChoiceField(label='Type de questions', choices=Exercice.TYPES)
    difficulte = forms.ChoiceField(label='Difficulté', choices=Exercice.DIFFICULTES, initial='moyen')


class AIExerciseTitleForm(BootstrapFormMixin, forms.Form):
    titre = forms.CharField(label='Titre de l’exercice', max_length=200)


AIPreviewFormSet = forms.formset_factory(QuestionQCMForm, extra=0, can_delete=True,
    min_num=1, validate_min=True, max_num=10, validate_max=True)
