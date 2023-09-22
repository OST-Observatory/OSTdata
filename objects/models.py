from django.db import models

from django.conf import settings

from astropy.coordinates.angles import Angle

from obs_run.models import ObservationRun, DataFile

from simple_history.models import HistoricalRecords

from tags.models import Tag

from users.models import get_sentinel_user


class Object(models.Model):
    #   An object can be associated with multiple observation runs.
    observation_run = models.ManyToManyField(
        ObservationRun,
        blank=True,
    )

    #   An object can be associated with multiple data files.
    datafiles = models.ManyToManyField(
        DataFile,
        blank=True,
    )

    #   Name
    name = models.CharField(max_length=200)

    #   Rights management
    is_public = models.BooleanField(default=True)

    #   Coordinates
    ra = models.FloatField(default=-1)
    dec = models.FloatField(default=-1)

    # JD the object was first observed
    first_hjd = models.FloatField(default=0.)

    #   Is it a main target
    is_main = models.BooleanField(default=True)

    #   Was the target observed photometrically or/and spectroscopically
    photometry = models.BooleanField(default=False)
    spectroscopy = models.BooleanField(default=False)

    #   Can the target be resolved by Simbad
    simbad_resolved = models.BooleanField(default=False)

    #   Object type
    STAR_CLUSTER = 'SC'
    SOLAR_SYSTEM = 'SO'
    GALAXY = 'GA'
    NEBULA = 'NE'
    STAR = 'ST'
    OTHER = 'OT'
    UNKNOWN = 'UK'
    OBJECT_TYPE_CHOICES = (
        (GALAXY,       'Galaxy'),
        (STAR_CLUSTER, 'Star cluster'),
        (NEBULA,       'Nebula'),
        (SOLAR_SYSTEM, 'Solar system'),
        (STAR,         'Star'),
        (OTHER,        'Other'),
        (UNKNOWN,      'Unknown')
    )
    object_type = models.CharField(
        max_length=2,
        choices=OBJECT_TYPE_CHOICES,
        default=UNKNOWN,
    )

    #   Field to add notes etc.
    note = models.TextField(default='', blank=True)

    #   Tags
    # tags = models.ManyToManyField(Tag, related_name='objects', blank=True)
    tags = models.ManyToManyField(Tag, blank=True)

    #   Bookkeeping
    history = HistoricalRecords()
    # added_on      = models.DateTimeField(auto_now_add=True)
    # last_modified = models.DateTimeField(auto_now=True)
    # added_by      = models.ForeignKey(
    #     settings.AUTH_USER_MODEL,
    #     on_delete=models.SET(get_sentinel_user),
    #     null=True,
    #     # related_name='added_run',
    # )

    # #   Get JD the object was first observed
    # def first_hjd(self):
    #     valid_datafiles = self.datafile_set.filter(hjd__gt=2451545) \
    #                           .order_by('hjd')
    #     if not valid_datafiles:
    #         return 0.
    #     else:
    #         return valid_datafiles[0].hjd

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
        return "{}: {:.2f} {:.2f}".format(
            self.name,
            self.ra,
            self.dec,
        )


class Identifier(models.Model):
    """
    An alternative name for a object
    """
    #   Alternative names should be removed when the object is removed
    obj = models.ForeignKey(Object, on_delete=models.CASCADE)

    name = models.CharField(max_length=200)

    href = models.CharField(max_length=400, blank=True)

    info_from_header = models.BooleanField(default=False)

    #   Bookkeeping
    history = HistoricalRecords()
    # added_on      = models.DateTimeField(auto_now_add=True)
    # last_modified = models.DateTimeField(auto_now=True)
    # added_by      = models.ForeignKey(
    #     settings.AUTH_USER_MODEL,
    #     on_delete=models.SET(get_sentinel_user),
    #     null=True,
    # )

    #   String representation of self
    def __str__(self):
        return "{} = {} ; {}".format(self.obj.name, self.name, self.href)
