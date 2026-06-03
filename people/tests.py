from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

class AuthLogoutCacheTests(TestCase):
    def setUp(self):
        self.agent_user = User.objects.create_user(username='agent', password='password123')
        self.admin_user = User.objects.create_superuser(username='admin', password='password123')

    def test_unauthenticated_redirect(self):
        # Root redirects unauthenticated users
        response = self.client.get('/')
        self.assertRedirects(response, reverse('login'))

        # Direct view access redirects unauthenticated users
        response = self.client.get(reverse('people:agent_dashboard'))
        self.assertRedirects(response, '/accounts/login/?next=/people/dashboard/')

        response = self.client.get(reverse('people:admin_dashboard'))
        self.assertRedirects(response, '/accounts/login/?next=/people/admin-dashboard/')

    def test_logout_redirect_and_subsequent_access_denied(self):
        # Login
        self.client.login(username='agent', password='password123')
        
        # Access agent dashboard succeeds
        response = self.client.get(reverse('people:agent_dashboard'))
        self.assertEqual(response.status_code, 200)

        # Logout redirects to login page
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'))

        # Cannot access dashboard anymore after logout
        response = self.client.get(reverse('people:agent_dashboard'))
        self.assertRedirects(response, '/accounts/login/?next=/people/dashboard/')

    def test_cache_control_headers_on_agent_dashboard(self):
        self.client.login(username='agent', password='password123')
        response = self.client.get(reverse('people:agent_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        cache_control = response.headers.get('Cache-Control', '')
        self.assertIn('max-age=0', cache_control)
        self.assertIn('no-cache', cache_control)
        self.assertIn('no-store', cache_control)
        self.assertIn('must-revalidate', cache_control)
        self.assertIn('private', cache_control)

    def test_cache_control_headers_on_admin_dashboard(self):
        self.client.login(username='admin', password='password123')
        response = self.client.get(reverse('people:admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        cache_control = response.headers.get('Cache-Control', '')
        self.assertIn('max-age=0', cache_control)
        self.assertIn('no-cache', cache_control)
        self.assertIn('no-store', cache_control)
        self.assertIn('must-revalidate', cache_control)
        self.assertIn('private', cache_control)

    def test_authenticated_user_login_redirect(self):
        # When an authenticated user visits the login page, they should be redirected.
        self.client.login(username='agent', password='password123')
        response = self.client.get(reverse('login'))
        
        # LOGIN_REDIRECT_URL is '/' which then redirects the agent to their dashboard.
        # So we expect a redirect to '/' (which redirects to people/dashboard/)
        self.assertRedirects(response, '/', target_status_code=302)

