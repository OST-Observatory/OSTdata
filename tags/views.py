from django.shortcuts import render
from django.conf import settings

def tag_list(request, project=None, **kwargs):
    """
        Simple view showing all defined tags, and allowing for deletion and
        creation of new ones. Tag retrieval, deletion and creation is handled
        through the API
    """

    context = {
        'script_name': settings.FORCE_SCRIPT_NAME,
        }

    return render(request, 'tags/tag_list.html', context)
