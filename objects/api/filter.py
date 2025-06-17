from django_filters import rest_framework as filters

from astropy.coordinates import Angle

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
