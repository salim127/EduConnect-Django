from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.auth.models import Group, User
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView, View

from config.mixins import QueryStringMixin

from .forms import HubAuthenticationForm, PasswordForm, ProfileForm, RegisterForm, RoleForm, UserCreateForm, UserUpdateForm
from .roles import SYSTEM_ROLES


@method_decorator(login_not_required, name='dispatch')
class HubLoginView(LoginView):
    authentication_form = HubAuthenticationForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True


@method_decorator(login_not_required, name='dispatch')
class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('accounts:login')

    def form_valid(self, form):
        messages.success(self.request, 'Compte créé : vous pouvez vous connecter.')
        return super().form_valid(form)


class ProfileView(TemplateView):
    template_name = 'accounts/profile.html'


class ProfileEditView(UpdateView):
    form_class = ProfileForm
    template_name = 'accounts/profile_form.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Profil mis à jour.')
        return super().form_valid(form)


class PasswordView(PasswordChangeView):
    form_class = PasswordForm
    template_name = 'accounts/password_form.html'
    success_url = reverse_lazy('accounts:profile')

    def form_valid(self, form):
        messages.success(self.request, 'Mot de passe modifié.')
        return super().form_valid(form)


# ---------- Utilisateurs (administration) ----------
class UserListView(PermissionRequiredMixin, QueryStringMixin, ListView):
    permission_required = 'auth.view_user'
    template_name = 'accounts/user_list.html'
    paginate_by = 10

    def get_queryset(self):
        qs = User.objects.prefetch_related('groups').order_by('-date_joined')
        g = self.request.GET
        if q := g.get('q', '').strip():
            qs = qs.filter(Q(username__icontains=q) | Q(first_name__icontains=q)
                           | Q(last_name__icontains=q) | Q(email__icontains=q))
        if g.get('role', '').isdigit():
            qs = qs.filter(groups__pk=g['role'])
        if g.get('actif') in ('1', '0'):
            qs = qs.filter(is_active=g['actif'] == '1')
        return qs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx['roles'] = Group.objects.order_by('name')
        return ctx


class UserCreateView(PermissionRequiredMixin, CreateView):
    permission_required = 'auth.add_user'
    form_class = UserCreateForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')

    def form_valid(self, form):
        messages.success(self.request, 'Utilisateur créé.')
        return super().form_valid(form)


class UserUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = 'auth.change_user'
    model = User
    form_class = UserUpdateForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')

    def form_valid(self, form):
        if self.object == self.request.user and not form.cleaned_data['is_active']:
            form.add_error('is_active', 'Vous ne pouvez pas désactiver votre propre compte.')
            return self.form_invalid(form)
        messages.success(self.request, 'Utilisateur modifié.')
        return super().form_valid(form)


class UserToggleView(PermissionRequiredMixin, View):
    permission_required = 'auth.change_user'
    http_method_names = ['post']

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user == request.user:
            messages.error(request, 'Vous ne pouvez pas désactiver votre propre compte.')
        else:
            user.is_active = not user.is_active
            user.save(update_fields=['is_active'])
            messages.success(request, f'Compte {"activé" if user.is_active else "désactivé"}.')
        return redirect('accounts:user_list')


class UserDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = 'auth.delete_user'
    model = User
    http_method_names = ['post']
    success_url = reverse_lazy('accounts:user_list')

    def form_valid(self, form):
        if self.object == self.request.user or self.object.is_superuser:
            messages.error(self.request, 'Ce compte ne peut pas être supprimé.')
        else:
            try:
                self.object.delete()
                messages.success(self.request, 'Utilisateur supprimé.')
            except ProtectedError:
                messages.error(self.request, 'Cet utilisateur possède des cours : désactivez son compte à la place.')
        return redirect(self.success_url)


# ---------- Rôles ----------
class RoleListView(PermissionRequiredMixin, QueryStringMixin, ListView):
    permission_required = 'auth.view_group'
    template_name = 'accounts/role_list.html'
    paginate_by = 10

    def get_queryset(self):
        qs = Group.objects.annotate(nb_users=Count('user', distinct=True), nb_perms=Count('permissions', distinct=True)).order_by('name')
        if q := self.request.GET.get('q', '').strip():
            qs = qs.filter(name__icontains=q)
        return qs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx['system_roles'] = SYSTEM_ROLES
        return ctx


class RoleCreateView(PermissionRequiredMixin, CreateView):
    permission_required = 'auth.add_group'
    form_class = RoleForm
    template_name = 'accounts/role_form.html'
    success_url = reverse_lazy('accounts:role_list')

    def form_valid(self, form):
        messages.success(self.request, 'Rôle créé.')
        return super().form_valid(form)


class RoleUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = 'auth.change_group'
    model = Group
    form_class = RoleForm
    template_name = 'accounts/role_form.html'
    success_url = reverse_lazy('accounts:role_list')

    def form_valid(self, form):
        messages.success(self.request, 'Rôle modifié.')
        return super().form_valid(form)


class RoleDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = 'auth.delete_group'
    model = Group
    http_method_names = ['post']
    success_url = reverse_lazy('accounts:role_list')

    def form_valid(self, form):
        if self.object.name in SYSTEM_ROLES:
            messages.error(self.request, 'Les rôles système sont protégés.')
        elif self.object.user_set.exists():
            messages.error(self.request, 'Ce rôle est attribué à des utilisateurs.')
        else:
            self.object.delete()
            messages.success(self.request, 'Rôle supprimé.')
        return redirect(self.success_url)
