"""DiffSyncModel subclasses for Nautobot-to-ServiceNow data sync."""
from typing import List, Optional
from django.conf import settings
from requests.api import delete
from nautobot.dcim.models import Device as NautobotDevice
from nautobot.dcim.models import Site
import uuid

from diffsync import DiffSyncModel
import nautobot_ssot_servicenow.diffsync.tonb.nbutils as tonb_nbutils

DEFAULT_DEVICE_ROLE = "leaf"
DEFAULT_DEVICE_ROLE_COLOR = "ff0000"
DEFAULT_DEVICE_STATUS = "Active"
DEFAULT_DEVICE_STATUS_COLOR = "ff0000"


class Location(DiffSyncModel):
    """ServiceNow Location model."""

    _modelname = "location"
    _identifiers = ("name",)
    _attributes = ("parent_location_name",)
    _children = {"device": "devices"}

    name: str
    parent_location_name: Optional[str]

    devices: List["Device"] = list()

    sys_id: Optional[str] = None
    region_pk: Optional[uuid.UUID] = None
    site_pk: Optional[uuid.UUID] = None

    @classmethod
    def create(cls, diffsync, ids, attrs):
        "Create Site in Nautobot."
        ## TODO: Figure out how Koch distinguishes between Sites and Regions
        site_obj = tonb_nbutils.create_site(site_name=ids["name"])

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete Site in Nautobot"""
        site = Site.objects.get(name=self.name)
        site.delete()
        super().delete()
        return self


class Device(DiffSyncModel):
    """ServiceNow Device model."""

    _modelname = "device"
    _identifiers = ("name",)
    # For now we do not store more of the device fields in ServiceNow:
    # platform, model, role, vendor
    # ...as we would need to sync these data models to ServiceNow as well, and we don't do that yet.
    _attributes = ("location_name", "model", "vendor")
    _children = {"interface": "interfaces"}

    name: str

    location_name: Optional[str]
    model: Optional[str]
    platform: Optional[str]
    role: Optional[str]
    vendor: Optional[str]

    interfaces: List["Interface"] = list()

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None

    @classmethod
    def create(cls, diffsync, ids, attrs):
        "Create Device in Nautobot under its parent site."
        ## TODO: Update creation of objects to take defined parameters.
        device_type_object = tonb_nbutils.create_device_type_object(
            device_type=attrs["model"], vendor_name=attrs["vendor"]
        )
        device_role_object = tonb_nbutils.create_device_role_object(
            role_name=DEFAULT_DEVICE_ROLE, role_color=DEFAULT_DEVICE_ROLE_COLOR
        )
        device_status_object = tonb_nbutils.create_device_status(DEFAULT_DEVICE_STATUS, DEFAULT_DEVICE_STATUS_COLOR)
        site_object = tonb_nbutils.create_site(attrs["location_name"])

        new_device = NautobotDevice(
            status=device_status_object,
            device_type=device_type_object,
            device_role=device_role_object,
            site=site_object,
            name=ids["name"],
        )

        new_device.validated_save()

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def delete(self) -> Optional["DiffSyncModel"]:
        """Delete device in Nautobot."""
        device = NautobotDevice.objects.get(name=self.name)
        device.delete()
        super().delete()
        return super().delete()


class Interface(DiffSyncModel):
    """ServiceNow Interface model."""

    _modelname = "interface"
    _identifiers = (
        "device_name",
        "name",
    )
    _shortname = ("name",)
    _attributes = ("ip_address",)
    _children = {}

    name: str
    device_name: str
    ip_address: Optional[str]

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None

    @classmethod
    def create(cls, diffsync, ids, attrs):
        "Create interface in Nautobot under its parent device."
        device = NautobotDevice.objects.get(name=ids["device_name"])
        device.interfaces.create(name=ids["name"])

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def delete(self) -> Optional["DiffSyncModel"]:
        device = NautobotDevice.objects.get(name=self.device_name)
        interface = device.interfaces.get(name=self.name)
        interface.delete()
        return super().delete()


#    access_vlan: Optional[int]
#    active: Optional[bool]
#    allowed_vlans: List[str] = list()
#    description: Optional[str]
#    is_virtual: Optional[bool]
#    is_lag: Optional[bool]
#    is_lag_member: Optional[bool]
#    lag_members: List[str] = list()
#    mode: Optional[str]  # TRUNK, ACCESS, L3, NONE
#    mtu: Optional[int]
#    parent: Optional[str]
#    speed: Optional[int]
#    switchport_mode: Optional[str]
#    type: Optional[str]
#    #    ip_addresses: List["IPAddress"] = list()
#    sys_id: Optional[str] = None
#    pk: Optional[uuid.UUID] = None


# class IPAddress(DiffSyncModel):
#     """An IPv4 or IPv6 address."""
#
#     _modelname = "ip_address"
#     _identifiers = ("address",)
#     _attributes = (
#         "device_name",
#         "interface_name",
#     )
#
#     address: str  # TODO: change to netaddr.IPAddress?
#     device_name: Optional[str]
#     interface_name: Optional[str]
#     sys_id: Optional[str] = None
#     pk: Optional[uuid.UUID] = None


Location.update_forward_refs()
Device.update_forward_refs()
Interface.update_forward_refs()
