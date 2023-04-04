from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from obs_run.models import Obs_run, DataFile

from .serializers import RunSerializer, RunListSerializer, DataFileSerializer

from .filter import RunFilter, DataFileFilter


# ===============================================================
#   OBSERVATION RUNS
# ===============================================================

class RunViewSet(viewsets.ModelViewSet):
    """
        Returns a list of all stars/objects in the database
    """

    queryset = Obs_run.objects.all()
    serializer_class = RunSerializer

    filter_backends = (DjangoFilterBackend,)
    filterset_class = RunFilter

    def get_serializer_class(self):
        if self.action == 'list':
            return RunListSerializer
        if self.action == 'retrieve':
            return RunSerializer
        return RunSerializer



@api_view(['GET'])
def getRunDataFile(request, run_pk):
    '''
        Get all DataFile object associated with a observation run
    '''

    #   Get Observation run and DataFiles
    obsrun = Obs_run.objects.get(pk=run_pk)
    datafiles = obsrun.datafile_set.all()

    pagination_class = None

    #   Arrange DataFile infos
    return_dict = {}
    for datafile in datafiles:
        return_dict[datafile.pk] = "{} - {}".format(
            datafile.file_type,
            datafile.exposure_type,
        )
    return Response(return_dict)

# ===============================================================
#   DATA FILE
# ===============================================================

class DataFileViewSet(viewsets.ModelViewSet):
    """
        Returns a list of all stars/objects in the database
    """

    queryset = DataFile.objects.all()
    serializer_class = DataFileSerializer

    filter_backends = (DjangoFilterBackend,)
    filterset_class = DataFileFilter
