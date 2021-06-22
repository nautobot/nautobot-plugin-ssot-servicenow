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
        name = "ServiceNow"
        data_target = "ServiceNow"
        data_target_icon = static("nautobot_ssot_servicenow/ServiceNow_logo.svg")
        description = "Synchronize data from Nautobot into ServiceNow."

    @classmethod
    def data_mappings(cls):
        return (
            DataMapping("Region", reverse("dcim:region_list"), "Location", None),
            DataMapping("Site", reverse("dcim:site_list"), "Location", None),
            DataMapping("Device", reverse("dcim:device_list"), "IP Switch", None),
            DataMapping("Interface", reverse("dcim:interface_list"), "Interface", None),
        )

    @classmethod
    def config_information(cls):
        configs = settings.PLUGINS_CONFIG.get("nautobot_ssot_servicenow", {})
        return {
            "ServiceNow instance": configs.get("instance"),
            "Username": configs.get("username"),
            # Password is intentionally omitted!
            "Application prefix": configs.get("app_prefix"),
        }

    def sync_data(self):
        """Sync a slew of Nautobot data into ServiceNow."""
        configs = settings.PLUGINS_CONFIG.get("nautobot_ssot_servicenow", {})
        self.snc = ServiceNowClient(
            instance=configs.get("instance"),
            username=configs.get("username"),
            password=configs.get("password"),
            app_prefix=configs.get("app_prefix"),
            worker=self,
        )
        self.log_info(message="Loading current data from ServiceNow...")
        self.servicenow_diffsync = ServiceNowDiffSync(client=self.snc, job=self, sync=self.sync)
        self.servicenow_diffsync.load()

        self.log_info(message="Loading current data from Nautobot...")
        self.nautobot_diffsync = NautobotDiffSync(job=self, sync=self.sync)
        self.nautobot_diffsync.load()

        diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE
        if self.kwargs["log_unchanged"]:
            diffsync_flags |= DiffSyncFlags.LOG_UNCHANGED_RECORDS
        if not self.kwargs["delete_records"]:
            diffsync_flags |= DiffSyncFlags.SKIP_UNMATCHED_DST

        self.log_info(message="Calculating diffs...")
        diff = self.servicenow_diffsync.diff_from(self.nautobot_diffsync, flags=diffsync_flags)
        self.sync.diff = diff.dict()
        self.sync.save()

        if not self.kwargs["dry_run"]:
            self.log_info(message="Syncing from Nautobot to ServiceNow...")
            self.servicenow_diffsync.sync_from(self.nautobot_diffsync, flags=diffsync_flags)
            self.log_info(message="Sync complete")

    def lookup_object(self, model_name, unique_id):
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
