"""Central DRF exception handler with safe client responses and server-side logging."""
import logging

from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        view = context.get('view')
        view_name = getattr(view, '__class__', type('x', (), {})).__name__
        logger.exception('Unhandled API exception in %s', view_name, exc_info=exc)
        from rest_framework.response import Response
        return Response({'detail': 'An unexpected error occurred.'}, status=500)
    return response
