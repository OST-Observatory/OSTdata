from django.db import models

from django.conf import settings

from collections import OrderedDict

from astropy.io import fits
from astropy.coordinates.angles import Angle

from users.models import get_sentinel_user

from tags.models import Tag

from .analyze_files import set_file_info

############################################################################

class Obs_run(models.Model):
    #   Name
    name = models.CharField(max_length=200)

    #   Rights management
    is_public = models.BooleanField(default=True)

    readonly_users  = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='readonly_run',
        blank=True,
    )
    readwrite_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='readwrite_run',
        blank=True,
    )
    managers        = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='managed_run',
        blank=True,
    )

    #   Data reduction status
    PARTLY_REDUCED   = 'PR'
    FULLY_REDUCED    = 'FR'
    REDUCTION_FAILED = 'ER'
    NEW              = 'NE'
    REDUCTION_STATUS_CHOICES = (
        (PARTLY_REDUCED,   'Partly reduced'),
        (FULLY_REDUCED,    'Fully reduced'),
        (REDUCTION_FAILED, 'Reduction error'),
        (NEW,              'New')
    )
    reduction_status = models.CharField(
        max_length=2,
        choices=REDUCTION_STATUS_CHOICES,
        default=NEW,
    )

    #   Observation type
    photometry = models.BooleanField(default=False)
    spectroscopy = models.BooleanField(default=False)

    #   Field to add notes etc.
    note = models.TextField(default='', blank=True)

    #   Tags
    # tags = models.ManyToManyField(Tag, related_name='runs', blank=True)
    tags = models.ManyToManyField(Tag, blank=True)

    #   Bookkeeping
    added_on      = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    added_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET(get_sentinel_user),
        null=True,
        # related_name='added_run',
    )

    #   String representation of self
    def __str__(self):
        return self.name


class DataFile(models.Model):
    """
    Super class for any file that contains data.
    """
    #   DataFile belongs to an observation run and is deleted when the
    #   observation run is deleted.
    obsrun = models.ForeignKey(
        Obs_run,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    #   The file
    datafile = models.FilePathField(max_length=150)

    #   File type (FITS, CR2, ...)
    file_type = models.CharField(max_length=50, default='')

    #   Exposure type
    BIAS = 'BI'
    DARK = 'DA'
    FLAT = 'FL'
    LIGHT = 'LI'
    UNKNOWN = 'UK'
    EXPOSURE_TYPE_POSSIBILITIES = (
        (BIAS, 'Bias'),
        (DARK, 'Dark'),
        (FLAT, 'Flat'),
        (LIGHT, 'Light'),
        (UNKNOWN, 'Unknown'),
    )
    exposure_type = models.CharField(
        max_length=2,
        choices=EXPOSURE_TYPE_POSSIBILITIES,
        default=UNKNOWN,
    )

    #   Telescope and instrument
    instrument = models.CharField(max_length=50, default='')
    telescope = models.CharField(max_length=50, default='')
    focal_length = models.FloatField(default=-1)

    #   Exposure parameters
    hjd = models.FloatField(default=-1)
    obs_date = models.CharField(max_length=50, default='')
    exptime = models.FloatField(default=-1)

    #   Image parameters
    naxis1 = models.FloatField(default=-1)
    naxis2 = models.FloatField(default=-1)
    pixel_size = models.FloatField(default=-1)

    #   Filed of view
    fov_x = models.FloatField(default=-1)
    fov_y = models.FloatField(default=-1)

    #   Target infos
    main_target = models.CharField(max_length=50, default='Unknown')
    ra = models.FloatField(default=-1)
    dec = models.FloatField(default=-1)

    #   Observing conditions
    airmass =  models.FloatField(default=-1)
    #   Ambient temperature in deg C
    ambient_temperature =  models.FloatField(default=-1)
    #   Dewpoint in deg C
    dewpoint =  models.FloatField(default=-1)
    #   Barometric pressure in hPa
    pressure =  models.FloatField(default=-1)
    #   Humidity in %
    humidity =  models.FloatField(default=-1)
    #   Wind speed in m/s
    wind_speed =  models.FloatField(default=-1)
    #   Wind direction in deg
    wind_direction =  models.FloatField(default=-1)

    #   Tags
    # tags = models.ManyToManyField(Tag, related_name='datafile', blank=True)
    tags = models.ManyToManyField(Tag, blank=True)

    #   Bookkeeping
    added_on      = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    added_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET(get_sentinel_user),
        null=True,
        # related_name='added_run',
    )

    #   Get infos
    def set_infos(self):
        '''
            Get informations to fill the model
        '''
        # return get_file_info(self.pk)
        set_file_info(self)

    #   Get FITS header
    def get_fits_header(self, hdu=0):
        '''
            Get FITS Header
        '''
        try:
            header = fits.getheader(self.datafile, hdu)
            h = OrderedDict()
            #   Sanitize header
            for k, v in header.items():
                if (k != 'comment' and
                        k != 'history' and
                        k != '' and
                        type(v) is not fits.card.Undefined
                ):
                    h[k] = v
        except Exception as e:
            print(e)
            h = {}
        return h

    #   hms and dms representation for ra and dec
    def ra_hms(self):
        if self.ra != -1:
            try:
                a = Angle(float(self.ra), unit='degree').hms
            except Exception as e:
                # return self.ra
                return '-'
            return "{:02.0f}:{:02.0f}:{:05.2f}".format(*a)
        else:
            return '-'

    def dec_dms(self):
        if self.ra != -1:
            try:
                a = Angle(float(self.dec), unit='degree').dms
            except Exception as e:
                # return self.dec
                return '-'
            return "{:+03.0f}:{:02.0f}:{:05.2f}".format(
                a[0],
                abs(a[1]),
                abs(a[2]),
                )
        else:
            return '-'


    #   String representation of self
    def __str__(self):
        return "{} - {} - {}".format(
            self.file_type,
            self.exposure_type,
            self.obs_date,
        )
