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



    #   Method definitions for the filter definitions above
    def filter_name(self, queryset, name, value):
        return queryset.filter(name__icontains=value)

    def filter_ra(self, queryset, name, value):
        ra_min, ra_max = value.split('--')

        try:
            if ':' in ra_min:
                ra_min = ra_min+'0'
                ra_min = Angle(ra_min, unit='hour').degree
            else:
                ra_min = Angle(ra_min, unit='degree').degree
        except:
            ra_min = Angle(0., unit='degree').degree

        try:
            if ':' in ra_max:
                ra_max = ra_max+'0'
                ra_max = Angle(ra_max, unit='hour').degree
            else:
                ra_max = Angle(ra_max, unit='degree').degree
        except:
            ra_max = Angle(360., unit='degree').degree

        return queryset.filter(ra__range=[ra_min, ra_max])

    def filter_dec(self, queryset, name, value):
        dec_min, dec_max = value.split('--')

        try:
            if ':' in dec_min:
                dec_min = dec_min+'0'
                dec_min = Angle(dec_min, unit='degree').degree
            else:
                dec_min = float(dec_min)
        except:
            dec_min = -90.

        try:
            if ':' in dec_max:
                dec_max = dec_max+'0'
                dec_max = Angle(dec_max, unit='degree').degree
            else:
                dec_max = float(dec_max)
        except:
            dec_max = 90.

        dec_min = Angle(dec_min, unit='degree').degree
        dec_max = Angle(dec_max, unit='degree').degree

        return queryset.filter(dec__range=[dec_min, dec_max])

    def filter_obs_run(self, queryset, name, value):
        year, month, day = value.split('-')

        return queryset.filter(obsrun__name__icontains=year+month+day)

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
