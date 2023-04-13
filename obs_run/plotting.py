import numpy as np

import datetime

from astroplan import Observer

from astropy.time import Time
import astropy.units as u
from astropy.coordinates import SkyCoord, AltAz, get_moon, EarthLocation

from bokeh import models as mpl
from bokeh import plotting as bpl
from bokeh.models import TabPanel, Tabs

from .models import Obs_run

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
    observing_conditions = obs_run.datafile_set.all().order_by('hjd') \
        .values_list(
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
    tabs = []\

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

        #   Plot spectrum
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
    fig = bpl.figure(width=400, height=240, toolbar_location=None,
                     y_range=(0, 90), x_axis_type="datetime")

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

        frame_star = AltAz(obstime=times, location=ost_location)

        obj_altaz = obj.transform_to(frame_star)

        moon = get_moon(times)
        moon_altaz = moon.transform_to(frame_star)

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

        label = mpl.Label(x=75, y=40, x_units='screen', text='Could not calculate visibility', render_mode='css',
                          border_line_color='red', border_line_alpha=1.0, text_color='red',
                          background_fill_color='white', background_fill_alpha=1.0)

        fig.add_layout(label)

    return fig
