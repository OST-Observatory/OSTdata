"""Session-based authentication tests (hard-cut from DRF tokens)."""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

User = get_user_model()


class SessionAuthTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='alice-pass')
        self.login_url = '/api/users/auth/login/'
        self.logout_url = '/api/users/auth/logout/'
        self.user_url = '/api/users/auth/user/'
        self.csrf_url = '/api/users/auth/csrf/'
        self.change_password_url = '/api/users/auth/change-password/'

    def _csrf_header(self):
        self.client.get(self.csrf_url)
        token = self.client.cookies.get('csrftoken')
        self.assertIsNotNone(token)
        return {'HTTP_X_CSRFTOKEN': token.value}

    def test_csrf_endpoint_sets_cookie(self):
        resp = self.client.get(self.csrf_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('csrftoken', self.client.cookies)
        self.assertFalse(resp.data['authenticated'])

    def test_login_sets_session_without_token_field(self):
        resp = self.client.post(
            self.login_url,
            {'username': 'alice', 'password': 'alice-pass'},
            format='json',
            **self._csrf_header(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('user', resp.data)
        self.assertNotIn('token', resp.data)
        self.assertEqual(resp.data['user']['username'], 'alice')

        user_resp = self.client.get(self.user_url)
        self.assertEqual(user_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(user_resp.data['username'], 'alice')

    def test_login_invalid_credentials(self):
        resp = self.client.post(
            self.login_url,
            {'username': 'alice', 'password': 'wrong'},
            format='json',
            **self._csrf_header(),
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_invalidates_session(self):
        self.client.force_login(self.user)
        logout_resp = self.client.post(self.logout_url, **self._csrf_header())
        self.assertEqual(logout_resp.status_code, status.HTTP_200_OK)

        user_resp = self.client.get(self.user_url)
        self.assertEqual(user_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unsafe_request_without_csrf_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        resp = client.post(self.logout_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unsafe_request_with_csrf_allowed(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.get(self.csrf_url)
        token = client.cookies.get('csrftoken')
        resp = client.post(self.logout_url, HTTP_X_CSRFTOKEN=token.value)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_change_password_invalidates_session(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            self.change_password_url,
            {
                'old_password': 'alice-pass',
                'new_password1': 'new-pass-123',
                'new_password2': 'new-pass-123',
            },
            format='json',
            **self._csrf_header(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data.get('relogin_required'))

        user_resp = self.client.get(self.user_url)
        self.assertEqual(user_resp.status_code, status.HTTP_403_FORBIDDEN)

        login_resp = self.client.post(
            self.login_url,
            {'username': 'alice', 'password': 'new-pass-123'},
            format='json',
            **self._csrf_header(),
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)
