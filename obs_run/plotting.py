import numpy as np

import datetime

from astroplan import Observer

from astropy import wcs
from astropy.time import Time
import astropy.units as u
from astropy.table import Table
from astropy.timeseries import TimeSeries, aggregate_downsample
from astropy.coordinates import SkyCoord, AltAz, get_moon, EarthLocation

from skyfield.data import hipparcos
from skyfield.api import load

from bokeh import models as mpl
from bokeh import plotting as bpl
from bokeh.models import TabPanel, Tabs, ColumnDataSource, VBar

import matplotlib.pyplot as plt

import io

import base64

from .models import Obs_run, DataFile

from objects.models import Object

############################################################################

def plot_observation_conditions(obs_run_pk):
    '''
        Plot observing conditions

        Parameters
        ----------
        obs_run_pk          : `integer`
            ID of the observation run


        Returns
        -------
        tabs
            Tabs for the plot
    '''
    #   Get observation run
    obs_run = Obs_run.objects.get(pk=obs_run_pk)

    #   Get observing conditions
    observing_conditions = obs_run.datafile_set.all().filter(hjd__gt = -1) \
        .order_by('hjd').values_list(
            'hjd',
            'ambient_temperature',
            'dewpoint',
            'pressure',
            'humidity',
            'wind_speed',
            'wind_direction',
        )
    n_data_points = len(observing_conditions[0])
    conditions_array = np.array(observing_conditions)

    #   Prepare Y axis lable
    y_axis_lable = [
        '',
        'Ambient temperature',
        'Dewpoint',
        'Pressure',
        'Humidity',
        'Wind speed',
        'Wind direction',
        ]
    y_axis_lable_units = [
        '',
        u'[\N{DEGREE SIGN} C]',
        u'[\N{DEGREE SIGN} C]',
        '[hPa]',
        '[%]',
        '[m/s]',
        u'[\N{DEGREE SIGN}]',
        ]

    #   Convert JD to datetime object
    timezone_hour_delta = 1
    x_data = conditions_array[:,0]
    delta = datetime.timedelta(hours=timezone_hour_delta)
    x_data = Time(x_data, format='jd').datetime + delta

    #   Prepare list for tabs in the figure
    tabs = []

    for i in range(1,n_data_points):
        #   Initialize figure
        fig = bpl.figure(
            width=520,
            height=240,
            toolbar_location=None,
            x_axis_type="datetime",
            )

        #   Apply JD to datetime conversion
        fig.xaxis.formatter = mpl.DatetimeTickFormatter()
        fig.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()

        #   Plot observation data
        fig.line(
          x_data,
          conditions_array[:,i],
          line_width=1,
          color="blue",
          )

        #   Set figure labels
        fig.toolbar.logo = None
        fig.yaxis.axis_label = f'{y_axis_lable[i]} {y_axis_lable_units[i]}'
        fig.xaxis.axis_label = 'Time'
        fig.yaxis.axis_label_text_font_size = '10pt'
        fig.xaxis.axis_label_text_font_size = '10pt'
        fig.min_border = 5

        #   Fill tabs list
        tabs.append(TabPanel(child=fig, title=y_axis_lable[i]))

    #   Make figure from tabs list
    return Tabs(tabs=tabs)

############################################################################

def plot_visibility(start_hjd, exposure_time, ra, dec):
    """
        Plot moon distance and hight above the horizon on the night
        or day of the observation

        Parameters
        ----------
        start_hjd       : `float`
            JD of the start of the observation

        exposure_time   : `float`
            Exposure time of the observation in seconds

        ra              : `float`
            Right ascension of the object in deg

        dec             : `float`
            Declination of the object in deg
    """
    #   Prepare figure
    fig = bpl.figure(
      width=400,
      height=240,
      toolbar_location=None,
      y_range=(0, 90),
      x_axis_type="datetime",
      )

    fig.toolbar.logo = None
    fig.title.align = 'center'
    fig.yaxis.axis_label = 'Altitude (dgr)'
    fig.xaxis.axis_label = 'UT'
    fig.yaxis.axis_label_text_font_size = '10pt'
    fig.xaxis.axis_label_text_font_size = '10pt'
    fig.min_border = 5

    try:
        #   Set OST location
        ost_location = EarthLocation(
            lat=52.409184,
            lon=12.973185,
            height=39.,
            )

        #   Define the location by means of astroplan
        ost = Observer(
          location=ost_location,
          name="OST",
          timezone="Europe/Berlin"
          )

        # time = Time(start_hjd + (end_hjd - start_hjd)/2., format='jd')
        time = Time(start_hjd + exposure_time / 2. / 86400., format='jd')

        #   Sunset
        sunset = ost.sun_set_time(time, which='nearest')

        #   Sunrise
        sunrise = ost.sun_rise_time(time, which='nearest')

        #   Sanitize sunset and sunrise for night observations
        #   TODO: Account for solar observations
        if time > sunset and time > sunrise:
            sunrise = ost.sun_rise_time(time, which='next')
        elif time < sunset and time < sunrise:
            sunset = ost.sun_set_time(time, which='previous')

        times = np.linspace(sunset.jd, sunrise.jd, 100)
        times = Time(times, format='jd')

        obj = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, )

        frame_obj = AltAz(obstime=times, location=ost_location)

        obj_altaz = obj.transform_to(frame_obj)

        moon = get_moon(times)
        moon_altaz = moon.transform_to(frame_obj)

        times = times.to_datetime()

        fig.line(
          times,
          obj_altaz.alt,
          color='blue',
          line_width=2,
          legend_label='Object',
          )
        fig.line(
          times,
          moon_altaz.alt,
          color='orange',
          line_dash='dashed',
          line_width=2,
          legend_label='Moon',
          )

        #   Convert JD to datetime object
        # timezone_hour_delta = 1
        # delta = datetime.timedelta(hours=timezone_hour_delta)
        # x_data = Time(x_data, format='jd').datetime + delta

        obsstart = Time(start_hjd, format='jd').datetime
        # obsend = Time(end_hjd, format='jd').datetime
        obsend = Time(start_hjd + exposure_time / 86400., format='jd').datetime
        obs = mpl.BoxAnnotation(
          left=obsstart,
          right=obsend,
          fill_alpha=0.5,
          fill_color='red',
          )
        fig.add_layout(obs)

    except Exception as e:

        print(e)

        label = mpl.Label(
          x=75,
          y=40,
          x_units='screen',
          text='Could not calculate visibility',
          render_mode='css',
          border_line_color='red',
          border_line_alpha=1.0,
          text_color='red',
          background_fill_color='white',
          background_fill_alpha=1.0,
          )

        fig.add_layout(label)

    return fig

############################################################################

def plot_field_of_view(data_file_pk):
    """
        Plot star positions and show field of view

        Parameters
        ----------
        data_file_pk    : `integer`
            ID of the DataFile object, representing the observation
    """
    #   Get DataFile
    datafile = DataFile.objects.get(pk=data_file_pk)
    NAXIS1 = datafile.naxis1
    NAXIS2 = datafile.naxis2

    #   Generate WCS
    w = wcs.WCS(header={
        # Width of the output fits/image
        'NAXIS1': NAXIS1,
        # Height of the output fits/image
        'NAXIS2': NAXIS2,
        # Number of coordinate axes
        'WCSAXES': 2,
        # Pixel coordinate of reference point
        'CRPIX1': int(datafile.naxis1 / 2),
        # Pixel coordinate of reference point
        'CRPIX2': int(datafile.naxis2 / 2),
        # [deg] Coordinate increment at reference point
        'CDELT1': datafile.fov_x / datafile.naxis1,
        # [deg] Coordinate increment at reference point
        'CDELT2': datafile.fov_y / datafile.naxis2,
        # Units of coordinate increment and value
        'CUNIT1': 'deg',
        # Units of coordinate increment and value
        'CUNIT2': 'deg',
        'CTYPE1': 'RA---SIN',
        'CTYPE2': 'DEC--SIN',
        # [deg] Coordinate value at reference point
        'CRVAL1': datafile.ra,
        # [deg] Coordinate value at reference point
        'CRVAL2': datafile.dec,
    })


    #   Draw star positions
    with load.open(hipparcos.URL) as f:
        stars = hipparcos.load_dataframe(f)

    stars = Table.from_pandas(stars)

    stars_loc_x, stars_loc_y = w.world_to_pixel(SkyCoord(
      ra=stars["ra_degrees"] * u.deg,
      dec=stars["dec_degrees"] * u.deg
      ))

    #   Limiting stellar magnitude
    THRES_MAG = 18.5

    #   Restrict stars to field of view and magnitude threshold
    mask = (stars_loc_x > -NAXIS1) & (stars_loc_x < NAXIS1) & \
           (stars_loc_y > -NAXIS2) & (stars_loc_y < NAXIS2) & \
           (stars["magnitude"] < THRES_MAG)
    stars = stars[mask]

    mag_min = stars["magnitude"].min()
    mag_max = stars["magnitude"].max()

    STAR_MINSIZE = 1
    STAR_MAXSIZE = 160

    def mag2size(mag):
        stars_sizes  = (np.exp(-mag) - np.exp(-mag_max)) * (STAR_MAXSIZE - STAR_MINSIZE) / np.exp(-mag_min) + STAR_MINSIZE
        return stars_sizes

    def size2mag(size):
        # need to define the inverse function of mag2size
        mag = -np.log((size - STAR_MINSIZE) * np.exp(-mag_min) / (STAR_MAXSIZE - STAR_MINSIZE) + np.exp(-mag_max))
        return mag

    # fig = plt.figure(figsize=(6.5,3.5))
    # fig = plt.figure(figsize=(5,2.7))
    fig = plt.figure(figsize=(5,2.8))
    ax = fig.add_subplot(projection=w)

    scatter = ax.scatter(
        stars_loc_x[mask],
        stars_loc_y[mask],
        s=mag2size(stars["magnitude"]),
        color="k",
        )

    box = ax.get_position()
    ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])

    # find the legend item magnitudes
    labels = np.arange(np.ceil(mag_min), np.floor(mag_max))

    kw = dict(
        prop="sizes",
        num=labels,
        color="k",
        fmt="{x:.0f}",
        func=size2mag,
        )
    legend = ax.legend(
        *scatter.legend_elements(**kw),
        loc='center left',
        bbox_to_anchor=(1.2, 0.5),
        title="Magnitude",
        fontsize=7,
        title_fontsize=7,
        )


    ax.grid(True, color="k", linestyle="dashed")

    ax.set_xlim(-NAXIS1, NAXIS1)
    ax.set_ylim(-NAXIS2, NAXIS2)

    ax.tick_params(
        axis='x',
        labelbottom=True,
        labeltop=True,
        bottom=True,
        top=True,
        labelsize=7,
        )
    ax.tick_params(
        axis='y',
        labelleft=True,
        labelright=True,
        left=True,
        right=True,
        # fontsize=0.5,
        labelsize=7,
        )

    # plt.xticks(fontsize = 1)

    ax.set_xlabel(
        "RA (J2000)",
        fontsize=7,
        )
    ax.set_ylabel(
        "Dec (J2000)",
        fontsize=7,
        )

    ax.set_aspect("equal")
    # ax.axvspan(*ax.get_xlim(), zorder=-100, color="white") # generate a white background for the plot
    ax.invert_xaxis()

    flike = io.BytesIO()
    fig.savefig(flike)
    b64 = base64.b64encode(flike.getvalue()).decode()
    return b64

    # #   Prepare figure
    # fig = bpl.figure(
    #   width=400,
    #   height=240,
    #   toolbar_location=None,
    #   # y_range=(0, 90),
    #   # x_axis_type="datetime",
    #   )
    #
    #
    # fig.toolbar.logo = None
    # fig.title.align = 'center'
    # fig.yaxis.axis_label = 'DEC (dgr)'
    # fig.xaxis.axis_label = 'RA (dgr)'
    # fig.yaxis.axis_label_text_font_size = '10pt'
    # fig.xaxis.axis_label_text_font_size = '10pt'
    # fig.min_border = 5
    #
    #
    # fig.scatter(
    #     x=stars_loc_x[mask],
    #     y=stars_loc_y[mask],
    #     marker="circle",
    #     color='black',
    #     radius=mag2size(stars["magnitude"]),
    #     # fill_alpha=0.3,
    #     # line_alpha=1.0,
    #     # size=4,
    #     # # size=mag2size(stars["magnitude"]),
    #     # line_width=1.,
    #     )
    # # fig.circle(
    # #     stars_loc_x[mask],
    # #     stars_loc_y[mask],
    # #     color='powderblue',
    # #     fill_alpha=0.3,
    # #     line_alpha=1.0,
    # #     size=4,
    # #     # size=mag2size(stars["magnitude"]),
    # #     line_width=1.,
    # #     )
    #
    # return fig

############################################################################

def time_distribution_model(model, yaxis_lable):
    '''
        Plots the time distribution of the 'model' (yearly binned)
        Two Plots - First: bar plot; Second: cumulative plot

        Parameters
        ----------
        model           : `django.db.models.Model` object
            Model to be graphically represented

        yaxis_lable     : `string`
            Lable for the Y axis


        Returns
        -------
        tabs
            Tabs for the plot
    '''
    #   Get JDs of all model objects - clean results of not usable JDs
    if model == Object:
        term_hjd = 'first_hjd'
    elif model == Obs_run:
        term_hjd = 'mid_observation_jd'
    else:
        term_hjd = 'hjd'
    jds = np.array(model.objects.all().values_list(
            term_hjd,
            flat=True
            )
        )
    mask = np.where(jds)
    jds = np.sort(jds[mask])

    #   Get number of valid model objects - with valid JDs
    n_valid = len(jds)

    #   Create a Time object for the observation times
    obs_time = Time(jds, format='jd')

    #   Make time series and use reshape to get a justified array
    ts = TimeSeries(
        time=obs_time,
        data={'nobs': np.ones((n_valid))}
        )

    #   Binned time series using numpy sum function
    ts_sum = aggregate_downsample(
        ts,
        time_bin_size = 1 * u.yr,
        aggregate_func=np.sum,
        ).filled(0.)

    #   Convert JD to datetime object
    timezone_hour_delta = 1
    x_data = ts_sum['time_bin_start'].value
    delta = datetime.timedelta(hours=timezone_hour_delta)
    x_data = Time(x_data, format='jd').datetime + delta

    #   Prepare list for tabs in the figure
    tabs = []


    ###
    #   Bar plot
    #
    source = ColumnDataSource(dict(x=x_data,top=ts_sum['nobs'].value,))

    glyph = VBar(
        x="x",
        top="top",
        bottom=0,
        width=20000000000,
        fill_color="#fcab40",
        )

    #   Initialize figure
    fig = bpl.figure(
        # sizing_mode="inherit",
        # sizing_mode="scale_both",
        sizing_mode="scale_width",
        # width_policy='fit',
        # width_policy='max',
        aspect_ratio=3.,
        # width=600,
        # height=200,
        toolbar_location=None,
        x_axis_type="datetime",
        )

    fig.add_glyph(source, glyph)

    #   Apply JD to datetime conversion
    fig.xaxis.formatter = mpl.DatetimeTickFormatter()
    fig.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()

    #   Set figure labels
    fig.toolbar.logo = None
    fig.yaxis.axis_label = yaxis_lable
    fig.xaxis.axis_label = 'Time'
    fig.yaxis.axis_label_text_font_size = '10pt'
    fig.xaxis.axis_label_text_font_size = '10pt'
    fig.min_border = 5

    #   Add bar plot to tab list
    tabs.append(TabPanel(child=fig, title='Bar plot'))


    ###
    #   Cumulative plot
    #

    #   Initialize figure
    fig = bpl.figure(
        # sizing_mode="inherit",
        # sizing_mode="scale_both",
        sizing_mode="scale_width",
        # width_policy='fit',
        # width_policy='max',
        aspect_ratio=3.,
        # width=600,
        # height=200,
        toolbar_location=None,
        x_axis_type="datetime",
        )

    #   Apply JD to datetime conversion
    fig.xaxis.formatter = mpl.DatetimeTickFormatter()
    fig.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()

    #   Plot cumulative number
    fig.line(
        x_data,
        np.cumsum(ts_sum['nobs']),
        line_width=2,
        color="#fcab40",
        )

    #   Set figure labels
    fig.toolbar.logo = None
    fig.yaxis.axis_label = yaxis_lable
    fig.xaxis.axis_label = 'Time'
    fig.yaxis.axis_label_text_font_size = '10pt'
    fig.xaxis.axis_label_text_font_size = '10pt'
    fig.min_border = 5

    #   Add cumulative plot to tab list
    tabs.append(TabPanel(child=fig, title='Cumulative plot'))


    #   Make figure from tabs list
    return Tabs(tabs=tabs, sizing_mode="scale_width", aspect_ratio=3.)
