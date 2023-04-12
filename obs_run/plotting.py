import numpy as np

import datetime

from astropy.time import Time
import astropy.units as u
from astropy.coordinates import SkyCoord, AltAz, get_moon
from astropy.time import Time

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

    #   Convert JD to datetime object and set x-axis formatter
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
        fig.xaxis.axis_label = 'JD'
        fig.yaxis.axis_label_text_font_size = '10pt'
        fig.xaxis.axis_label_text_font_size = '10pt'
        fig.min_border = 5

        #   Fill tabs list
        tabs.append(TabPanel(child=fig, title=y_axis_lable[i]))

    #   Make figure from tabs list
    return Tabs(tabs=tabs)

