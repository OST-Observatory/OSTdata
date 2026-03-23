"""
Public, non-sensitive settings for the SPA (no authentication required).
"""
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(
    summary='Public UI configuration',
    description=(
        'Non-sensitive limits for the SPA, e.g. async ZIP download job polling. '
        'Values come from Django settings / environment (see DOWNLOAD_JOB_*).'
    ),
)
@api_view(['GET'])
@permission_classes([AllowAny])
def ui_public_config(request):
    return Response(
        {
            'download_job_poll_interval_ms': int(getattr(settings, 'DOWNLOAD_JOB_POLL_INTERVAL_MS', 2000)),
            'download_job_max_wait_ms': int(getattr(settings, 'DOWNLOAD_JOB_MAX_WAIT_MS', 45 * 60 * 1000)),
        }
    )
