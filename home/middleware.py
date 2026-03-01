import logging
import time

logger = logging.getLogger('api')


class RequestLoggingMiddleware:
    """Middleware to log API requests and responses with timing information."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()

        # Log incoming request
        logger.info(
            "API Request: %s %s",
            request.method,
            request.path,
            extra={
                'method': request.method,
                'path': request.path,
                'params': dict(request.GET),
            }
        )

        response = self.get_response(request)

        # Log response
        duration = time.time() - start_time
        logger.info(
            "API Response: %s %s - %d (%.2fs)",
            request.method,
            request.path,
            response.status_code,
            duration,
        )

        return response
