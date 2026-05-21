from django.test import TestCase

from objects.models import Object, Identifier
from objects.search import find_search_match_via, normalize_search_term


class ObjectSearchTests(TestCase):
    def setUp(self):
        self.obj = Object.objects.create(name='Andromeda Galaxy', object_type='GA')
        Identifier.objects.create(obj=self.obj, name='M 31')
        Identifier.objects.create(obj=self.obj, name='NGC 224')

    def test_find_search_match_via_alias(self):
        self.assertEqual(find_search_match_via(self.obj, 'M 31'), 'M 31')
        self.assertEqual(find_search_match_via(self.obj, 'M31'), 'M 31')
        self.assertIsNone(find_search_match_via(self.obj, 'Andromeda'))
        self.assertIsNone(find_search_match_via(self.obj, 'galaxy'))

    def test_normalize_search_term(self):
        self.assertEqual(normalize_search_term('  M31  '), 'M31')
