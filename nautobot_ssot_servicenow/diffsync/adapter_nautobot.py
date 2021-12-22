"""DiffSync adapter class for Nautobot as source-of-truth."""

from diffsync import DiffSync
from diffsync.exceptions import ObjectNotFound

from nautobot.dcim.models import Device, Interface, Region, Site
from nautobot.extras.models import Tag
from nautobot.utilities.choices import ColorChoices

from . import models


class NautobotDiffSync(DiffSync):
    """Nautobot adapter for DiffSync."""

    location = models.Location
    device = models.Device
    interface = models.Interface

    top_level = [
        "location",
    ]

    def __init__(self, *args, job, sync, **kwargs):
        """Initialize the NautobotDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync

    def load_regions(self, parent_location=None):
        """Recursively add Nautobot Region objects as DiffSync Location models."""
        parent_pk = parent_location.region_pk if parent_location else None
        for region_record in Region.objects.filter(parent=parent_pk):
            location = self.location(diffsync=self, name=region_record.name, region_pk=region_record.pk)
            if parent_location:
                parent_location.contained_locations.append(location)
                location.parent_location_name = parent_location.name
            self.add(location)
            self.load_regions(parent_location=location)

    def load_sites(self):
        """Add Nautobot Site objects as DiffSync Location models."""
        for site_record in Site.objects.all():
            # A Site and a Region may share the same name; if so they become part of the same Location record.
            try:
                location = self.get(self.location, site_record.name)
                location.site_pk = site_record.pk
            except ObjectNotFound:
                location = self.location(diffsync=self, name=site_record.name, site_pk=site_record.pk)
                self.add(location)
            if site_record.region:
                if location.name != site_record.region.name:
                    region_location = self.get(self.location, site_record.region.name)
                    region_location.contained_locations.append(location)
                    location.parent_location_name = region_location.name

    def load_interface(self, interface_record, device_model):
        """Import a single Nautobot Interface object as a DiffSync Interface model."""
        interface = self.interface(
            diffsync=self,
            name=interface_record.name,
            device_name=device_model.name,
            description=interface_record.description,
            pk=interface_record.pk,
        )
        self.add(interface)
        device_model.add_child(interface)

    def load(self):
        """Load data from Nautobot."""
        # Import all Nautobot Region records as Locations
        self.load_regions(parent_location=None)

        # Import all Nautobot Site records as Locations
        self.load_sites()

        for location in self.get_all(self.location):
            if location.site_pk is None:
                continue
            for device_record in Device.objects.filter(site__pk=location.site_pk):
                device = self.device(
                    diffsync=self,
                    name=device_record.name,
                    platform=str(device_record.platform) if device_record.platform else None,
                    model=str(device_record.device_type),
                    role=str(device_record.device_role),
                    location_name=location.name,
                    vendor=str(device_record.device_type.manufacturer),
                    status=device_record.status,
                    pk=device_record.pk,
                )
                self.add(device)
                location.add_child(device)

                for interface_record in Interface.objects.filter(device=device_record):
                    self.load_interface(interface_record, device)

    def tag_involved_objects(self, target):
        """Tag all objects that were successfully synced to the target."""
        # Delete any existing "ssot-synced-to-servicenow" tag so as to untag existing objects
        if Tag.objects.filter(slug="ssot-synced-to-servicenow").exists():
            Tag.objects.get(slug="ssot-synced-to-servicenow").delete()
        # Ensure that "ssot-synced-to-servicenow" tag is created
        tag = Tag.objects.create(
            slug="ssot-synced-to-servicenow",
            name="SSoT Synced to ServiceNow",
            description="Object synced successfully from Nautobot to ServiceNow",
            color=ColorChoices.COLOR_LIGHT_GREEN,
        )
        for modelname in ["location", "device", "interface"]:
            for local_instance in self.get_all(modelname):
                unique_id = local_instance.get_unique_id()
                # Verify that the object now has a counterpart in the target DiffSync
                try:
                    target.get(modelname, unique_id)
                except ObjectNotFound:
                    continue

                self.tag_object(modelname, unique_id, tag)

    def tag_object(self, modelname, unique_id, tag):
        """Apply the given tag to the identified object."""
        model_instance = self.get(modelname, unique_id)
        if modelname == "location":
            # Unfortunately Regions cannot be tagged.
            if model_instance.site_pk is not None:
                Site.objects.get(pk=model_instance.site_pk).tags.add(tag)
        elif modelname == "device":
            Device.objects.get(pk=model_instance.pk).tags.add(tag)
        elif modelname == "interface":
            Interface.objects.get(pk=model_instance.pk).tags.add(tag)
