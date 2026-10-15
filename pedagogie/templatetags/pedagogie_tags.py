from django import template

from accounts.roles import is_admin

register = template.Library()


def _allowed(obj, user, action):
    perm = f'pedagogie.{action}_{obj._meta.model_name}'
    return user.has_perm(perm) and (is_admin(user) or obj.enseignant == user)


@register.filter
def can_edit(obj, user):
    return _allowed(obj, user, 'change')


@register.filter
def can_delete(obj, user):
    return _allowed(obj, user, 'delete')
