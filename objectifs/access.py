from accounts.roles import TEACHER, is_admin


def is_manager(user):
    return is_admin(user) or user.groups.filter(name=TEACHER).exists()
