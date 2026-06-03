from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

class FinanceAuthCacheTests(TestCase):
    def setUp(self):
        self.agent_user = User.objects.create_user(username='agent', password='password123')
        self.admin_user = User.objects.create_superuser(username='admin', password='password123')

    def test_unauthenticated_redirect_finance(self):
        # Access pending transactions when not logged in redirects to login
        response = self.client.get(reverse('finance:pending_transactions'))
        self.assertRedirects(response, '/accounts/login/?next=/finance/pending/')

        # Access upload statement when not logged in redirects to login
        response = self.client.get(reverse('finance:upload_statement'))
        self.assertRedirects(response, '/accounts/login/?next=/finance/upload/')

    def test_cache_control_headers_on_finance_views(self):
        # Pending transactions cache check
        self.client.login(username='agent', password='password123')
        response = self.client.get(reverse('finance:pending_transactions'))
        self.assertEqual(response.status_code, 200)
        
        cache_control = response.headers.get('Cache-Control', '')
        self.assertIn('max-age=0', cache_control)
        self.assertIn('no-cache', cache_control)
        self.assertIn('no-store', cache_control)
        self.assertIn('must-revalidate', cache_control)
        self.assertIn('private', cache_control)

        # Upload statement cache check (requires admin user)
        self.client.login(username='admin', password='password123')
        response = self.client.get(reverse('finance:upload_statement'))
        self.assertEqual(response.status_code, 200)

        cache_control = response.headers.get('Cache-Control', '')
        self.assertIn('max-age=0', cache_control)
        self.assertIn('no-cache', cache_control)
        self.assertIn('no-store', cache_control)
        self.assertIn('must-revalidate', cache_control)
        self.assertIn('private', cache_control)
