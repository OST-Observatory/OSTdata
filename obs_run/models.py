from django.db import models

from django.conf import settings

from simple_history.models import HistoricalRecords

from collections import OrderedDict

from astropy.io import fits
from astropy.coordinates.angles import Angle

# from users.models import get_sentinel_user

from tags.models import Tag

from .analyze_files import set_file_info
from pathlib import Path


############################################################################


class ObservationRun(models.Model):
    #   Name
    name = models.CharField(max_length=200)

    #   Rights management
    is_public = models.BooleanField(default=True)

    readonly_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='readonly_run',
        blank=True,
    )
    readwrite_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='readwrite_run',
        blank=True,
    )
    managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='managed_run',
        blank=True,
    )

    #   Data reduction status
    PARTLY_REDUCED = 'PR'
    FULLY_REDUCED = 'FR'
    REDUCTION_FAILED = 'ER'
    NEW = 'NE'
    REDUCTION_STATUS_CHOICES = (
        (PARTLY_REDUCED, 'Partly reduced'),
        (FULLY_REDUCED, 'Fully reduced'),
        (REDUCTION_FAILED, 'Reduction error'),
        (NEW, 'New')
    )
    reduction_status = models.CharField(
        max_length=2,
        choices=REDUCTION_STATUS_CHOICES,
        default=NEW,
    )

    #   Observation type
    photometry = models.BooleanField(default=False)
    spectroscopy = models.BooleanField(default=False)

    #   Julian date of the middle of the observation
    mid_observation_jd = models.FloatField(default=0)

    #   Field to add notes etc.
    note = models.TextField(default='', blank=True)

    #   Tags
    # tags = models.ManyToManyField(Tag, related_name='runs', blank=True)
    tags = models.ManyToManyField(Tag, blank=True)

    #   Override flags to prevent automatic tasks from overwriting user changes
    name_override = models.BooleanField(default=False)
    is_public_override = models.BooleanField(default=False)
    reduction_status_override = models.BooleanField(default=False)
    photometry_override = models.BooleanField(default=False)
    spectroscopy_override = models.BooleanField(default=False)
    note_override = models.BooleanField(default=False)
    mid_observation_jd_override = models.BooleanField(default=False)

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

    #   String representation of self
    def __str__(self):
        return self.name

    class Meta:
        indexes = [
            models.Index(fields=['mid_observation_jd'], name='run_mid_jd_idx'),
            models.Index(fields=['reduction_status'], name='run_red_status_idx'),
            models.Index(fields=['is_public'], name='run_is_public_idx'),
        ]


class DataFile(models.Model):
    """
    Super class for any file that contains data.
    """
    #   DataFile belongs to an observation run and is deleted when the
    #   observation run is deleted.
    observation_run = models.ForeignKey(
        ObservationRun,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    #   The file
    datafile = models.FilePathField(max_length=150)

    #   File metadata for reconciliation and integrity
    file_size = models.BigIntegerField(default=0)
    content_hash = models.CharField(max_length=64, default='', db_index=True)

    #   File type (FITS, CR2, ...)
    file_type = models.CharField(max_length=50, default='')

    #   Exposure type
    BIAS = 'BI'
    DARK = 'DA'
    FLAT = 'FL'
    LIGHT = 'LI'
    WAVE = 'WA'
    UNKNOWN = 'UK'
    EXPOSURE_TYPE_POSSIBILITIES = (
        (BIAS, 'Bias'),
        (DARK, 'Dark'),
        (FLAT, 'Flat'),
        (LIGHT, 'Light'),
        (WAVE, 'Wave'),
        (UNKNOWN, 'Unknown'),
    )
    exposure_type = models.CharField(
        max_length=2,
        choices=EXPOSURE_TYPE_POSSIBILITIES,
        default=UNKNOWN,
    )

    #   ML-based exposure type classification
    exposure_type_ml = models.CharField(
        max_length=2,
        choices=EXPOSURE_TYPE_POSSIBILITIES,
        default=UNKNOWN,
        blank=True,
        null=True,
        help_text='Exposure type determined by ML classification model',
    )
    exposure_type_ml_confidence = models.FloatField(
        default=None,
        blank=True,
        null=True,
        help_text='Confidence score from ML classification (0.0-1.0)',
    )
    exposure_type_ml_abstained = models.BooleanField(
        default=False,
        help_text='Whether the ML model abstained (returned unknown)',
    )

    #   User-set exposure type
    exposure_type_user = models.CharField(
        max_length=2,
        choices=EXPOSURE_TYPE_POSSIBILITIES,
        default=None,
        blank=True,
        null=True,
        help_text='Exposure type manually set by user',
    )
    exposure_type_user_override = models.BooleanField(
        default=False,
        help_text='Override flag to prevent automatic updates to user-set exposure type',
    )

    #   Spectroscopy?
    spectroscopy = models.BooleanField(default=False)
    spectrograph_possibilities = (
        ('D', 'DADOS'),
        ('B', 'BACHES'),
        ('E', 'EINSTEIN_TOWER'),
        ('N', 'NONE'),
    )
    spectrograph = models.CharField(
        max_length=1,
        choices=spectrograph_possibilities,
        default='N',
    )

    #   Telescope and instrument
    instrument = models.CharField(max_length=50, default='')
    telescope = models.CharField(max_length=50, default='')
    focal_length = models.FloatField(default=-1)

    #   Exposure parameters
    hjd = models.FloatField(default=-1)
    obs_date = models.CharField(max_length=50, default='')
    exptime = models.FloatField(default=-1)

    #   Camera parameters (for dark matching)
    ccd_temp = models.FloatField(default=-999)      # sensor temperature in °C
    gain = models.FloatField(default=-1)           
    egain = models.FloatField(default=-1)         
    pedestal = models.IntegerField(default=-1)       
    offset = models.IntegerField(default=-1)       
    readout_mode = models.CharField(max_length=50, default='') 
    binning_x = models.IntegerField(default=1)     
    binning_y = models.IntegerField(default=1)     

    #   Image parameters
    naxis1 = models.FloatField(default=-1)
    naxis2 = models.FloatField(default=-1)
    pixel_size = models.FloatField(default=-1)

    #   Filed of view
    fov_x = models.FloatField(default=-1)
    fov_y = models.FloatField(default=-1)

    #   Target info
    main_target = models.CharField(max_length=50, default='-')
    header_target_name = models.CharField(max_length=50, default='-')
    ra = models.FloatField(default=-1)
    dec = models.FloatField(default=-1)

    #   Observing conditions
    air_mass = models.FloatField(default=-1)
    #   Ambient temperature in deg C
    ambient_temperature = models.FloatField(default=-1)
    #   Dewpoint in deg C
    dewpoint = models.FloatField(default=-1)
    #   Barometric pressure in hPa
    pressure = models.FloatField(default=-1)
    #   Humidity in %
    humidity = models.FloatField(default=-1)
    #   Wind speed in m/s
    wind_speed = models.FloatField(default=-1)
    #   Wind direction in deg
    wind_direction = models.FloatField(default=-1)

    #   Tags
    # tags = models.ManyToManyField(Tag, related_name='datafile', blank=True)
    tags = models.ManyToManyField(Tag, blank=True)

    #   Bookkeeping
    history = HistoricalRecords()

    #   Status
    parameter_status_possibilities = (
        ('FIT', 'FITS'),
        ('CLA', 'CLASSIC_IMAGE_ANALYSIS'),
        ('AIA', 'AI_IMAGE_ANALYSIS'),
    )
    status_parameters = models.CharField(
        max_length=3,
        choices=parameter_status_possibilities,
        default='FIT',
    )

    #   Override flags to prevent automatic tasks from overwriting user changes
    exposure_type_override = models.BooleanField(default=False)
    spectroscopy_override = models.BooleanField(default=False)
    spectrograph_override = models.BooleanField(default=False)
    instrument_override = models.BooleanField(default=False)
    telescope_override = models.BooleanField(default=False)
    status_parameters_override = models.BooleanField(default=False)
    wcs_override = models.BooleanField(default=False)

    #   Plate Solving
    plate_solved = models.BooleanField(default=False)
    plate_solve_attempted_at = models.DateTimeField(null=True, blank=True)
    plate_solve_error = models.TextField(null=True, blank=True)
    plate_solve_tool = models.CharField(max_length=50, null=True, blank=True)
    re_evaluated_after_plate_solve = models.BooleanField(
        default=False,
        help_text='True if re_evaluate_plate_solved_files has processed this file (avoids double evaluation).'
    )

    #   WCS (World Coordinate System) parameters from plate solving
    wcs_ra = models.FloatField(null=True, blank=True)
    wcs_dec = models.FloatField(null=True, blank=True)
    wcs_ra_hms = models.CharField(max_length=20, null=True, blank=True)
    wcs_dec_dms = models.CharField(max_length=20, null=True, blank=True)
    wcs_field_radius = models.FloatField(null=True, blank=True)
    wcs_orientation = models.FloatField(null=True, blank=True)
    wcs_pix_scale = models.FloatField(null=True, blank=True)
    wcs_parity = models.CharField(max_length=20, null=True, blank=True)
    wcs_field_width = models.FloatField(null=True, blank=True)
    wcs_field_height = models.FloatField(null=True, blank=True)
    # FITS WCS parameters
    wcs_cd1_1 = models.FloatField(null=True, blank=True)
    wcs_cd1_2 = models.FloatField(null=True, blank=True)
    wcs_cd2_1 = models.FloatField(null=True, blank=True)
    wcs_cd2_2 = models.FloatField(null=True, blank=True)
    wcs_cdelt1 = models.FloatField(null=True, blank=True)
    wcs_cdelt2 = models.FloatField(null=True, blank=True)
    wcs_crota1 = models.FloatField(null=True, blank=True)
    wcs_crota2 = models.FloatField(null=True, blank=True)
    wcs_crpix1 = models.FloatField(null=True, blank=True)
    wcs_crpix2 = models.FloatField(null=True, blank=True)
    wcs_crval1 = models.FloatField(null=True, blank=True)
    wcs_crval2 = models.FloatField(null=True, blank=True)

    #   Get information
    def set_info(self):
        """
            Get information to fill the model
        """
        # return get_file_info(self.pk)
        set_file_info(self)

    #   Get FITS header
    def get_fits_header(self, hdu=0):
        """
            Get FITS Header
        """
        try:
            # Only attempt for FITS files
            path = Path(self.datafile)
            ext = path.suffix.lower()
            file_type = (self.file_type or '').upper()
            is_fits = (file_type == 'FITS') or (ext in ['.fits', '.fit', '.fts'])
            if not is_fits:
                return {}

            # Tolerate some malformed headers without spamming logs
            header = fits.getheader(self.datafile, hdu, ignore_missing_simple=True)
            h = OrderedDict()
            #   Sanitize header
            for k, v in header.items():
                if (k != 'comment' and
                        k != 'history' and
                        k != '' and
                        type(v) is not fits.card.Undefined):
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

    #   Effective exposure type based on priority logic
    @property
    def effective_exposure_type(self):
        """
        Determine the effective exposure type based on priority:
        1. exposure_type_user (if set, not None, not empty string)
        2. exposure_type_ml (if set AND matches exposure_type header value)
        3. 'UK' (Unknown) if exposure_type_ml is set but doesn't match exposure_type
        4. exposure_type (header-based, fallback)
        """
        # Priority 1: User-set type
        if self.exposure_type_user and self.exposure_type_user.strip():
            return self.exposure_type_user
        
        # Priority 2 & 3: ML type
        if self.exposure_type_ml and self.exposure_type_ml.strip():
            if self.exposure_type_ml == self.exposure_type:
                return self.exposure_type_ml
            else:
                return self.UNKNOWN  # 'UK'
        
        # Priority 4: Header-based type
        return self.exposure_type

    def get_effective_exposure_type_display(self):
        """
        Get the human-readable label for the effective exposure type.
        """
        effective_type = self.effective_exposure_type
        for code, label in self.EXPOSURE_TYPE_POSSIBILITIES:
            if code == effective_type:
                return label
        return 'Unknown'

    #   String representation of self
    def __str__(self):
        return "{} - {} - {}".format(
            self.file_type,
            self.exposure_type,
            self.obs_date,
        )

    class Meta:
        indexes = [
            models.Index(fields=['observation_run'], name='df_run_idx'),
            models.Index(fields=['file_type'], name='df_file_type_idx'),
            models.Index(fields=['exposure_type'], name='df_expo_type_idx'),
            models.Index(fields=['exposure_type_ml'], name='df_expo_type_ml_idx'),
            models.Index(fields=['exposure_type_user'], name='df_expo_type_user_idx'),
            models.Index(fields=['exptime'], name='df_exptime_idx'),
            models.Index(fields=['hjd'], name='df_hjd_idx'),
            models.Index(fields=['instrument'], name='df_instrument_idx'),
            models.Index(fields=['telescope'], name='df_telescope_idx'),
            models.Index(fields=['main_target'], name='df_main_target_idx'),
            models.Index(fields=['ccd_temp'], name='df_ccd_temp_idx'),
            models.Index(fields=['gain'], name='df_gain_idx'),
            models.Index(fields=['egain'], name='df_egain_idx'),
            models.Index(fields=['binning_x', 'binning_y'], name='df_binning_idx'),
        ]


class DownloadJob(models.Model):
    """Background job to prepare ZIP archives of data files.
    Stores minimal state for polling and retrieval.
    """
    STATUS_CHOICES = (
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='download_jobs',
    )
    run = models.ForeignKey(
        ObservationRun,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='download_jobs',
    )
    selected_ids = models.JSONField(null=True, blank=True)
    filters = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='queued')
    progress = models.IntegerField(default=0)
    bytes_total = models.BigIntegerField(default=0)
    bytes_done = models.BigIntegerField(default=0)
    file_path = models.CharField(max_length=512, blank=True, default='')
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"DownloadJob #{self.pk} ({self.status})"
