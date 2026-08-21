from django_filters import rest_framework as filters
from rest_framework.request import Request

from objects.models import Object
from ostdata.custom_permissions import (
    get_allowed_model_to_view_for_user,
)
from tags.models import Tag

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

    #   RA & DEC filter
    ra = filters.CharFilter(
        field_name="ra",
        method='filter_ra',
        lookup_expr='icontains',
    )
    dec = filters.CharFilter(
        field_name="dec",
        method='filter_dec',
        lookup_expr='icontains',
    )

    #   observation run filter
    obs_run = filters.CharFilter(
        field_name="obs_run",
        method='filter_obs_run',
        lookup_expr='icontains',
        )

    #   Tag filter
    tags = filters.ModelMultipleChoiceFilter(queryset=Tag.objects.all())

    #   Object type filter
    object_type = filters.CharFilter(
        field_name="object_type",
        method='filter_object_type',
        lookup_expr='exact',
    )

    #   Method definitions for the filter definitions above
    def filter_name(self, queryset, name, value):
        return queryset.filter(name__icontains=value)

    def filter_object_type(self, queryset, name, value):
        return queryset.filter(object_type=value)

    def filter_ra(self, queryset, name, value):
        if not value:
            return queryset
        try:
            # Check if value is a range (contains '--')
            if '--' in value:
                ra_min, ra_max = value.split('--')
                return queryset.filter(ra__gte=float(ra_min), ra__lte=float(ra_max))
            else:
                # Single value case
                ra_value = float(value)
                return queryset.filter(ra=ra_value)
        except (ValueError, TypeError):
            return queryset

    def filter_dec(self, queryset, name, value):
        if not value:
            return queryset
        try:
            # Check if value is a range (contains '--')
            if '--' in value:
                dec_min, dec_max = value.split('--')
                return queryset.filter(dec__gte=float(dec_min), dec__lte=float(dec_max))
            else:
                # Single value case
                dec_value = float(value)
                return queryset.filter(dec=dec_value)
        except (ValueError, TypeError):
            return queryset

    def filter_obs_run(self, queryset, name, value):
        year, month, day = value.split('-')

        return queryset.filter(observation_run__name__icontains=year+month+day)

    class Meta:
        model = Object
        fields = ['name', 'object_type']
        # fields = ['pk']
        # fields = ['observation_run']


    @property
    def qs(self):
        parent = super().qs
        request = self.request
        assert isinstance(request, Request)

        parent = get_allowed_model_to_view_for_user(
            parent,
            request.user,
            Object,
            )

        #   Get the column order from the GET dictionary
        getter = request.query_params.get
        col = getter('order[0][column]')
        if col is not None:
            order_column = int(col)
            order_name = getter('columns[%i][data]' % order_column)
            if not order_name:
                return parent.order_by('name')
            if getter('order[0][dir]') == 'desc':
                order_name = '-' + order_name

            return parent.order_by(order_name)
        else:
            return parent.order_by('name')
