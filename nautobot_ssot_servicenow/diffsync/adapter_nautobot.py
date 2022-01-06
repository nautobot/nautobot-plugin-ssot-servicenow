"""DiffSync adapter class for Nautobot as source-of-truth."""

from diffsync import DiffSync
from diffsync.exceptions import ObjectNotFound

from nautobot.dcim.models import Device, DeviceType, Interface, Manufacturer, Region, Site
from nautobot.extras.models import Tag
from nautobot.utilities.choices import ColorChoices

from . import models


class NautobotDiffSync(DiffSync):
    """Nautobot adapter for DiffSync."""

    company = models.Company
    device = models.Device  # child of location
    interface = models.Interface  # child of device
    location = models.Location
    product_model = models.ProductModel  # child of company

    top_level = [
        "company",
        "location",
    ]

    def __init__(self, *args, job, sync, **kwargs):
        """Initialize the NautobotDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync

    def load_manufacturers(self):
        """Add Manufacturers and their descendant DeviceTypes as DiffSyncModel instances."""
        for mfr_record in Manufacturer.objects.all():
            mfr = self.company(diffsync=self, name=mfr_record.name, manufacturer=True, pk=mfr_record.pk)
            self.add(mfr)
            for dtype_record in DeviceType.objects.filter(manufacturer=mfr_record):
                dtype = self.product_model(
                    diffsync=self,
                    manufacturer_name=mfr.name,
                    model_name=dtype_record.model,
                    model_number=dtype_record.model,
                    pk=dtype_record.pk,
                )
                self.add(dtype)
                mfr.add_child(dtype)

        self.job.log_info(
            message=f"Loaded {len(self.get_all('company'))} manufacturer records and "
            f"{len(self.get_all('product_model'))} device-type records from Nautobot."
        )

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

    def load_sites(self, single_site=None):
        """Add Nautobot Site objects as DiffSync Location models."""
        for location in self.get_all(self.location):
            self.job.log_debug(f"Getting Sites associated with {location}")
            for site_record in Site.objects.filter(region__name=location.name):
                if single_site and site_record != single_site:
                    self.job.log_debug(f"Skipping site {site_record}")
                    continue
                # A Site and a Region may share the same name; if so they become part of the same Location record.
                try:
                    region_location = self.get(self.location, site_record.name)
                    region_location.site_pk = site_record.pk
                except ObjectNotFound:
                    site_location = self.location(
                        diffsync=self,
                        name=site_record.name,
                        latitude=site_record.latitude or "",
                        longitude=site_record.longitude or "",
                        site_pk=site_record.pk,
                    )
                    self.add(site_location)
                    if site_record.region:
                        if site_record.name != site_record.region.name:
                            region_location = self.get(self.location, site_record.region.name)
                            region_location.contained_locations.append(location)
                            location.parent_location_name = region_location.name

        self.job.log_info(
            message=f"Loaded {len(self.get_all('location'))} aggregated site and region records from Nautobot."
        )

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

    def load(self, region_filter=None, site_filter=None):
        """Load data from Nautobot."""
        self.load_manufacturers()
        # Import all Nautobot Region records as Locations
        if region_filter:
            location = self.location(diffsync=self, name=region_filter.name, region_pk=region_filter.pk)
            self.add(location)
            self.load_regions(parent_location=location)
        else:
            self.load_regions()

        # Import all Nautobot Site records as Locations
        self.load_sites(single_site=site_filter)

        for location in self.get_all(self.location):
            if location.site_pk is None:
                continue
            for device_record in Device.objects.filter(site__pk=location.site_pk):
                device = self.device(
                    diffsync=self,
                    name=device_record.name,
                    location_name=location.name,
                    asset_tag=device_record.asset_tag or "",
                    manufacturer_name=device_record.device_type.manufacturer.name,
                    model_name=device_record.device_type.model,
                    serial=device_record.serial,
                    pk=device_record.pk,
                )
                self.add(device)
                location.add_child(device)

                for interface_record in Interface.objects.filter(device=device_record):
                    self.load_interface(interface_record, device)

        self.job.log_info(
            message=f"Loaded {len(self.get_all('device'))} device records and "
            f"{len(self.get_all('interface'))} interface records from Nautobot."
        )

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
        for modelname in [
            "company",
            "device",
            "interface",
            "location",
            "product_model",
        ]:
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
        if modelname == "company":
            # Manufacturers cannot be tagged
            pass
        elif modelname == "device":
            Device.objects.get(pk=model_instance.pk).tags.add(tag)
        elif modelname == "interface":
            Interface.objects.get(pk=model_instance.pk).tags.add(tag)
        elif modelname == "location":
            # Regions cannot be tagged, but Sites can
            if model_instance.site_pk is not None:
                Site.objects.get(pk=model_instance.site_pk).tags.add(tag)
        elif modelname == "product_model":
            DeviceType.objects.get(pk=model_instance.pk).tags.add(tag)
