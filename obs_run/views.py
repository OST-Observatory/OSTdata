from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, reverse
from django.conf import settings
from django.utils.timezone import make_aware

from datetime import datetime, timedelta

# from pathlib import Path

import environ

import numpy as np

from bokeh.embed import components
from bokeh.resources import CDN

from .models import ObservationRun, DataFile

from objects.models import Object

from tags.models import Tag

from ostdata.custom_permissions import check_user_can_view_run

from .forms import UploadRunForm

from .auxil import (
    invalid_form,
    populate_runs,
    sort_modified_created,
    wascreated,
    get_size_dir,
    )

from .plotting import (
    plot_observation_conditions,
    plot_visibility,
    plot_field_of_view,
    time_distribution_model,
    )

############################################################################


def dashboard(request):
    """
        Dashboard view
    """

    #   TODO: Add filter for time, so that only recent objects are shown

    # public_runs = ObservationRun.objects \
    #     .filter(is_public__exact=True).order_by('name')
    # private_runs = None
    #
    # if not request.user.is_anonymous:
    #     user = request.user
    #     private_runs = ObservationRun.objects \
    #         .filter(is_public__exact=False) \
    #         .filter(pk__in=user.get_read_model(ObservationRun).values('pk')) \
    #         .order_by('name')
    #
    # context = {'public_runs': public_runs,
    #            'private_runs': private_runs,
    #            }

    #   Set time frame of 7 days using datetime object
    #   -> used for filtering recent history entries
    dtime_naive = datetime.now() - timedelta(days=7)
    aware_datetime = make_aware(dtime_naive)

    #   Statistic on number of objects and observation runs
    stats = {}

    #   Get all Observation runs and runs added within the last 7 days
    obs_runs = ObservationRun.objects.all()
    obs_runs_7d = ObservationRun.history.filter(history_date__gte=aware_datetime)

    #   Get Objects and Objects added within the last 7 days
    obj = Object.objects.all()
    obj_7d = Object.history.filter(history_date__gte=aware_datetime)

    #   Get Data Files and Data Files added within the last 7 days
    files = DataFile.objects.all()
    files_7d = DataFile.history.filter(history_date__gte=aware_datetime)

    #   Add to statistic number of observation run, objects, ...
    stats['nruns'] = obs_runs.count()
    stats["nruns_PR"] = obs_runs.filter(reduction_status='PR').count()
    stats["nruns_FR"] = obs_runs.filter(reduction_status='FR').count()
    stats["nruns_ER"] = obs_runs.filter(reduction_status='ER').count()
    stats["nruns_NE"] = obs_runs.filter(reduction_status='NE').count()
    stats['nruns_lw'] = obs_runs_7d.count()

    stats['nobj'] = obj.count()
    stats['nobj_lw'] = obj_7d.count()
    stats['nobj_SC'] = obj.filter(object_type='SC').count()
    stats['nobj_SO'] = obj.filter(object_type='SO').count()
    stats['nobj_GA'] = obj.filter(object_type='GA').count()
    stats['nobj_NE'] = obj.filter(object_type='NE').count()
    stats['nobj_ST'] = obj.filter(object_type='ST').count()
    stats['nobj_OT'] = obj.filter(object_type='OT').count()
    stats['nobj_UK'] = obj.filter(object_type='UK').count()

    stats['nfiles'] = files.count()
    stats['nfiles_lw'] = files_7d.count()
    stats['nbias'] = files.filter(exposure_type='BI').count()
    stats['ndarks'] = files.filter(exposure_type='DA').count()
    stats['nflats'] = files.filter(exposure_type='FL').count()
    stats['nlights'] = files.filter(exposure_type='LI').count()
    stats['nwaves'] = files.filter(exposure_type='WA').count()
    stats['nfits'] = files.filter(file_type__exact='FITS').count()
    stats['njpeg'] = files.filter(file_type__exact='JPG').count()
    stats['ncr2'] = files.filter(file_type__exact='CR2').count()
    stats['ntiff'] = files.filter(file_type__exact='TIFF').count()
    stats['nser'] = files.filter(file_type__exact='SER').count()

    # Initialise environment variables
    #   TODO: Replace with default environment file
    env = environ.Env()
    environ.Env.read_env()
    data_path = env("DATA_PATH", default='/archive/ftp/')
    stats['file_size'] = get_size_dir(data_path) * pow(1000, -4)

    #   Recent/Last 25 changes to the observation runs and Objects
    recent_obs_runs_changes = sorted(
        obs_runs,
        key=sort_modified_created,
        reverse=True,
        )
    recent_obs_runs_changes = recent_obs_runs_changes[:25]

    recent_obj_changes = sorted(
        obj,
        key=sort_modified_created,
        reverse=True,
        )
    recent_obj_changes = recent_obj_changes[:25]

    #   Some magic to avoid problems - probably
    recent_obs_runs_changes = [{"modeltype": 'Observation run', "date": r.history.latest().history_date, "user": r.history.latest().history_user.username if r.history.latest().history_user is not None else "unknown", "instance": r, "created": wascreated(r)} for r in
                      recent_obs_runs_changes]
    recent_obj_changes = [{"modeltype": 'Object', "date": r.history.latest().history_date, "user": r.history.latest().history_user.username if r.history.latest().history_user is not None else "unknown", "instance": r, "created": wascreated(r)} for r in
                      recent_obj_changes]

    #   Prepare plots
    observation_run_time_plot = time_distribution_model(
        ObservationRun,
        'N observation runs',
        )
    objects_time_plot = time_distribution_model(
        Object,
        'N objects',
        )

    script, figures = components(
        {
            'observation_run_time_plot': observation_run_time_plot, 'objects_time_plot': objects_time_plot,
            },
        CDN,
        )

    context = {
        'stats': stats,
        'recent_obj_changes': recent_obj_changes,
        'recent_obs_runs_changes': recent_obs_runs_changes,
        'figures': figures,
        'script': script,
        }

    return render(request, 'obs_run/dashboard.html', context)

############################################################################


def obs_run_list(request):
    """
        View showing a list of all observation runs
    """

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

            #   Initialize `ObservationRun` model
            run = ObservationRun(
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
    obs_run = get_object_or_404(ObservationRun, pk=run_id)

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
    objects_main = Object.objects.filter(is_main=True).filter(observation_run=obs_run)
    for obj in objects_main:
        #   Get Datafiles associated with these objects (restrict to current
        #   ObservationRun and to science data [exposure_type='LI'])
        data_files = obj.datafiles.all() \
            .filter(observation_run=obs_run) \
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
        exptime_air_mass_jd = data_files.values_list(
            'exptime',
            'air_mass',
            'hjd',
            )
        #   Convert to numpy array to facilitate processing
        np_exptime_air_mass_jd = np.array(exptime_air_mass_jd, dtype=float)
        #   Get minimal and maximum air_mass
        min_air_mass = min(np_exptime_air_mass_jd[:,1])
        max_air_mass = max(np_exptime_air_mass_jd[:,1])
        #   Get exposure time sum
        total_exposure_time = np.sum(np_exptime_air_mass_jd[:,0])
        #   Get minimal and maximum JD
        min_jd = min(np_exptime_air_mass_jd[:,2])
        # max_jd = max(np_exptime_air_mass_jd[:,2])

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
            f"{min_air_mass:.2f}",
            f"{max_air_mass:.2f}",
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
