"""Utility functions for Nautobot ORM."""
from nautobot.dcim.models import DeviceType, DeviceRole, Site, Manufacturer, Region
from nautobot.extras.models.statuses import Status
from nautobot.extras.models.tags import Tag
from nautobot.extras.models.customfields import CustomField
from django.contrib.contenttypes.models import ContentType
from django.utils.text import slugify


def create_site(site_name):
    """Creates a specified site in Nautobot.

    Args:
        site_name (str): Name of the site.
    """
    try:
        site_obj = Site.objects.get(name=site_name)
    except Site.DoesNotExist:
        site_obj = Site(name=site_name, slug=slugify(site_name), status=Status.objects.get(name="Staging"))
        site_obj.validated_save()
    return site_obj


def create_region(region_name):
    """Creates a specified region in Nautobot.

    Args:
        region_name (str): Name of the site.
    """
    try:
        region_obj = Region.objects.get(name=region_name)
    except Site.DoesNotExist:
        region_obj = Region(name=region_name, slug=slugify(region_name))
        region_obj.validated_save()
    return region_obj


def create_device_type_object(device_type, vendor_name):
    """Create a specified device type in Nautobot.
    Args:
        device_type (str): Device model gathered from DiffSync model.
    """
    try:
        device_type_obj = DeviceType.objects.get(model=device_type)
    except DeviceType.DoesNotExist:
        mf = create_manufacturer(vendor_name)
        device_type_obj = DeviceType(manufacturer=mf, model=device_type, slug=slugify(device_type))
        device_type_obj.validated_save()
    return device_type_obj


def create_manufacturer(vendor_name):
    """Create specified manufacturer in Nautobot."""
    try:
        mf = Manufacturer.objects.get(name=vendor_name)
    except Manufacturer.DoesNotExist:
        mf = Manufacturer(name=vendor_name, slug=slugify(vendor_name))
        mf.validated_save()
    return mf


def create_device_role_object(role_name, role_color):
    """Create specified device role in Nautobot.
    Args:
        role_name (str): Role name.
        role_color (str): Role color.
    """
    try:
        role_obj = DeviceRole.objects.get(name=role_name)
    except DeviceRole.DoesNotExist:
        role_obj = DeviceRole(name=role_name, slug=role_name.lower(), color=role_color)
        role_obj.validated_save()
    return role_obj


def create_device_status(device_status, device_status_color):
    """Verifies device status object exists in Nautobot. If not, creates specified device status.

    Args:
        device_status (str): Status name.
        device_status_color (str): Status color.
    """
    try:
        status_obj = Status.objects.get(name=device_status)
    except Status.DoesNotExist:
        dcim_device = ContentType.objects.get(app_label="dcim", model="device")
        status_obj = Status(
            name=device_status,
            slug=device_status.lower(),
            color=device_status_color,
            description="Status used for ServiceNow Sync.",
        )
        status_obj.validated_save()
        status_obj.content_types.set([dcim_device])
    return status_obj
