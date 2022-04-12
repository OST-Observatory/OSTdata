
from rest_framework.serializers import ModelSerializer

from tags.models import Tag

# ===============================================================
# TAGS
# ===============================================================

class TagSerializer(ModelSerializer):

   class Meta:
      model = Tag
      fields = [
            'name',
            'description',
            'color',
            'pk',
      ]
      read_only_fields = ('pk',)

#class SimpleTagSerializer(ModelSerializer):

   #class Meta:
      #model = Tag
      #fields = [
            #'name',
            #'color',
            #'description',
      #]
