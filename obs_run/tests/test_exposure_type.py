"""Effective exposure type: rule behaviour and Python/SQL equivalence."""
from itertools import product

from django.db.models import Count
from django.test import TestCase, override_settings

from obs_run.exposure_type import (
    RULE_AGREE,
    RULE_HEADER_FIRST,
    RULES,
    arc_lamp_token,
    effective_exposure_type,
    name_rule_exposure_type,
)
from obs_run.models import DataFile, ObservationRun
from utilities import annotate_effective_exposure_type, get_effective_exposure_type_filter

HEADERS = ['UK', 'LI', 'DA']
MLS = [None, '', 'UK', 'LI', 'DA']
USERS = [None, '', 'LI', 'UK']
NAMES = ['{}.fit', 'DADOS_Ar-Ne-{}_1s.fit']
CODES = ['UK', 'LI', 'DA', 'WA']


class EffectiveExposureTypeRuleTest(TestCase):
    def test_header_first(self):
        cases = [
            # header, ml, user, expected
            ('LI', 'DA', 'FL', 'FL'),  # user label wins
            ('LI', None, None, 'LI'),  # ML not run
            ('LI', 'UK', None, 'LI'),  # ML abstained -> header
            ('UK', 'DA', None, 'DA'),  # header gap -> ML
            ('UK', 'UK', None, 'UK'),
            ('DA', 'DA', None, 'DA'),
            ('LI', 'DA', None, 'UK'),  # disagreement -> review
        ]
        for header, ml, user, expected in cases:
            with self.subTest(header=header, ml=ml, user=user):
                self.assertEqual(effective_exposure_type(header, ml, user, RULE_HEADER_FIRST), expected)

    def test_agree(self):
        cases = [
            ('LI', 'DA', 'FL', 'FL'),
            ('LI', None, None, 'LI'),
            ('LI', 'UK', None, 'UK'),
            ('UK', 'DA', None, 'UK'),
            ('DA', 'DA', None, 'DA'),
            ('LI', 'DA', None, 'UK'),
        ]
        for header, ml, user, expected in cases:
            with self.subTest(header=header, ml=ml, user=user):
                self.assertEqual(effective_exposure_type(header, ml, user, RULE_AGREE), expected)

    @override_settings(EXPOSURE_TYPE_EFFECTIVE_RULE='agree')
    def test_model_property_follows_setting(self):
        datafile = DataFile(exposure_type='UK', exposure_type_ml='DA')
        self.assertEqual(datafile.effective_exposure_type, 'UK')
        with self.settings(EXPOSURE_TYPE_EFFECTIVE_RULE='header_first'):
            self.assertEqual(datafile.effective_exposure_type, 'DA')

    @override_settings(EXPOSURE_TYPE_EFFECTIVE_RULE='nonsense')
    def test_invalid_setting(self):
        with self.assertRaises(ValueError):
            DataFile(exposure_type='LI').effective_exposure_type


class NameRuleTest(TestCase):
    def test_arc_lamp_names(self):
        for name in ('DADOS_Ar-Ne-0001_1s.fit', 'thar_2s.FIT', 'ThAr001.fit', 'hg_ar.fits', 'ne_ar_5s.fit',
                     'Neon.fit', 'argon-01.fit', 'wavecal_0003.fit', 'arc_001.fit', 'DADOS_ArNe.fit'):
            with self.subTest(name=name):
                self.assertTrue(arc_lamp_token(f'/data/run/{name}', ''))
        for name in ('arcturus_300.FIT', 'moon_near_terminator.fit', 'barnes_star.fit', 'search.fit', 'm42.fit',
                     'neonova.fit', 'darkflat.fit'):
            with self.subTest(name=name):
                self.assertIsNone(arc_lamp_token(f'/data/run/{name}', 'M 42'))

    def test_object_and_directory(self):
        self.assertEqual(arc_lamp_token('/data/run/0001.fit', 'ThAr lamp'), 'thar')
        self.assertIsNone(arc_lamp_token('/data/thar/0001.fit', ''))  # directories are not used

    def test_header_types_and_setting(self):
        self.assertEqual(name_rule_exposure_type('LI', 'thar.fit', '', enabled=True), 'WA')
        self.assertEqual(name_rule_exposure_type('UK', 'thar.fit', '', enabled=True), 'WA')
        self.assertEqual(name_rule_exposure_type('DA', 'thar.fit', '', enabled=True), '')
        self.assertEqual(name_rule_exposure_type('FL', 'thar.fit', '', enabled=True), '')
        with self.settings(EXPOSURE_TYPE_NAME_RULE=False):
            self.assertEqual(name_rule_exposure_type('LI', 'thar.fit', ''), '')

    def test_precedence(self):
        for rule in RULES:
            with self.subTest(rule=rule):
                self.assertEqual(effective_exposure_type('LI', 'DA', None, rule, name_rule='WA'), 'WA')
                self.assertEqual(effective_exposure_type('LI', 'DA', 'LI', rule, name_rule='WA'), 'LI')

    def test_save_keeps_rule_in_sync(self):
        run = ObservationRun.objects.create(name='2024-12-12')
        with self.settings(EXPOSURE_TYPE_NAME_RULE=True):
            datafile = DataFile.objects.create(observation_run=run, datafile='/d/DADOS_Ar-Ne-0001_1s.fit',
                                               file_type='FITS', exposure_type='LI', exposure_type_ml='DA')
            self.assertEqual((datafile.exposure_type_rule, datafile.effective_exposure_type), ('WA', 'WA'))
            datafile.exposure_type = 'DA'
            datafile.save(update_fields=['exposure_type'])
            datafile.refresh_from_db()
            self.assertEqual(datafile.exposure_type_rule, '')
        with self.settings(EXPOSURE_TYPE_NAME_RULE=False):
            datafile = DataFile.objects.create(observation_run=run, datafile='/d/thar.fit', file_type='FITS',
                                               exposure_type='LI')
            self.assertEqual(datafile.exposure_type_rule, '')


@override_settings(EXPOSURE_TYPE_NAME_RULE=True)
class EffectiveExposureTypeSqlEquivalenceTest(TestCase):
    """Every header/ML/user/name combination: SQL annotation and Q filter == Python function."""

    @classmethod
    def setUpTestData(cls):
        cls.expected_args = {}
        for i, (header, ml, user, name) in enumerate(product(HEADERS, MLS, USERS, NAMES)):
            run = ObservationRun.objects.create(name=f'run-{i}')
            datafile = DataFile.objects.create(
                observation_run=run, datafile=f'/tmp/{name.format(i)}', file_type='FITS',
                exposure_type=header, exposure_type_ml=ml, exposure_type_user=user,
            )
            cls.expected_args[datafile.pk] = (header, ml, user, datafile.exposure_type_rule)
        assert any(args[3] for args in cls.expected_args.values())

    def _expected(self, pk, rule):
        header, ml, user, name_rule = self.expected_args[pk]
        return effective_exposure_type(header, ml, user, rule=rule, name_rule=name_rule)

    def test_annotation(self):
        for rule in RULES:
            with self.subTest(rule=rule), self.settings(EXPOSURE_TYPE_EFFECTIVE_RULE=rule):
                rows = annotate_effective_exposure_type(DataFile.objects.all()).values_list(
                    'pk', 'annotated_effective_exposure_type',
                )
                for pk, value in rows:
                    self.assertEqual(value, self._expected(pk, rule), self.expected_args[pk])

    def test_filter(self):
        for rule, code in product(RULES, CODES):
            with self.subTest(rule=rule, code=code), self.settings(EXPOSURE_TYPE_EFFECTIVE_RULE=rule):
                matched = set(
                    DataFile.objects.filter(get_effective_exposure_type_filter(code)).values_list('pk', flat=True)
                )
                expected = {pk for pk in self.expected_args if self._expected(pk, rule) == code}
                self.assertEqual(matched, expected)

    def test_related_count_filter(self):
        for rule, code in product(RULES, CODES):
            with self.subTest(rule=rule, code=code), self.settings(EXPOSURE_TYPE_EFFECTIVE_RULE=rule):
                runs = ObservationRun.objects.annotate(
                    n=Count('datafile', filter=get_effective_exposure_type_filter(code, 'datafile__')),
                )
                counted = {run.datafile_set.get().pk: run.n for run in runs}
                expected = {pk: int(self._expected(pk, rule) == code) for pk in self.expected_args}
                self.assertEqual(counted, expected)
