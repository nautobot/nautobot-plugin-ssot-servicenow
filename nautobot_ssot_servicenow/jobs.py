"""ServiceNow Data Target Job."""
from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse

from diffsync.enum import DiffSyncFlags

from nautobot.dcim.models import Device, Interface, Region, Site
from nautobot.extras.jobs import Job, BooleanVar

from nautobot_ssot.jobs.base import DataMapping, DataTarget

from .diffsync.adapter_nautobot import NautobotDiffSync
from .diffsync.adapter_servicenow import ServiceNowDiffSync
from .servicenow import ServiceNowClient


class ServiceNowDataTarget(DataTarget, Job):
    """Job syncing data from Nautobot to ServiceNow."""

    log_unchanged = BooleanVar(
        description="Create log entries even for unchanged objects",
        default=False,
    )

    delete_records = BooleanVar(
        description="Delete records from ServiceNow if not present in Nautobot",
        default=False,
    )

    class Meta:
        """Metadata about this Job."""
        name = "ServiceNow"
        data_target = "ServiceNow"
        data_target_icon = static("nautobot_ssot_servicenow/ServiceNow_logo.svg")
        description = "Synchronize data from Nautobot into ServiceNow."

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataTarget."""
        return (
            DataMapping("Region", reverse("dcim:region_list"), "Location", None),
            DataMapping("Site", reverse("dcim:site_list"), "Location", None),
            DataMapping("Device", reverse("dcim:device_list"), "IP Switch", None),
            DataMapping("Interface", reverse("dcim:interface_list"), "Interface", None),
        )

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataTarget."""
        configs = settings.PLUGINS_CONFIG.get("nautobot_ssot_servicenow", {})
        return {
            "ServiceNow instance": configs.get("instance"),
            "Username": configs.get("username"),
            # Password is intentionally omitted!
        }

    def sync_data(self):
        """Sync a slew of Nautobot data into ServiceNow."""
        configs = settings.PLUGINS_CONFIG.get("nautobot_ssot_servicenow", {})
        snc = ServiceNowClient(
            instance=configs.get("instance"),
            username=configs.get("username"),
            password=configs.get("password"),
            worker=self,
        )
        self.log_info(message="Loading current data from ServiceNow...")
        servicenow_diffsync = ServiceNowDiffSync(client=snc, job=self, sync=self.sync)
        servicenow_diffsync.load()

        self.log_info(message="Loading current data from Nautobot...")
        nautobot_diffsync = NautobotDiffSync(job=self, sync=self.sync)
        nautobot_diffsync.load()

        diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE
        if self.kwargs["log_unchanged"]:
            diffsync_flags |= DiffSyncFlags.LOG_UNCHANGED_RECORDS
        if not self.kwargs["delete_records"]:
            diffsync_flags |= DiffSyncFlags.SKIP_UNMATCHED_DST

        self.log_info(message="Calculating diffs...")
        diff = servicenow_diffsync.diff_from(nautobot_diffsync, flags=diffsync_flags)
        self.sync.diff = diff.dict()
        self.sync.save()

        if not self.kwargs["dry_run"]:
            self.log_info(message="Syncing from Nautobot to ServiceNow...")
            servicenow_diffsync.sync_from(nautobot_diffsync, flags=diffsync_flags)
            self.log_info(message="Sync complete")

    def lookup_object(self, model_name, unique_id):
        """Look up a Nautobot object based on the DiffSync model name and unique ID."""
        if model_name == "location":
            try:
                return (Region.objects.get(name=unique_id), None)
            except Region.DoesNotExist:
                pass
            try:
                return (Site.objects.get(name=unique_id), None)
            except Site.DoesNotExist:
                pass
        elif model_name == "device":
            try:
                return (Device.objects.get(name=unique_id), None)
            except Device.DoesNotExist:
                pass
        elif model_name == "interface":
            device_name, interface_name = unique_id.split("__")
            try:
                return (Interface.objects.get(device__name=device_name, name=interface_name), None)
            except Interface.DoesNotExist:
                pass
        return (None, None)


jobs = [ServiceNowDataTarget]
