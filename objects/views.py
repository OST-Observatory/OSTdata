from django.shortcuts import render, get_object_or_404

from tags.models import Tag

from .models import Object

def objects_list(request):
    '''
        View showing a list of all objects
    '''

    context = {}

    return render(request, 'objects/objects_list.html', context)

############################################################################

def object_detail(request, object_id, **kwargs):
    """
        Detailed view for an object
    """

    object = get_object_or_404(Object, pk=object_id)

    context = {
        'object': object,
        'tags': Tag.objects.all(),
    }

    return render(request, 'objects/objects_detail.html', context)
