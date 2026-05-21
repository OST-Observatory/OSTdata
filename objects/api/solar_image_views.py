import mimetypes

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from objects.models import Object
from objects.solar_system_images import (
    ALLOWED_UPLOAD_CONTENT_TYPES,
    delete_image_for_object,
    find_image_path_for_object,
    get_images_directory,
    image_info_for_object,
    save_image_for_object,
    sanitize_object_image_stem,
)
from ostdata.permissions import HasPerm


def _object_visible(request, obj):
    if getattr(request.user, 'is_authenticated', False):
        return True
    return bool(getattr(obj, 'is_public', False))


@extend_schema(summary='Solar-system object preview image', tags=['Objects'])
@api_view(['GET'])
@permission_classes([AllowAny])
def object_solar_image(request, pk: int):
    obj = get_object_or_404(Object, pk=pk)
    if not _object_visible(request, obj):
        raise Http404
    if obj.object_type != 'SO':
        raise Http404
    path = find_image_path_for_object(obj)
    if not path:
        raise Http404
    content_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path.open('rb'), content_type=content_type or 'image/jpeg')


@extend_schema(summary='List solar-system objects and image status', tags=['Admin'])
@api_view(['GET'])
@permission_classes([IsAuthenticated, HasPerm('acl_objects_edit')])
def admin_list_solar_system_images(request):
    qs = Object.objects.filter(object_type='SO').order_by('name')
    items = []
    for obj in qs:
        has_image, url, stem = image_info_for_object(obj, request)
        items.append({
            'pk': obj.pk,
            'name': obj.name,
            'is_public': obj.is_public,
            'sanitized_filename': stem,
            'has_image': has_image,
            'image_url': url,
        })
    return Response({
        'directory': str(get_images_directory()),
        'items': items,
    })


@extend_schema(summary='Upload solar-system object image', tags=['Admin'])
@api_view(['POST'])
@permission_classes([IsAuthenticated, HasPerm('acl_objects_edit')])
@parser_classes([MultiPartParser, FormParser])
def admin_upload_solar_system_image(request):
    object_id = request.data.get('object_id') or request.POST.get('object_id')
    if object_id is None:
        return Response({'detail': 'object_id is required'}, status=400)
    try:
        obj = Object.objects.get(pk=int(object_id))
    except (Object.DoesNotExist, TypeError, ValueError):
        return Response({'detail': 'Object not found'}, status=404)
    if obj.object_type != 'SO':
        return Response({'detail': 'Object is not a solar-system object (type SO)'}, status=400)
    uploaded = request.FILES.get('file') or request.FILES.get('image')
    if not uploaded:
        return Response({'detail': 'file is required'}, status=400)
    content_type = (getattr(uploaded, 'content_type', '') or '').lower()
    if content_type and content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        return Response({'detail': f'Unsupported image type: {content_type}'}, status=400)
    path = save_image_for_object(obj, uploaded)
    has_image, url, stem = image_info_for_object(obj, request)
    return Response({
        'pk': obj.pk,
        'sanitized_filename': stem,
        'saved_as': path.name,
        'has_image': has_image,
        'image_url': url,
    })


@extend_schema(summary='Delete solar-system object image', tags=['Admin'])
@api_view(['DELETE'])
@permission_classes([IsAuthenticated, HasPerm('acl_objects_edit')])
def admin_delete_solar_system_image(request, object_id: int):
    try:
        obj = Object.objects.get(pk=object_id, object_type='SO')
    except Object.DoesNotExist:
        return Response({'detail': 'Solar-system object not found'}, status=404)
    deleted = delete_image_for_object(obj)
    return Response({'deleted': deleted, 'sanitized_filename': sanitize_object_image_stem(obj.name)})
