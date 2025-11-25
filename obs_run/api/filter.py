
from django_filters import rest_framework as filters
from django.db.models import Count, F, FloatField, ExpressionWrapper, Q
import re

from obs_run.models import ObservationRun, DataFile
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
        choices=ObservationRun.REDUCTION_STATUS_CHOICES,
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

    # Exposure time filters removed (not implemented server-side for runs)


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
        model = ObservationRun
        fields = ['name']

    @property
    def qs(self):
        parent = super().qs

        parent = get_allowed_model_to_view_for_user(
            parent,
            self.request.user,
            ObservationRun,
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

    instrument = filters.CharFilter(
        field_name="instrument",
        lookup_expr='icontains',
    )

    #   Main target filter (tokenized, tolerant to whitespace variations)
    main_target = filters.CharFilter(method='filter_main_target_tokens')

    #   Exposure time range
    exptime_min = filters.NumberFilter(
        field_name="exptime",
        lookup_expr='gte',
    )
    exptime_max = filters.NumberFilter(
        field_name="exptime",
        lookup_expr='lte',
    )


    #   Exposure time filter
    exposure_type = filters.MultipleChoiceFilter(
        field_name="exposure_type",
        choices=DataFile.EXPOSURE_TYPE_POSSIBILITIES,
        )

    #   Spectroscopy flag
    spectroscopy = filters.BooleanFilter(
        field_name="spectroscopy",
    )

    #   File name contains (match on path string)
    file_name = filters.CharFilter(
        field_name="datafile",
        lookup_expr='icontains',
    )

    #   Total pixel count range (naxis1 * naxis2)
    pixel_count_min = filters.NumberFilter(method='filter_pixel_count_min')
    pixel_count_max = filters.NumberFilter(method='filter_pixel_count_max')

    #   Tag filter
    tags = filters.ModelMultipleChoiceFilter(queryset=Tag.objects.all())

    # #   Method definitions for the filter definitions above
    # def filter_name(self, queryset, name, value):
    #     return queryset.filter(name__icontains=value)

    class Meta:
        model = DataFile
        fields = ['observation_run']

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
            return parent.order_by('observation_run')

    # Methods for pixel count filters
    def _with_pixel_count(self, queryset):
        return queryset.annotate(
            pixel_count=ExpressionWrapper(F('naxis1') * F('naxis2'), output_field=FloatField())
        )

    def filter_pixel_count_min(self, queryset, name, value):
        qs = self._with_pixel_count(queryset)
        return qs.filter(pixel_count__gte=value)

    def filter_pixel_count_max(self, queryset, name, value):
        qs = self._with_pixel_count(queryset)
        return qs.filter(pixel_count__lte=value)

    def filter_main_target_tokens(self, queryset, name, value):
        if not value:
            return queryset
        # Split by whitespace AND at alpha-numeric boundaries (e.g., "M67" -> ["M","67"]) so that
        # inputs without spaces still match names with spaces like "M 67".
        tokens = [t for t in re.split(r"\s+|(?<=\D)(?=\d)|(?<=\d)(?=\D)", str(value).strip()) if t]
        if not tokens:
            return queryset
        q = Q()
        # Build AND across tokens, each token may match main_target OR header_target_name
        for t in tokens:
            q &= (Q(main_target__icontains=t) | Q(header_target_name__icontains=t))
        return queryset.filter(q)
