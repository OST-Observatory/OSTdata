"""Effective exposure type: rule behaviour and Python/SQL equivalence."""
from itertools import product

from django.db.models import Count
from django.test import TestCase, override_settings

from obs_run.exposure_type import (
    RULE_AGREE,
    RULE_HEADER_FIRST,
    RULES,
    effective_exposure_type,
)
from obs_run.models import DataFile, ObservationRun
from utilities import annotate_effective_exposure_type, get_effective_exposure_type_filter

HEADERS = ['UK', 'LI', 'DA']
MLS = [None, '', 'UK', 'LI', 'DA']
USERS = [None, '', 'LI', 'UK']
CODES = ['UK', 'LI', 'DA']


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


class EffectiveExposureTypeSqlEquivalenceTest(TestCase):
    """Every header/ML/user combination: SQL annotation and Q filter == Python function."""

    @classmethod
    def setUpTestData(cls):
        cls.expected_args = {}
        for i, (header, ml, user) in enumerate(product(HEADERS, MLS, USERS)):
            run = ObservationRun.objects.create(name=f'run-{i}')
            datafile = DataFile.objects.create(
                observation_run=run, datafile=f'/tmp/{i}.fit', file_type='FITS',
                exposure_type=header, exposure_type_ml=ml, exposure_type_user=user,
            )
            cls.expected_args[datafile.pk] = (header, ml, user)

    def _expected(self, pk, rule):
        return effective_exposure_type(*self.expected_args[pk], rule=rule)

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
