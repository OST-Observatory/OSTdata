
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters

from rest_framework import viewsets

from .serializers import NightSerializer, NightListSerializer

from night.models import Night
from tags.models import Tag

from ostdata.custom_permissions import get_allowed_nights_to_view_for_user


# ===============================================================
# NIGHTS
# ===============================================================

class NightFilter(filters.FilterSet):
    '''
        Filter definitions for table with nights
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
        choices=Night.REDUCTION_STATUS_CHOICES,
        )

    #   Tag filter
    tags = filters.ModelMultipleChoiceFilter(queryset=Tag.objects.all())

    #   Method definitions for the filter definitions above
    def filter_name(self, queryset, name, value):
        return queryset.filter(name__icontains=value)

    class Meta:
        model = Night
        fields = ['name']

    @property
    def qs(self):
        parent = super().qs

        parent = get_allowed_nights_to_view_for_user(parent, self.request.user)

        #   Get the column order from the GET dictionary
        getter = self.request.query_params.get
        if not getter('order[0][column]') is None:
            order_column = int(getter('order[0][column]'))
            order_name = getter('columns[%i][data]' % order_column)
            if getter('order[0][dir]') == 'desc': order_name = '-'+order_name

            return parent.order_by(order_name)
        else:
            return parent


class NightViewSet(viewsets.ModelViewSet):
    """
        Returns a list of all stars/objects in the database
    """

    queryset = Night.objects.all()
    serializer_class = NightSerializer

    filter_backends = (DjangoFilterBackend,)
    filterset_class = NightFilter

    def get_serializer_class(self):
        if self.action == 'list':
            return NightListSerializer
        if self.action == 'retrieve':
            return NightSerializer
        return NightSerializer


