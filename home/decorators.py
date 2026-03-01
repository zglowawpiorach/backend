import logging
from functools import wraps
from django.http import JsonResponse
import traceback

logger = logging.getLogger('api')


def api_error_handler(view_func):
    """Decorator to catch and log exceptions in API views."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except Exception as e:
            # Get DEBUG setting safely
            from django.conf import settings
            debug = getattr(settings, 'DEBUG', False)

            # Log the full error with context
            logger.error(
                "API Error in %s: %s",
                view_func.__name__,
                str(e),
                extra={
                    'view': view_func.__name__,
                    'path': request.path,
                    'method': request.method,
                    'params': dict(request.GET),
                    'traceback': traceback.format_exc(),
                },
                exc_info=True
            )

            # Return user-friendly error response
            return JsonResponse({
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': str(e) if debug else 'An internal error occurred',
                }
            }, status=500)

    return wrapped
