from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import Group, Permission, User

from config.forms import BootstrapFormMixin

from .roles import LEARNER, SYSTEM_ROLES

PERM_MODELS = [('auth', 'user'), ('auth', 'group'), ('pedagogie', 'cours'), ('pedagogie', 'exercice'), ('objectifs', 'objectifapprentissage'), ('objectifs', 'tacheapprentissage'), ('ressources', 'categorie'), ('ressources', 'ressource')]
ACTIONS = {'add': 'Ajouter', 'change': 'Modifier', 'delete': 'Supprimer', 'view': 'Consulter'}


class HubAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    pass


class RegisterForm(BootstrapFormMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email')

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields['email'].required = True

    def save(self, commit=True):
        user = super().save(commit)
        user.groups.add(Group.objects.get(name=LEARNER))
        return user


class UserCreateForm(BootstrapFormMixin, UserCreationForm):
    role = forms.ModelChoiceField(queryset=Group.objects.order_by('name'), label='Rôle')
    is_active = forms.BooleanField(required=False, initial=True, label='Compte actif')

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = self.cleaned_data['is_active']
        user.save()
        user.groups.set([self.cleaned_data['role']])
        return user


class UserUpdateForm(BootstrapFormMixin, forms.ModelForm):
    role = forms.ModelChoiceField(queryset=Group.objects.order_by('name'), label='Rôle')

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email', 'is_active')
        labels = {'is_active': 'Compte actif'}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields['role'].initial = self.instance.groups.first()

    def save(self, commit=True):
        user = super().save(commit)
        user.groups.set([self.cleaned_data['role']])
        return user


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email')


class PasswordForm(BootstrapFormMixin, PasswordChangeForm):
    pass


class RoleForm(BootstrapFormMixin, forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(), required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Group
        fields = ('name', 'permissions')
        labels = {'name': 'Nom du rôle'}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        perms = Permission.objects.filter(
            content_type__app_label__in=['auth', 'pedagogie', 'objectifs'],
            content_type__model__in=[m for _, m in PERM_MODELS],
        ).select_related('content_type')
        self.fields['permissions'].queryset = perms
        if self.instance.pk and self.instance.name in SYSTEM_ROLES:
            self.fields['name'].disabled = True  # rôle système protégé
            self.fields['name'].help_text = 'Rôle système : le nom ne peut pas être modifié.'
        selected = {str(v) for v in (self['permissions'].value() or [])}
        by_code = {(p.content_type.model, p.codename.split('_')[0]): p for p in perms}
        self.perm_groups = [
            (model.capitalize(), [(label, by_code[(model, act)], str(by_code[(model, act)].pk) in selected)
                                  for act, label in ACTIONS.items() if (model, act) in by_code])
            for _, model in PERM_MODELS
        ]
