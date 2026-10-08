from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """
    View decorator:

        @role_required('Engineer', 'Admin')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            if request.user.groups.filter(name__in=roles).exists():
                return view_func(request, *args, **kwargs)

            raise PermissionDenied(
                'You do not have permission to access this page.'
            )

        return _wrapped_view

    return decorator
