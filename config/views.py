from django.views.generic import RedirectView
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

@method_decorator(never_cache, name='dispatch')
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
