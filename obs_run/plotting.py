import numpy as np

import datetime
import os
from zoneinfo import ZoneInfo
from pathlib import Path

from astroplan import Observer

from astropy import wcs
from astropy.time import Time
import astropy.units as u
from astropy.table import Table
from astropy.timeseries import TimeSeries, aggregate_downsample
from astropy.coordinates import SkyCoord, AltAz, get_body, EarthLocation

from skyfield.data import hipparcos
from skyfield.api import load

from bokeh import models as mpl
from bokeh import plotting as bpl
from bokeh.models import TabPanel, Tabs, ColumnDataSource, VBar

import matplotlib.pyplot as plt

import io

import base64

from .models import ObservationRun, DataFile
try:
    from django.conf import settings as django_settings
except Exception:
    django_settings = None

from objects.models import Object


############################################################################
def _get_plot_timezone():
    """
    Resolve desired timezone for plots.
    Priority: env PLOT_TIME_ZONE -> settings.PLOT_TIME_ZONE -> settings.TIME_ZONE -> 'UTC'
    Returns (tz_obj, tz_name_str, is_utc)
    """
    tz_name = os.environ.get('PLOT_TIME_ZONE')
    if not tz_name and django_settings is not None:
        tz_name = getattr(django_settings, 'PLOT_TIME_ZONE', None) or getattr(django_settings, 'TIME_ZONE', None)
    if not tz_name:
        tz_name = 'UTC'
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = datetime.timezone.utc
        tz_name = 'UTC'
    return tz, tz_name, (tz_name.upper() == 'UTC')



def plot_observation_conditions(obs_run_pk):
    """
        Plot observing conditions

        Parameters
        ----------
        obs_run_pk          : `integer`
            ID of the observation run


        Returns
        -------
        tabs
            Tabs for the plot
    """
    #   Get observation run
    obs_run = ObservationRun.objects.get(pk=obs_run_pk)

    #   Get observing conditions
    observing_conditions = obs_run.datafile_set.all().filter(hjd__gt=-1) \
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

    #   Prepare Y axis label
    y_axis_label = [
        '',
        'Ambient temperature',
        'Dewpoint',
        'Pressure',
        'Humidity',
        'Wind speed',
        'Wind direction',
    ]
    y_axis_label_units = [
        '',
        u'[\N{DEGREE SIGN} C]',
        u'[\N{DEGREE SIGN} C]',
        '[hPa]',
        '[%]',
        '[m/s]',
        u'[\N{DEGREE SIGN}]',
    ]

    #   Convert JD to datetime object
    # Use configured timezone for time axis
    tz, tz_name, is_utc = _get_plot_timezone()
    x_data = conditions_array[:, 0]
    x_data = Time(x_data, format='jd').to_datetime(timezone=tz)

    #   Prepare list for tabs in the figure
    tabs = []

    for i in range(1, n_data_points):
        #   Initialize figure
        fig = bpl.figure(
            height=260,
            toolbar_location=None,
            x_axis_type="datetime",
            sizing_mode="stretch_width",
        )

        #   Apply JD to datetime conversion and enforce display timezone via JS formatter
        tz, tz_name, is_utc = _get_plot_timezone()
        fig.xaxis.formatter = mpl.DatetimeTickFormatter(
            minutes="%y-%m-%d %H:%M",
            hours="%y-%m-%d %H:%M",
            days="%y-%m-%d",
            months="%y-%m",
            years="%Y",
        )

        #   Axes on all four sides (top/right mirror bottom/left)
        try:
            top_axis = mpl.DatetimeAxis(ticker=fig.xaxis[0].ticker, formatter=fig.xaxis[0].formatter)
            top_axis.axis_label = ''
            top_axis.axis_label_text_font_size = '0pt'
            top_axis.major_label_text_font_size = '0pt'  # hide tick labels
            fig.add_layout(top_axis, 'above')
        except Exception:
            pass
        try:
            right_axis = mpl.LinearAxis(ticker=fig.yaxis[0].ticker)
            right_axis.axis_label = ''
            right_axis.axis_label_text_font_size = '0pt'
            right_axis.major_label_text_font_size = '0pt'  # hide tick labels
            fig.add_layout(right_axis, 'right')
        except Exception:
            pass

        #   Plot observation data
        fig.line(
            x_data,
            conditions_array[:, i],
            line_width=1,
            color="blue",
        )

        #   Set figure labels
        fig.toolbar.logo = None
        fig.yaxis.axis_label = f'{y_axis_label[i]} {y_axis_label_units[i]}'
        fig.xaxis.axis_label = 'UTC' if is_utc else 'Local Time'
        fig.yaxis.axis_label_text_font_size = '10pt'
        fig.xaxis.axis_label_text_font_size = '10pt'
        fig.min_border = 5

        #   Fill tabs list
        tabs.append(TabPanel(child=fig, title=y_axis_label[i]))

    #   Make figure from tabs list
    tabs_widget = Tabs(tabs=tabs)
    tabs_widget.sizing_mode = "stretch_width"
    return tabs_widget


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
        height=240,
        toolbar_location=None,
        y_range=(0, 90),
        x_axis_type="datetime",
        sizing_mode="stretch_width",
    )

    fig.toolbar.logo = None
    fig.title.align = 'center'
    fig.yaxis.axis_label = 'Altitude (dgr)'
    fig.xaxis.axis_label = 'UT'
    fig.yaxis.axis_label_text_font_size = '10pt'
    fig.xaxis.axis_label_text_font_size = '10pt'
    fig.min_border = 5

    #   Axes on all four sides (top/right mirror bottom/left)
    try:
        top_axis = mpl.DatetimeAxis(ticker=fig.xaxis[0].ticker, formatter=fig.xaxis[0].formatter)
        top_axis.axis_label = ''
        top_axis.axis_label_text_font_size = '0pt'
        top_axis.major_label_text_font_size = '0pt'  # hide tick labels
        fig.add_layout(top_axis, 'above')
    except Exception:
        pass
    try:
        right_axis = mpl.LinearAxis(ticker=fig.yaxis[0].ticker)
        right_axis.axis_label = ''
        right_axis.axis_label_text_font_size = '0pt'
        right_axis.major_label_text_font_size = '0pt'  # hide tick labels
        fig.add_layout(right_axis, 'right')
    except Exception:
        pass

    try:
        #   Set OST location
        ost_location = EarthLocation(
            lat=52.409184,
            lon=12.973185,
            height=39.,
        )

        #   Define the location by means of astroplan
        tz, tz_name, is_utc = _get_plot_timezone()
        ost = Observer(
            location=ost_location,
            name="OST",
            timezone=tz_name,
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

        moon = get_body('moon', times)
        moon_altaz = moon.transform_to(frame_obj)

        times = times.to_datetime(timezone=tz)

        #   Enforce browser locale on x-axis via formatter
        fig.xaxis.formatter = mpl.DatetimeTickFormatter(
            minutes="%y-%m-%d %H:%M",
            hours="%y-%m-%d %H:%M",
            days="%y-%m-%d",
            months="%y-%m",
            years="%Y",
        )

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

        obsstart = Time(start_hjd, format='jd').to_datetime(timezone=tz)
        obsend = Time(start_hjd + exposure_time / 86400., format='jd').to_datetime(timezone=tz)
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
    magnitude_threshold = 18.5

    #   Restrict stars to field of view and magnitude threshold
    mask = (stars_loc_x > -NAXIS1) & (stars_loc_x < NAXIS1) & \
           (stars_loc_y > -NAXIS2) & (stars_loc_y < NAXIS2) & \
           (stars["magnitude"] < magnitude_threshold)
    stars = stars[mask]

    mag_min = stars["magnitude"].min()
    mag_max = stars["magnitude"].max()

    star_size_min = 1
    star_size_max = 160

    def mag2size(mag):
        stars_sizes = ((np.exp(-mag) - np.exp(-mag_max)) *
                       (star_size_max - star_size_min) / np.exp(-mag_min) +
                       star_size_min)
        return stars_sizes

    def size2mag(size):
        # need to define the inverse function of mag2size
        mag = -np.log(
            (size - star_size_min) * np.exp(-mag_min) /
            (star_size_max - star_size_min) +
            np.exp(-mag_max)
        )
        return mag

    # fig = plt.figure(figsize=(6.5,3.5))
    # fig = plt.figure(figsize=(5,2.7))
    fig = plt.figure(figsize=(5, 2.8))
    ax = fig.add_subplot(projection=w)

    scatter = ax.scatter(
        stars_loc_x[mask],
        stars_loc_y[mask],
        s=mag2size(stars["magnitude"]),
        color="k",
    )

    box = ax.get_position()
    ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])

    #   Find the legend item magnitudes
    #   TODO: Check these "labels". They do not work anymore.
    labels = np.arange(np.ceil(mag_min), np.floor(mag_max))
    # print(mag_min, mag_max)
    # print(labels)

    kw = dict(
        prop="sizes",
        # num=labels,
        num='auto',
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


def time_distribution_model(model, yaxis_label, months=None):
    """
        Plots the time distribution of the 'model' (yearly binned)
        Two Plots - First: bar plot; Second: cumulative plot

        Parameters
        ----------
        model           : `django.db.models.Model` object
            Model to be graphically represented

        yaxis_label     : `string`
            Label for the Y axis


        Returns
        -------
        tabs
            Tabs for the plot
    """
    #   Get JDs of all model objects - clean results of not usable JDs
    if model == Object:
        term_hjd = 'first_hjd'
    elif model == ObservationRun:
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

    #   Make time series
    ts = TimeSeries(
        time=obs_time,
        data={'nobs': np.ones(n_valid)}
    )

    #   Binned time series using numpy sum function
    ts_sum = aggregate_downsample(
        ts,
        time_bin_size=1 * u.yr,
        aggregate_func=np.sum,
    ).filled(0.)

    #   Choose bin size based on requested window (months)
    #   Monthly bins for limited windows, yearly bins for full history
    bin_size = 1 * u.yr
    if months is not None:
        try:
            m_int = int(months)
            if m_int > 0:
                bin_size = 1 * u.month
        except Exception:
            pass

    ts_sum = aggregate_downsample(
        ts,
        time_bin_size=bin_size,
        aggregate_func=np.sum,
    ).filled(0.)

    #   Convert JD to timezone-aware datetime for plotting
    tz, tz_name, is_utc = _get_plot_timezone()
    x_vals = ts_sum['time_bin_start'].value
    x_data = Time(x_vals, format='jd').to_datetime(timezone=tz)

    #   Optional: filter by months window
    if months is not None:
        now_dt = datetime.datetime.now(tz)
        approx_days = float(months) * 30.44
        cutoff = now_dt - datetime.timedelta(days=approx_days)
        mask = np.array([xd >= cutoff for xd in x_data])
        # ensure arrays
        x_data = np.array(x_data)[mask]
        y_vals = np.array(ts_sum['nobs'].value)[mask]
    else:
        y_vals = ts_sum['nobs'].value

    #   Prepare list for tabs in the figure
    tabs = []

    ###
    #   Bar plot
    #
    source = ColumnDataSource(dict(x=x_data, top=y_vals, ))

    glyph = VBar(
        x="x",
        top="top",
        bottom=0,
        width=20000000000,
        fill_color="#fcab40",
    )

    #   Initialize figure
    fig = bpl.figure(
        sizing_mode="stretch_width",
        aspect_ratio=3.,
        toolbar_location=None,
        x_axis_type="datetime",
    )

    fig.add_glyph(source, glyph)

    #   Apply JD to datetime conversion
    fig.xaxis.formatter = mpl.DatetimeTickFormatter(
        days="%y-%m-%d",
        months="%y-%m",
        years="%Y",
    )

    #   Set figure labels
    fig.toolbar.logo = None
    fig.yaxis.axis_label = yaxis_label
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
        sizing_mode="stretch_width",
        aspect_ratio=3.,
        toolbar_location=None,
        x_axis_type="datetime",
    )

    #   Apply JD to datetime conversion
    fig.xaxis.formatter = mpl.DatetimeTickFormatter(
        days="%y-%m-%d",
        months="%y-%m",
        years="%Y",
    )

    #   Plot cumulative number
    fig.line(
        x_data,
        np.cumsum(y_vals),
        line_width=2,
        color="#fcab40",
    )

    #   Set figure labels
    fig.toolbar.logo = None
    fig.yaxis.axis_label = yaxis_label
    fig.xaxis.axis_label = 'Time'
    fig.yaxis.axis_label_text_font_size = '10pt'
    fig.xaxis.axis_label_text_font_size = '10pt'
    fig.min_border = 5

    #   Add cumulative plot to tab list
    tabs.append(TabPanel(child=fig, title='Cumulative plot'))

    #   Make figure from tabs list
    return Tabs(tabs=tabs, sizing_mode="stretch_width", aspect_ratio=3.)


############################################################################


def plot_sky_fov(ra_center_deg, dec_center_deg, fov_x_deg, fov_y_deg, scale=8.0, rotation_deg=0.0):
    """
    Bokeh plot of stars in a sky region around (ra, dec) with camera FOV overlay.

    Parameters
    ----------
    ra_center_deg : float
        Center RA in degrees
    dec_center_deg : float
        Center Dec in degrees
    fov_x_deg : float
        Camera field-of-view width (deg)
    fov_y_deg : float
        Camera field-of-view height (deg)
    scale : float
        Multiplier for display window relative to camera FOV (e.g., 8)
    rotation_deg : float
        Optional rotation of camera FOV rectangle in degrees
    """
    # Display window size
    half_w = 0.5 * max(0.01, float(fov_x_deg)) * float(scale)
    half_h = 0.5 * max(0.01, float(fov_y_deg)) * float(scale)

    ra_min = ra_center_deg - half_w
    ra_max = ra_center_deg + half_w
    dec_min = dec_center_deg - half_h
    dec_max = dec_center_deg + half_h

    # Load Hipparcos stars
    with load.open(hipparcos.URL) as f:
        stars_df = hipparcos.load_dataframe(f)

    # Rough box filter (deg). Ignoring RA wrap for simplicity.
    stars = stars_df[(stars_df['ra_degrees'] >= ra_min) & (stars_df['ra_degrees'] <= ra_max) &
                     (stars_df['dec_degrees'] >= dec_min) & (stars_df['dec_degrees'] <= dec_max)]

    # Map magnitude to marker size (smaller is dimmer)
    mag = stars['magnitude']
    size = (10.0 - mag.clip(0, 10)) * 1.5 + 1.0

    # Figure
    fig = bpl.figure(
        height=420,
        toolbar_location='above',
        x_axis_label='RA (deg)',
        y_axis_label='Dec (deg)',
        sizing_mode='stretch_width',
    )

    # Scatter stars
    fig.scatter(x=stars['ra_degrees'], y=stars['dec_degrees'], size=size, color='white', line_color=None, fill_alpha=0.9, marker="circle")
    fig.background_fill_color = "#000014"
    fig.border_fill_color = "#000014"
    fig.outline_line_color = "#333"
    fig.xgrid.grid_line_alpha = 0.2
    fig.ygrid.grid_line_alpha = 0.2
    # Improve contrast of axes and labels on dark background
    try:
        for ax in fig.xaxis:
            ax.axis_label_text_color = "#cfd8ff"
            ax.major_label_text_color = "#cfd8ff"
            ax.axis_line_color = "#8899cc"
            ax.major_tick_line_color = "#8899cc"
            ax.minor_tick_line_color = "#556699"
        for ay in fig.yaxis:
            ay.axis_label_text_color = "#cfd8ff"
            ay.major_label_text_color = "#cfd8ff"
            ay.axis_line_color = "#8899cc"
            ay.major_tick_line_color = "#8899cc"
            ay.minor_tick_line_color = "#556699"
    except Exception:
        pass

    # Camera FOV rectangle overlay
    angle_rad = rotation_deg * np.pi / 180.0
    fig.rect(x=ra_center_deg, y=dec_center_deg, width=fov_x_deg, height=fov_y_deg,
             angle=angle_rad, fill_alpha=0.1, fill_color='red', line_color='red', line_alpha=0.8)

    # Ranges
    fig.x_range.start = ra_min
    fig.x_range.end = ra_max
    fig.y_range.start = dec_min
    fig.y_range.end = dec_max

    # Mirror axes top/right without labels
    try:
        top_axis = mpl.LinearAxis()
        top_axis.axis_label = ''
        top_axis.axis_label_text_font_size = '0pt'
        top_axis.major_label_text_font_size = '0pt'
        top_axis.axis_line_color = "#8899cc"
        top_axis.major_tick_line_color = "#8899cc"
        top_axis.minor_tick_line_color = "#556699"
        fig.add_layout(top_axis, 'above')
    except Exception:
        pass
    try:
        right_axis = mpl.LinearAxis()
        right_axis.axis_label = ''
        right_axis.axis_label_text_font_size = '0pt'
        right_axis.major_label_text_font_size = '0pt'
        right_axis.axis_line_color = "#8899cc"
        right_axis.major_tick_line_color = "#8899cc"
        right_axis.minor_tick_line_color = "#556699"
        fig.add_layout(right_axis, 'right')
    except Exception:
        pass

    return fig


def _try_load_constellation_lines():
    """
    Attempts to load constellation line segments and optional labels from
    OSTdata/obs_run/data/constellations_lines.json

    Expected JSON structure example:
    {
      "segments": [[ra1, dec1, ra2, dec2], ...],
      "labels": [[ra, dec, "Name"], ...]
    }
    Returns (segments, labels) or ([], []).
    """
    try:
        base = Path(__file__).resolve().parent
        import json

        # 1) Custom JSON (our simple structure)
        json_path = base / 'data' / 'constellations_lines.json'
        if json_path.exists():
            with open(json_path, 'r') as fh:
                data = json.load(fh)
            segments = data.get('segments', [])
            labels = data.get('labels', [])
            return segments, labels

        # 2) GeoJSON (lines), optional GeoJSON (labels)
        geojson_lines = base / 'data' / 'constellations_lines.geojson'
        geojson_labels = base / 'data' / 'constellations_labels.geojson'
        segments: list[list[float]] = []
        labels: list[list[object]] = []

        def _load_geojson(path: Path):
            print(f"Loading geojson from {path}")
            try:
                with open(path, 'r') as fh:
                    return json.load(fh)
            except Exception:
                return None

        gj = _load_geojson(geojson_lines)
        if gj and 'features' in gj:
            for feat in gj['features']:
                geom = feat.get('geometry') or {}
                gtype = (geom.get('type') or '').lower()
                coords = geom.get('coordinates')
                if not coords:
                    continue
                if gtype == 'linestring':
                    # linestring: list of [ra, dec]; make segments per consecutive points
                    try:
                        for i in range(len(coords) - 1):
                            (ra1, dc1) = coords[i]
                            (ra2, dc2) = coords[i + 1]
                            segments.append([float(ra1), float(dc1), float(ra2), float(dc2)])
                    except Exception:
                        continue
                elif gtype == 'multilinestring':
                    try:
                        for line in coords:
                            for i in range(len(line) - 1):
                                (ra1, dc1) = line[i]
                                (ra2, dc2) = line[i + 1]
                                segments.append([float(ra1), float(dc1), float(ra2), float(dc2)])
                    except Exception:
                        continue

        gj_labels = _load_geojson(geojson_labels)
        if gj_labels and 'features' in gj_labels:
            for feat in gj_labels['features']:
                geom = feat.get('geometry') or {}
                props = feat.get('properties') or {}
                gtype = (geom.get('type') or '').lower()
                coords = geom.get('coordinates')
                name = props.get('name') or props.get('NAME') or props.get('iauname') or props.get('IAU')
                if not name:
                    continue
                try:
                    if gtype == 'point' and isinstance(coords, (list, tuple)) and len(coords) >= 2:
                        ra, dc = float(coords[0]), float(coords[1])
                        labels.append([ra, dc, str(name)])
                except Exception:
                    continue

        if segments:
            return segments, labels

        # 3) Optional: GeoPackage via geopandas (if available)
        gpkg_path = base / 'data' / 'constellations_lines.gpkg'
        if gpkg_path.exists():
            try:
                import geopandas as gpd  # type: ignore
                gdf = gpd.read_file(gpkg_path)
                for _, row in gdf.iterrows():
                    geom = row.geometry
                    if geom is None:
                        continue
                    try:
                        if geom.geom_type == 'LineString':
                            xs, ys = geom.xy
                            for i in range(len(xs) - 1):
                                segments.append([float(xs[i]), float(ys[i]), float(xs[i+1]), float(ys[i+1])])
                        elif geom.geom_type == 'MultiLineString':
                            for line in geom.geoms:
                                xs, ys = line.xy
                                for i in range(len(xs) - 1):
                                    segments.append([float(xs[i]), float(ys[i]), float(xs[i+1]), float(ys[i+1])])
                    except Exception:
                        continue
                if not labels and 'name' in gdf.columns:
                    try:
                        # crude centroid for labels
                        gdf_cent = gdf.to_crs(4326)
                        for _, row in gdf_cent.iterrows():
                            if row.geometry is None:
                                continue
                            c = row.geometry.representative_point()
                            labels.append([float(c.x), float(c.y), str(row.get('name'))])
                    except Exception:
                        pass
                if segments:
                    return segments, labels
            except Exception:
                pass

        return [], []
    except Exception:
        return [], []


def plot_sky_fov_with_constellations(ra_center_deg, dec_center_deg, fov_x_deg, fov_y_deg,
                                     scale=8.0, rotation_deg=0.0, show_constellations=False):
    """
    Wrapper that optionally overlays constellation lines and labels.
    """
    fig = plot_sky_fov(ra_center_deg, dec_center_deg, fov_x_deg, fov_y_deg, scale=scale, rotation_deg=rotation_deg)
    if not show_constellations:
        return fig

    segments, labels = _try_load_constellation_lines()
    if not segments:
        return fig

    half_w = 0.5 * max(0.01, float(fov_x_deg)) * float(scale)
    half_h = 0.5 * max(0.01, float(fov_y_deg)) * float(scale)
    ra_min = ra_center_deg - half_w
    ra_max = ra_center_deg + half_w
    dec_min = dec_center_deg - half_h
    dec_max = dec_center_deg + half_h

    # Filter and plot line segments within box (naive RA wrap handling)
    xs = []
    ys = []
    for s in segments:
        try:
            ra1, dc1, ra2, dc2 = map(float, s)
        except Exception:
            continue
        if (ra_min <= ra1 <= ra_max and dec_min <= dc1 <= dec_max) or (ra_min <= ra2 <= ra_max and dec_min <= dc2 <= dec_max):
            xs.append([ra1, ra2])
            ys.append([dc1, dc2])
    if xs:
        fig.multi_line(xs, ys, line_color="#5555ff", line_alpha=0.6, line_width=1)

    # Labels only when sufficiently zoomed out
    if labels and scale >= 10:
        try:
            import pandas as pd
            lbl_filtered = [[float(ra), float(dc), str(name)] for (ra, dc, name) in labels
                            if (ra_min <= float(ra) <= ra_max and dec_min <= float(dc) <= dec_max)]
            if lbl_filtered:
                df = pd.DataFrame(lbl_filtered, columns=['ra', 'dec', 'name'])
                source = ColumnDataSource(df)
                from bokeh.models import LabelSet
                labelset = LabelSet(x='ra', y='dec', text='name', text_color="#8888ff",
                                    text_font_size='9pt', x_offset=4, y_offset=4, source=source,
                                    background_fill_color=None, render_mode='css')
                fig.add_layout(labelset)
        except Exception:
            pass

    return fig
