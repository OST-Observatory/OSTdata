from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, reverse
from django.conf import settings

import numpy as np

from bokeh.embed import components
from bokeh.resources import CDN

from .models import Obs_run

from objects.models import Object

from tags.models import Tag

from ostdata.custom_permissions import check_user_can_view_run

from .forms import UploadRunForm

from .auxil import invalid_form, populate_runs

from .plotting import (
    plot_observation_conditions,
    plot_visibility,
    plot_field_of_view,
    )

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
            .filter(pk__in=user.get_read_model(Obs_run).values('pk')) \
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
        'script_name': settings.FORCE_SCRIPT_NAME,
        }

    return render(request, 'obs_run/obs_run_list.html', context)

############################################################################

@check_user_can_view_run
def obs_run_detail(request, run_id, **kwargs):
    """
        Detailed view for an observation run
    """
    #   Get observation run
    obs_run = get_object_or_404(Obs_run, pk=run_id)

    #   Prepare reduction status
    reduction_status = obs_run.reduction_status

    #   Prepare date string
    name = obs_run.name
    date_string = name[0:4]+'-'+name[4:6]+'-'+name[6:8]

    #   Get pk and name of auxiliary objects
    aux_objects_pk_name = obs_run.object_set.filter(is_main=False).values_list(
        'pk',
        'name',
    )
    auxillary_objects = []
    for value in aux_objects_pk_name:
        auxillary_objects.append(
            (value[1], reverse('objects:object_detail', args=[value[0]]))
            )

    #   Get data associated with main objects (also from data files)
    main_objects = []
    main_objects_detail = []

    #   Get all objects
    objects_main = Object.objects.filter(is_main=True).filter(obsrun=obs_run)
    for obj in objects_main:
        #   Get Datafiles associated with these objects (restrict to current
        #   Obs_run and to science data [exposure_type='LI'])
        data_files = obj.datafiles.all() \
            .filter(obsrun=obs_run) \
            .filter(exposure_type='LI')

        #   Get instruments & telescopes + sanitize the output with set and join
        # instruments = ', '.join(set(list(data_files.values_list(
        #     'instrument',
        #     flat=True
        #     ))))
        instruments = ',\n'.join(set(list(data_files.values_list(
            'instrument',
            flat=True
            ))))
        telescopes = ',\n'.join(set(data_files.values_list(
            'telescope',
            flat=True
            )))

        #   Get exposure times, airmass and JD
        exptime_airmass_jd = data_files.values_list(
            'exptime',
            'airmass',
            'hjd',
            )
        #   Convert to numpy array to facilitate processing
        np_exptime_airmass_jd = np.array(exptime_airmass_jd, dtype=float)
        #   Get minimal and maximum airmass
        min_airmass = min(np_exptime_airmass_jd[:,1])
        max_airmass = max(np_exptime_airmass_jd[:,1])
        #   Get exposure time sum
        total_exposure_time = np.sum(np_exptime_airmass_jd[:,0])
        #   Get minimal and maximum JD
        min_jd = min(np_exptime_airmass_jd[:,2])
        # max_jd = max(np_exptime_airmass_jd[:,2])

        #   Prepare visibility plot
        visibility_plot = plot_visibility(
            min_jd,
            total_exposure_time,
            obj.ra,
            obj.dec,
            )
        vis_script, vis_figure = components(
            {'visibility':visibility_plot},
            CDN,
            )

        #   Prepare field of view plot
        fov_plot = plot_field_of_view(data_files[0].pk)
        # fov_script, fov_figure = components(
        #     {'fov':fov_plot},
        #     CDN,
        #     )

        #   Fill list with infos
        main_objects_detail.append((
            obj.pk,
            obj.name,
            obj.ra,
            obj.dec,
            instruments,
            telescopes,
            f"{total_exposure_time:.1f}",
            f"{min_airmass:.2f}",
            f"{max_airmass:.2f}",
            vis_script,
            vis_figure,
            # fov_script,
            # fov_figure,
            fov_plot,
            reverse('objects:object_detail', args=[obj.pk]),
            obj.get_object_type_display
            ))
        # main_objects.append((
        #     obj.name,
        #     reverse('objects:object_detail', args=[obj.pk]),
        #     ))


    #   Sanitize reduction status
    if reduction_status == 'PR':
        reduction_status_long = 'Partly reduced'
    elif reduction_status == 'FR':
        reduction_status_long = 'Fully reduced'
    elif reduction_status == 'ER':
        reduction_status_long = 'Reduction error'
    elif reduction_status == 'NE':
        reduction_status_long = 'New'

    #   Plot observing conditions
    conditions_plots = plot_observation_conditions(run_id)

    #   Create HTML content
    script, figures = components({'conditions_plots': conditions_plots}, CDN)

    context = {
        # 'main_objects': main_objects,
        'auxillary_objects': auxillary_objects,
        'reduction_status': reduction_status_long,
        'date_string': date_string,
        'run': obs_run,
        'tags': Tag.objects.all(),
        'script_name': settings.FORCE_SCRIPT_NAME,
        'figures': figures,
        'script': script,
        # 'objects_main': objects_main,
        'main_objects_detail': main_objects_detail,
    }

    return render(request, 'obs_run/obs_run_detail.html', context)
