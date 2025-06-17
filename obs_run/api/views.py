from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from django_filters.rest_framework import DjangoFilterBackend

from obs_run.models import ObservationRun, DataFile
from ostdata.custom_permissions import IsAllowedOnRun, get_allowed_model_to_view_for_user

from .serializers import RunSerializer, RunListSerializer, DataFileSerializer
from .filter import RunFilter, DataFileFilter

from django.utils.timezone import make_aware
from datetime import datetime, timedelta
import environ
from ..auxil import get_size_dir
from objects.models import Object


# ===============================================================
#   OBSERVATION RUNS
# ===============================================================

class RunViewSet(viewsets.ModelViewSet):
    """
        Returns a list of all observation runs in the database
    """
    permission_classes = [IsAuthenticatedOrReadOnly]
    queryset = ObservationRun.objects.all()
    serializer_class = RunSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = RunFilter

    def get_queryset(self):
        queryset = ObservationRun.objects.all()
        if self.request.user.is_anonymous:
            return queryset.filter(is_public=True)
        return queryset

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
    observation_run = ObservationRun.objects.get(pk=run_pk)
    datafiles = observation_run.datafile_set.all()

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

@api_view(['GET'])
def getDashboardStats(request):
    """
    Get statistics for the dashboard including file counts, types and object statistics
    """
    # Set time frame of 7 days
    dtime_naive = datetime.now() - timedelta(days=7)
    aware_datetime = make_aware(dtime_naive)

    # Get all files and files added within the last 7 days
    files = DataFile.objects.all()
    files_7d = DataFile.history.filter(history_date__gte=aware_datetime)

    # Get all objects and objects added within the last 7 days
    objects = Object.objects.all()
    objects_7d = Object.history.filter(history_date__gte=aware_datetime)

    # Get all observation runs and runs added within the last 7 days
    runs = ObservationRun.objects.all()
    runs_7d = ObservationRun.history.filter(history_date__gte=aware_datetime)

    # Calculate file statistics
    stats = {
        'files': {
            'total': files.count(),
            'total_last_week': files_7d.count(),
            'bias': files.filter(exposure_type='BI').count(),
            'darks': files.filter(exposure_type='DA').count(),
            'flats': files.filter(exposure_type='FL').count(),
            'lights': files.filter(exposure_type='LI').count(),
            'fits': files.filter(file_type__exact='FITS').count(),
            'jpeg': files.filter(file_type__exact='JPG').count(),
            'cr2': files.filter(file_type__exact='CR2').count(),
            'tiff': files.filter(file_type__exact='TIFF').count(),
            'ser': files.filter(file_type__exact='SER').count()
        },
        'objects': {
            'total': objects.count(),
            'total_last_week': objects_7d.count(),
            'galaxies': objects.filter(object_type='GA').count(),
            'star_clusters': objects.filter(object_type='SC').count(),
            'nebulae': objects.filter(object_type='NE').count(),
            'stars': objects.filter(object_type='ST').count(),
            'solar_system': objects.filter(object_type='SO').count(),
            'other': objects.filter(object_type='OT').count(),
            'unknown': objects.filter(object_type='UK').count()
        },
        'runs': {
            'total': runs.count(),
            'total_last_week': runs_7d.count(),
            'partly_reduced': runs.filter(reduction_status='PR').count(),
            'fully_reduced': runs.filter(reduction_status='FR').count(),
            'reduction_error': runs.filter(reduction_status='ER').count(),
            'not_reduced': runs.filter(reduction_status='NE').count()
        }
    }

    # Get storage usage
    env = environ.Env()
    environ.Env.read_env()
    data_path = env("DATA_PATH", default='/archive/ftp/')
    stats['files']['storage_size'] = get_size_dir(data_path) * pow(1000, -4)  # Convert to TB

    return Response(stats)
