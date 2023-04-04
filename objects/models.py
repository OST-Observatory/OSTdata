from django.db import models

from django.conf import settings

from astropy.coordinates.angles import Angle

from obs_run.models import Obs_run, DataFile

from tags.models import Tag

from users.models import get_sentinel_user

class Object(models.Model):
    #   An object can be associated with multiple observation runs.
    obsrun = models.ManyToManyField(
        Obs_run,
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

    #   Is it a main target
    is_main = models.BooleanField(default=True)

    #   Tags
    # tags = models.ManyToManyField(Tag, related_name='objects', blank=True)
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
