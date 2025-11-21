
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from .serializers import TagSerializer

from tags.models import Tag

from ostdata.custom_permissions import get_allowed_run_objects_to_view_for_user

# ===============================================================
# TAGS
# ===============================================================

class TagFilter(filters.FilterSet):

   class Meta:
      model = Tag
      fields = ['name',]

   #@property
   #def qs(self):
      #parent = super().qs

      #return get_allowed_run_objects_to_view_for_user(parent, self.request.user)


class TagViewSet(viewsets.ModelViewSet):
   queryset = Tag.objects.all()
   serializer_class = TagSerializer
   permission_classes = [IsAuthenticatedOrReadOnly]

   def _has(self, user, codename: str) -> bool:
      try:
         return bool(user and (user.is_superuser or user.has_perm(f'users.{codename}')))
      except Exception:
         return False

   def create(self, request, *args, **kwargs):
      if not self._has(request.user, 'acl_tags_manage'):
         return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
      return super().create(request, *args, **kwargs)

   def update(self, request, *args, **kwargs):
      if not self._has(request.user, 'acl_tags_manage'):
         return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
      return super().update(request, *args, **kwargs)

   def partial_update(self, request, *args, **kwargs):
      if not self._has(request.user, 'acl_tags_manage'):
         return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
      return super().partial_update(request, *args, **kwargs)

   def destroy(self, request, *args, **kwargs):
      if not self._has(request.user, 'acl_tags_manage'):
         return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
      return super().destroy(request, *args, **kwargs)
   filter_backends = (DjangoFilterBackend,)
   filterset_class = TagFilter

