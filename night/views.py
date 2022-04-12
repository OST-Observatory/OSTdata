from django.shortcuts import render
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, reverse

from .models import Night

from tags.models import Tag

from ostdata.custom_permissions import check_user_can_view_night

from .forms import UploadNightForm

from .auxil import invalid_form, populate_nights

############################################################################

def dashboard(request):
    """
        Dashboard view
    """

    #   TODO: Add filter for time, so that only recent objects are shown

    public_nights = Night.objects \
        .filter(is_public__exact=True).order_by('name')
    private_nights = None

    if not request.user.is_anonymous:
        user = request.user
        private_nights = Night.objects \
            .filter(is_public__exact=False) \
            .filter(pk__in=user.get_read_nights().values('pk')) \
            .order_by('name')

    context = {'public_nights': public_nights,
               'private_nights': private_nights,
               }

    return render(request, 'night/dashboard.html', context)

############################################################################

def night_list(request):
    '''
        View showing a list of all nights
    '''

    upload_form = UploadNightForm()

    #   Handle uploads
    if request.method == 'POST' and request.user.is_authenticated:
        upload_form = UploadNightForm(
                request.POST,
                request.FILES,
            )
        if upload_form.is_valid():
            #   Sanitize uploaded data
            night_data = upload_form.cleaned_data

            #   Initialize `Night` model
            night = Night(
                name=night_data["main_id"],
                is_public=night_data["is_public"],
            )
            night.save()

            try:
                success, message = populate_nights(night_data)
                if success:
                    level = messages.SUCCESS
                else:
                    level = messages.ERROR
                    night.delete()
                messages.add_message(request, level, message)
            except Exception as e:
                print(e)
                night.delete()
                messages.add_message(
                    request,
                    messages.ERROR,
                    "Exception occurred when adding: {}".format(
                        night_data["main_id"]
                        ),
                )

            return HttpResponseRedirect(reverse('nights:night_list'))
        else:
            #   Handel invalid form
            invalid_form(request, 'nights:night_list')

    elif request.method != 'GET' and not request.user.is_authenticated:
        messages.add_message(
            request,
            messages.ERROR,
            "You need to login for that action!",
        )

    context = {
        'form_system': upload_form,
        }

    return render(request, 'night/night_list.html', context)

############################################################################

@check_user_can_view_night
def night_detail(request, night_id, **kwargs):
    """
        Detailed view for night
    """

    night   = get_object_or_404(Night, pk=night_id)
    context = {
        'night': night,
        'tags': Tag.objects.all(),
    }

    return render(request, 'night/night_detail.html', context)
    #return HttpResponse("This will be a night detail page!")
