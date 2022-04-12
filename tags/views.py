from django.shortcuts import render

def tag_list(request, project=None, **kwargs):
    """
        Simple view showing all defined tags, and allowing for deletion and
        creation of new ones. Tag retrieval, deletion and creation is handled
        through the API
    """

    return render(request, 'tags/tag_list.html')
