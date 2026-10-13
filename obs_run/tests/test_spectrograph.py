"""Spectrograph constraints, format default exposure type and their write paths."""
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from obs_run.analyze_image_and_video_header import analyze_video
from obs_run.exposure_type import format_default_exposure_type
from obs_run.models import DataFile, ObservationRun
from obs_run.spectrograph import automatic_spectrograph, constrained_spectrograph
from obs_run.tests.test_visibility_acl import _grant

User = get_user_model()

IMAGING_ONLY = [r'qhy\s*600m', r'zwo']


@override_settings(SPECTROGRAPH_IMAGING_ONLY_INSTRUMENTS=IMAGING_ONLY)
class ConstrainedSpectrographTest(TestCase):
    def test_constraints(self):
        cases = [
            # exposure type, instrument, spectrograph, expected value, expected reason
            ('DA', 'QHY268M', 'B', 'N', 'exposure_type'),
            ('BI', 'Apogee USB/Net', 'E', 'N', 'exposure_type'),
            ('LI', 'QHY 600M', 'D', 'N', 'instrument'),
            ('LI', 'QHY600M', 'E', 'N', 'instrument'),
            ('LI', 'QHY CCD QHY600M-62e19d4', 'D', 'N', 'instrument'),
            ('LI', 'ZWO ASI2600MC Pro(2600)', 'E', 'N', 'instrument'),
            ('LI', 'QHY268M', 'D', 'D', None),
            ('WA', 'SBIG ST-8 3 CCD Camera', 'B', 'B', None),
            ('LI', 'Apogee USB/Net', 'E', 'E', None),
            ('LI', '', 'E', 'E', None),
            ('DA', 'QHY 600M', 'N', 'N', None),
        ]
        for exposure_type, instrument, spectrograph, value, reason in cases:
            with self.subTest(exposure_type=exposure_type, instrument=instrument, spectrograph=spectrograph):
                self.assertEqual(constrained_spectrograph(exposure_type, instrument, spectrograph), (value, reason))

    def test_instrument_list_is_configurable(self):
        with self.settings(SPECTROGRAPH_IMAGING_ONLY_INSTRUMENTS=[r'qhy\s*600m']):
            self.assertEqual(constrained_spectrograph('LI', 'ZWO ASI2600MC Pro', 'D'), ('D', None))

    def test_automatic_spectrograph(self):
        datafile = DataFile(exposure_type='LI', exposure_type_ml='LI', instrument='QHY268M', spectrograph='N')
        self.assertEqual(automatic_spectrograph(datafile, 'B'), 'B')
        datafile.exposure_type_user = 'DA'
        self.assertEqual(automatic_spectrograph(datafile, 'B'), 'N')
        datafile.spectrograph, datafile.spectrograph_override = 'B', True
        self.assertEqual(automatic_spectrograph(datafile, 'D'), 'B')


@override_settings(EXPOSURE_TYPE_LIGHT_DEFAULT_FORMATS=['JPG', 'CR2', 'SER', 'AVI', 'MOV'])
class FormatDefaultExposureTypeTest(TestCase):
    def test_defaults(self):
        for file_type, expected in [('JPG', 'LI'), ('cr2', 'LI'), ('MOV', 'LI'), ('TIFF', 'UK'), ('FITS', 'UK')]:
            with self.subTest(file_type=file_type):
                self.assertEqual(format_default_exposure_type(file_type), expected)

    def test_analysis_respects_override(self):
        run = ObservationRun.objects.create(name='video')
        video = DataFile.objects.create(observation_run=run, datafile='/nonexistent/a.mov', file_type='MOV')
        analyze_video(video)
        self.assertEqual(video.exposure_type, 'LI')

        video.exposure_type, video.exposure_type_override = 'DA', True
        analyze_video(video)
        self.assertEqual(video.exposure_type, 'DA')


@override_settings(SPECTROGRAPH_IMAGING_ONLY_INSTRUMENTS=IMAGING_ONLY)
class ApplySpectrographRulesTest(TestCase):
    def setUp(self):
        run = ObservationRun.objects.create(name='mixed')
        common = {'observation_run': run, 'file_type': 'FITS'}
        self.dark = DataFile.objects.create(
            datafile='/tmp/d.fit', exposure_type='DA', exposure_type_ml='DA', spectrograph='B', **common,
        )
        self.imaging = DataFile.objects.create(
            datafile='/tmp/l.fit', exposure_type='LI', exposure_type_ml='LI', spectrograph='D',
            instrument='QHY 600M', **common,
        )
        self.spectrum = DataFile.objects.create(
            datafile='/tmp/s.fit', exposure_type='LI', exposure_type_ml='LI', spectrograph='D',
            instrument='QHY268M', **common,
        )
        self.manual = DataFile.objects.create(
            datafile='/tmp/m.fit', exposure_type='DA', exposure_type_ml='DA', spectrograph='B',
            spectrograph_override=True, **common,
        )

    def _values(self):
        return [DataFile.objects.get(pk=f.pk).spectrograph for f in (self.dark, self.imaging, self.spectrum, self.manual)]

    def test_dry_run(self):
        out = StringIO()
        call_command('apply_spectrograph_rules', '--dry-run', stdout=out)
        self.assertEqual(self._values(), ['B', 'D', 'D', 'B'])
        self.assertIn('B -> N (exposure_type)', out.getvalue())
        self.assertIn('D -> N (instrument)', out.getvalue())

    def test_apply(self):
        call_command('apply_spectrograph_rules', stdout=StringIO())
        self.assertEqual(self._values(), ['N', 'N', 'D', 'B'])
        self.assertEqual(self.dark.history.latest().history_change_reason, 'task:spectrograph_rules')


@override_settings(SPECTROGRAPH_IMAGING_ONLY_INSTRUMENTS=IMAGING_ONLY)
class ExposureTypeUserSpectrographTest(APITestCase):
    def setUp(self):
        run = ObservationRun.objects.create(name='baches')
        self.datafile = DataFile.objects.create(
            observation_run=run, datafile='/tmp/x.fit', file_type='FITS', exposure_type='LI',
            exposure_type_ml='LI', spectrograph='B', instrument='QHY268M',
        )
        user = User.objects.create_user(username='curator', password='pw')
        _grant(user, 'acl_datafiles_exposure_type_user')
        self.client.get('/api/users/auth/csrf/')
        self.client.force_login(user)

    def _patch(self, payload):
        token = self.client.cookies.get(settings.CSRF_COOKIE_NAME)
        headers = {'HTTP_X_CSRFTOKEN': token.value} if token else {}
        url = f'/api/admin/datafiles/{self.datafile.pk}/exposure-type-user/'
        return self.client.patch(url, payload, format='json', **headers)

    def test_dark_label_clears_spectrograph(self):
        response = self._patch({'exposure_type_user': 'DA'})
        self.assertEqual(response.status_code, 200, response.content)
        self.datafile.refresh_from_db()
        self.assertEqual(self.datafile.spectrograph, 'N')

    def test_manual_spectrograph_is_kept(self):
        DataFile.objects.filter(pk=self.datafile.pk).update(spectrograph_override=True)
        self._patch({'exposure_type_user': 'DA'})
        self.datafile.refresh_from_db()
        self.assertEqual(self.datafile.spectrograph, 'B')

    def test_light_label_keeps_spectrograph(self):
        self._patch({'exposure_type_user': 'LI'})
        self.datafile.refresh_from_db()
        self.assertEqual(self.datafile.spectrograph, 'B')
