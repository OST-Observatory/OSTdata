"""
Admin-specific filters for DataFiles list (all datafiles, no run visibility restriction).
"""
import re
from django_filters import rest_framework as filters
from django.db.models import Q

from obs_run.models import DataFile
from tags.models import Tag
from utilities import annotate_effective_exposure_type


class AdminDataFileFilter(filters.FilterSet):
    """
    Filter for admin list of all DataFiles.
    No run visibility filtering - staff/admin see all.
    """
    observation_run = filters.NumberFilter(field_name='observation_run_id')
    observation_run_name = filters.CharFilter(field_name='observation_run__name', lookup_expr='icontains')
    file_name = filters.CharFilter(field_name='datafile', lookup_expr='icontains')
    file_type = filters.CharFilter(field_name='file_type', lookup_expr='icontains')
    instrument = filters.CharFilter(field_name='instrument', lookup_expr='icontains')
    telescope = filters.CharFilter(field_name='telescope', lookup_expr='icontains')
    main_target = filters.CharFilter(method='filter_main_target_tokens')
    exposure_type = filters.MultipleChoiceFilter(
        field_name='exposure_type',
        choices=DataFile.EXPOSURE_TYPE_POSSIBILITIES,
    )
    exposure_type_ml = filters.MultipleChoiceFilter(
        field_name='exposure_type_ml',
        choices=DataFile.EXPOSURE_TYPE_POSSIBILITIES,
    )
    exposure_type_user = filters.MultipleChoiceFilter(
        field_name='exposure_type_user',
        choices=DataFile.EXPOSURE_TYPE_POSSIBILITIES,
    )
    has_user_type = filters.BooleanFilter(
        method='filter_has_user_type',
        label='Has user-set exposure type',
    )
    effective_exposure_type = filters.MultipleChoiceFilter(
        method='filter_effective_exposure_type',
        label='Effective exposure type',
        choices=DataFile.EXPOSURE_TYPE_POSSIBILITIES,
    )
    spectroscopy = filters.BooleanFilter(field_name='spectroscopy')
    spectrograph = filters.ChoiceFilter(
        field_name='spectrograph',
        choices=DataFile.spectrograph_possibilities,
    )
    exptime_min = filters.NumberFilter(field_name='exptime', lookup_expr='gte')
    exptime_max = filters.NumberFilter(field_name='exptime', lookup_expr='lte')
    plate_solved = filters.BooleanFilter(field_name='plate_solved')
    has_error = filters.BooleanFilter(
        method='filter_has_plate_error',
        label='Has plate solve error',
    )
    tags = filters.ModelMultipleChoiceFilter(queryset=Tag.objects.all())

    def filter_main_target_tokens(self, queryset, name, value):
        if not value:
            return queryset
        tokens = [t for t in re.split(r"\s+|(?<=\D)(?=\d)|(?<=\d)(?=\D)", str(value).strip()) if t]
        if not tokens:
            return queryset
        q = Q()
        for t in tokens:
            q &= (Q(main_target__icontains=t) | Q(header_target_name__icontains=t))
        return queryset.filter(q)

    def filter_has_plate_error(self, queryset, name, value):
        if value is True:
            return queryset.filter(plate_solve_error__isnull=False).exclude(plate_solve_error='')
        if value is False:
            return queryset.filter(Q(plate_solve_error__isnull=True) | Q(plate_solve_error=''))
        return queryset

    def filter_has_user_type(self, queryset, name, value):
        if value is True:
            return queryset.exclude(Q(exposure_type_user__isnull=True) | Q(exposure_type_user=''))
        if value is False:
            return queryset.filter(Q(exposure_type_user__isnull=True) | Q(exposure_type_user=''))
        return queryset

    def filter_effective_exposure_type(self, queryset, name, value):
        if not value:
            return queryset
        values = [value] if isinstance(value, str) else list(value)
        values = [v for v in values if v]
        if not values:
            return queryset
        queryset = annotate_effective_exposure_type(queryset)
        return queryset.filter(annotated_effective_exposure_type__in=values)
