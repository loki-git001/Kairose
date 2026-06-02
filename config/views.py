from django.views.generic import RedirectView
from django.urls import reverse

class HomeRouterView(RedirectView):
    """
    Smart Traffic Director for the root URL.
    Routes users based on their authentication status and roles.
    """
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return reverse('login')
        
        if self.request.user.is_staff or self.request.user.is_superuser:
            return reverse('people:admin_dashboard')
        
        return reverse('people:agent_dashboard')
