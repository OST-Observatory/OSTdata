
from django_filters import rest_framework as filters

from obs_run.models import Obs_run, DataFile
from tags.models import Tag

from ostdata.custom_permissions import (
    get_allowed_model_to_view_for_user,
    get_allowed_run_objects_to_view_for_user,
    )

# ===============================================================
#   OBSERVATION RUNS
# ===============================================================

class RunFilter(filters.FilterSet):
    '''
        Filter definitions for table with observation runs
    '''
    #   Name filter
    name = filters.CharFilter(
        field_name="name",
        method='filter_name',
        lookup_expr='icontains',
        )


    #   Status filter
    status = filters.MultipleChoiceFilter(
        field_name="observing_status",
        choices=Obs_run.REDUCTION_STATUS_CHOICES,
        )

    #   Tag filter
    tags = filters.ModelMultipleChoiceFilter(queryset=Tag.objects.all())

    #   Method definitions for the filter definitions above
    def filter_name(self, queryset, name, value):
        return queryset.filter(name__icontains=value)

    class Meta:
        model = Obs_run
        fields = ['name']

    @property
    def qs(self):
        parent = super().qs

        parent = get_allowed_model_to_view_for_user(
            parent,
            self.request.user,
            Obs_run,
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


# ===============================================================
#   DATA FILE
# ===============================================================

class DataFileFilter(filters.FilterSet):
    '''
        Filter definitions for table with observation runs
    '''
    #   File type filter
    file_type = filters.CharFilter(
        field_name="file_type",
        # method='filter_name',
        lookup_expr='icontains',
        )


    #   Exposure time filter
    exposure_type = filters.MultipleChoiceFilter(
        field_name="exposure_type",
        choices=DataFile.EXPOSURE_TYPE_POSSIBILITIES,
        )

    #   Tag filter
    tags = filters.ModelMultipleChoiceFilter(queryset=Tag.objects.all())

    # #   Method definitions for the filter definitions above
    # def filter_name(self, queryset, name, value):
    #     return queryset.filter(name__icontains=value)

    class Meta:
        model = DataFile
        fields = ['obsrun']

    @property
    def qs(self):
        parent = super().qs

        parent = get_allowed_run_objects_to_view_for_user(parent, self.request.user)

        #   Get the column order from the GET dictionary
        getter = self.request.query_params.get
        if not getter('order[0][column]') is None:
            order_column = int(getter('order[0][column]'))
            order_name = getter('columns[%i][data]' % order_column)
            if getter('order[0][dir]') == 'desc': order_name = '-'+order_name

            return parent.order_by(order_name)
        else:
            return parent.order_by('obsrun')
