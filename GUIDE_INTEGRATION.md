# Guide d'intégration

## 1. Organisation

```
config/       settings, urls racine, forms.py (BootstrapFormMixin), mixins.py (QueryStringMixin)
accounts/     User + Role (CRUD) ; roles.py = constantes de rôles et is_admin()
pedagogie/    Cours + Exercice (CRUD)
coaching/ ressources/ objectifs/   pages statiques : views.py + demo.py (données fictives) + urls.py
dashboard/    accueil public + tableau de bord
templates/    base.html, auth_base.html, components/, <app>/
static/       css/hub.css (design system), js/hub.js, images/
```

## 2. Conventions

- Une app = un `app_name` (namespace d'URL). Noms d'URL : `<entité>_list`, `_detail`, `_create`, `_update`, `_delete`.
- Templates : `templates/<app>/<entité>_list.html`, `_detail.html`, `_form.html`.
- Vues basées sur classes (`ListView`, `CreateView`…), `PermissionRequiredMixin`.
- Formulaires : `ModelForm` + `BootstrapFormMixin` (config/forms.py).
- Français pour l'interface et les noms de champs métier.

## 3. Intégrer un futur CRUD (ex. `SessionCoaching`)

1. Dans `coaching/models.py` : créer le modèle, puis `python manage.py makemigrations coaching && migrate`.
2. Créer `coaching/forms.py` (ModelForm avec `BootstrapFormMixin`) et remplacer dans `coaching/views.py` la vue statique par des vues CRUD. Pour la pagination, hériter de `QueryStringMixin` (config/mixins.py).
3. Remplacer `demo.py` par des requêtes ORM : supprimer la bannière `components/demo_banner.html` et les badges « Démo » des templates concernés, remplacer `soon_button.html` par de vrais boutons.
4. Les permissions `add/change/delete/view_<modèle>` sont créées par Django automatiquement ; attribuez-les aux rôles depuis **Administration → Rôles**. Pour que les rôles système les reçoivent par défaut, ajoutez le modèle dans `accounts/roles.py` (`ensure_system_roles`) et dans `PERM_MODELS` de `accounts/forms.py` pour les afficher dans l'écran des rôles.
5. Retirer le tag `DÉMO` de la ligne correspondante dans `templates/base.html`.

## 4. Ajouter des URL

Dans `coaching/urls.py` (déjà inclus par `config/urls.py` sous `coaching/`) :

```python
path('sessions/ajouter/', views.SessionCreateView.as_view(), name='session_create'),
```

Pour une nouvelle app : l'ajouter à `INSTALLED_APPS` et dans `config/urls.py`, puis ajouter son lien dans la sidebar (`templates/base.html`). L'état actif se base sur `request.resolver_match.view_name`.

## 5. Composants graphiques

| Besoin | Utiliser |
|---|---|
| Champ de formulaire | `{% include "components/field.html" with field=form.titre %}` |
| Pagination | `{% include "components/pagination.html" %}` (liste paginée + `QueryStringMixin`) |
| État vide | `{% include "components/empty.html" with icon="bi-inbox" title="…" text="…" %}` |
| Suppression | bouton `data-bs-toggle="modal" data-bs-target="#deleteModal" data-url="{% url … %}" data-name="…"` (modale dans base.html, POST) |
| Bouton « Bientôt disponible » | `components/soon_button.html` |
| Bandeau démonstration | `components/demo_banner.html` |
| Cartes, badges, tableaux | classes `card-x`, `badge-soft badge-primary/teal/amber`, `table-x`, `icon-box tone-*` (static/css/hub.css) |

Page type : étendre `base.html` et remplir les blocs `title`, `page_title`, `crumbs`, `content`.

## 6. Authentification

- Toutes les pages exigent une connexion (`LoginRequiredMiddleware`) sauf celles décorées `@login_not_required` (accueil, connexion, inscription).
- Utilisateur : `django.contrib.auth.models.User` ; rôle = groupe Django (`user.groups.first`).
- Protéger une vue : `PermissionRequiredMixin` + `permission_required = 'app.view_modele'`.
- Dans les templates : `{% if perms.app.add_modele %}`.
- Propriété d'un objet : voir `OwnerOrAdminMixin` (pedagogie/views.py) et les filtres `can_edit` / `can_delete` (pedagogie/templatetags).
- Lien vers un utilisateur : `settings.AUTH_USER_MODEL` pour les ForeignKey, ne pas remplacer le modèle User.
