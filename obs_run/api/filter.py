
from django_filters import rest_framework as filters
from django.db.models import Count

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
    #   Date filter
    name = filters.CharFilter(
        field_name="name",
        method='filter_name',
        lookup_expr='icontains',
        )


    #   Status filter
    status = filters.MultipleChoiceFilter(
        field_name="reduction_status",
        choices=Obs_run.REDUCTION_STATUS_CHOICES,
        )

    #   Tag filter
    tags = filters.ModelMultipleChoiceFilter(queryset=Tag.objects.all())

    #   Target filter
    target = filters.CharFilter(
        field_name="object",
        method="target_name_icontains",
        lookup_expr='icontains',
    )

    #   Observation type filter
    # obs_type = filters.BooleanFilter(
    #     # field_name="photometry",
    #     method="obs_type_isnull",
    #     # lookup_expr='isnull',
    # )
    photometry = filters.BooleanFilter(
        field_name="photometry",
    )
    spectroscopy = filters.BooleanFilter(
        field_name="spectroscopy",
    )

    n_datafiles_min = filters.NumberFilter(
        field_name="datafile",
        method='filter_files_gt',
        lookup_expr='gte',
    )
    n_datafiles_max = filters.NumberFilter(
        field_name="datafile",
        method='filter_files_lt',
        lookup_expr='lte',
    )

    exposure_time_min = filters.NumberFilter(
        field_name="datafile",
        method='filter_exposure_time_gt',
        lookup_expr='gte',
    )
    exposure_time_max = filters.NumberFilter(
        field_name="datafile",
        method='filter_exposure_time_lt',
        lookup_expr='lte',
    )


    #   Method definitions for the filter definitions above
    def filter_name(self, queryset, name, value):
        return queryset.filter(name__icontains=value)

    #   Target method
    def target_name_icontains(self, queryset, name, value):
        return queryset.filter(object__name__icontains=value)

    # #   Observation type method
    # def obs_type_isnull(self, queryset, name, value):
    #     print(queryset)
    #     print(queryset[0].photometry)
    #     if value == 'S':
    #         qs = queryset.filter(spectroscopy__isnull==False)
    #     elif value == 'P':
    #         qs = queryset.filter(photometry__isnull==False)
    #     elif value == 'U':
    #         qs = queryset.filter(photometry__isnull==True).filter(spectroscopy__isnull==True)
    #     else:
    #         qs = queryset
    #
    #     return qs

    def filter_files_gt(self, queryset, name, value):
        return queryset.annotate(num_files=Count(name, distinct=True)). \
            filter(num_files__gte=value)

    def filter_files_lt(self, queryset, name, value):
        return queryset.annotate(num_files=Count(name, distinct=True)). \
            filter(num_files__lte=value)
    #
    # def filter_exposure_time_gt(self, queryset, name, value):
    #     return queryset.annotate(expo_time=Count(name, distinct=True)). \
    #         filter(expo_time__gte=value)
    #
    # def filter_exposure_time_lt(self, queryset, name, value):
    #     return queryset.annotate(expo_time=Count(name, distinct=True)). \
    #         filter(expo_time__lte=value)

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
