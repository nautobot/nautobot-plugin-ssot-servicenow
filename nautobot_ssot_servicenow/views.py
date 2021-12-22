"""UI view classes and methods for nautobot-ssot-servicenow."""
from django.contrib import messages
from django.shortcuts import render
from django.views.generic import View

from nautobot.utilities.forms import restrict_form_fields

from .forms import SSOTServiceNowConfigForm
from .models import SSOTServiceNowConfig


class SSOTServiceNowConfigView(View):
    """Plugin-level configuration view for nautobot-ssot-servicenow."""

    def get(self, request):
        """Render the configuration page for this plugin."""
        instance = SSOTServiceNowConfig.load()
        form = SSOTServiceNowConfigForm(instance=instance)
        restrict_form_fields(form, request.user)

        return render(
            request,
            "nautobot_ssot_servicenow/config.html",
            {"form": form, "obj": instance, "editing": True},
        )

    def post(self, request):
        """Handle configuration changes for this plugin."""
        instance = SSOTServiceNowConfig.load()
        form = SSOTServiceNowConfigForm(instance=instance, data=request.POST)
        restrict_form_fields(form, request.user)

        if form.is_valid():
            form.save()

            messages.success(request, "Successfully updated configuration")

        return render(
            request,
            "nautobot_ssot_servicenow/config.html",
            {"form": form, "obj": instance, "editing": True},
        )
