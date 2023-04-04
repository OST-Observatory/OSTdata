from django_filters import rest_framework as filters

from objects.models import Object
from tags.models import Tag

from ostdata.custom_permissions import (
    get_allowed_model_to_view_for_user,
    )

# ===============================================================
#   OBJECTS
# ===============================================================

class ObjectFilter(filters.FilterSet):
    '''
        Filter definitions for table with observation runs
    '''
    #   Name filter
    name = filters.CharFilter(
        field_name="name",
        method='filter_name',
        lookup_expr='icontains',
        )

    #   Tag filter
    tags = filters.ModelMultipleChoiceFilter(queryset=Tag.objects.all())

    #   Method definitions for the filter definitions above
    def filter_name(self, queryset, name, value):
        return queryset.filter(name__icontains=value)


    class Meta:
        model = Object
        fields = ['name']
        # fields = ['pk']
        # fields = ['obsrun']

    @property
    def qs(self):
        parent = super().qs

        parent = get_allowed_model_to_view_for_user(
            parent,
            self.request.user,
            Object,
            )

        #   Get the column order from the GET dictionary
        getter = self.request.query_params.get
        if not getter('order[0][column]') is None:
            order_column = int(getter('order[0][column]'))
            order_name = getter('columns[%i][data]' % order_column)
            if getter('order[0][dir]') == 'desc': order_name = '-'+order_name

            return parent.order_by(order_name)
        else:
            return parent.order_by('name')
