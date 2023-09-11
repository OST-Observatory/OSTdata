from django.shortcuts import render, get_object_or_404
from django.conf import settings

import numpy as np

from tags.models import Tag

from .models import Object


def objects_list(request):
    """
        View showing a list of all objects
    """

    context = {
        'script_name': settings.FORCE_SCRIPT_NAME,
        }

    return render(request, 'objects/objects_list.html', context)

############################################################################


def object_detail(request, object_id, **kwargs):
    """
        Detailed view for an object
    """

    object = get_object_or_404(Object, pk=object_id)

    datafiles = object.datafiles.filter(exposure_type='LI')

    exptime = datafiles.values_list('exptime', flat=True)

    np_exptime = np.array(exptime, dtype=float)

    total_exposure_time = np.sum(np_exptime)

    obs_names = ',\n'.join(set(
        object.identifier_set.filter(info_from_header=True).values_list(
            'name',
            flat=True,
            )
        ))

    context = {
        'object': object,
        'tags': Tag.objects.all(),
        'script_name': settings.FORCE_SCRIPT_NAME,
        'total_exposure_time': f"{total_exposure_time:.1f}",
        'obs_names': obs_names,
    }

    return render(request, 'objects/objects_detail.html', context)
