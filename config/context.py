from django.conf import settings


def assets(request):
    return {'ASSET_V': settings.ASSET_VERSION}
