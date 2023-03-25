from django.shortcuts import render
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, reverse

from .models import Obs_run

from tags.models import Tag

from ostdata.custom_permissions import check_user_can_view_run

from .forms import UploadRunForm

from .auxil import invalid_form, populate_runs

############################################################################

def dashboard(request):
    """
        Dashboard view
    """

    #   TODO: Add filter for time, so that only recent objects are shown

    public_runs = Obs_run.objects \
        .filter(is_public__exact=True).order_by('name')
    private_runs = None

    if not request.user.is_anonymous:
        user = request.user
        private_runs = Obs_run.objects \
            .filter(is_public__exact=False) \
            .filter(pk__in=user.get_read_runs().values('pk')) \
            .order_by('name')

    context = {'public_runs': public_runs,
               'private_runs': private_runs,
               }

    return render(request, 'obs_run/dashboard.html', context)

############################################################################

def obs_run_list(request):
    '''
        View showing a list of all observation runs
    '''

    upload_form = UploadRunForm()

    #   Handle uploads
    if request.method == 'POST' and request.user.is_authenticated:
        upload_form = UploadRunForm(
                request.POST,
                request.FILES,
            )
        if upload_form.is_valid():
            #   Sanitize uploaded data
            run_data = upload_form.cleaned_data

            #   Initialize `Obs_run` model
            run = Obs_run(
                name=run_data["main_id"],
                is_public=run_data["is_public"],
            )
            run.save()

            try:
                success, message = populate_runs(run_data)
                if success:
                    level = messages.SUCCESS
                else:
                    level = messages.ERROR
                    run.delete()
                messages.add_message(request, level, message)
            except Exception as e:
                print(e)
                run.delete()
                messages.add_message(
                    request,
                    messages.ERROR,
                    "Exception occurred when adding: {}".format(
                        run_data["main_id"]
                        ),
                )

            return HttpResponseRedirect(reverse('runs:run_list'))
        else:
            #   Handel invalid form
            invalid_form(request, 'runs:run_list')

    elif request.method != 'GET' and not request.user.is_authenticated:
        messages.add_message(
            request,
            messages.ERROR,
            "You need to login for that action!",
        )

    context = {
        'form_system': upload_form,
        }

    return render(request, 'obs_run/obs_run_list.html', context)

############################################################################

@check_user_can_view_run
def obs_run_detail(request, run_id, **kwargs):
    """
        Detailed view for observation run
    """

    run   = get_object_or_404(Obs_run, pk=run_id)
    context = {
        'run': run,
        'tags': Tag.objects.all(),
    }

    return render(request, 'obs_run/obs_run_detail.html', context)
    #return HttpResponse("This will be a night detail page!")
