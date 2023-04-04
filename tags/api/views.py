
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters

from rest_framework import viewsets

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

   filter_backends = (DjangoFilterBackend,)
   filterset_class = TagFilter

