"""DiffSyncModel subclasses for Nautobot-to-ServiceNow data sync."""
from typing import List, Optional
import uuid

from diffsync import DiffSyncModel
import pysnow


class ServiceNowCRUDMixin:
    """Mixin class for all ServiceNow models, to support CRUD operations based on mappings.yaml."""

    _sys_id_cache = {}
    """Dict of table -> column_name -> value -> sys_id."""

    def map_data_to_sn_record(self, data, mapping_entry, existing_record=None):
        """Map create/update data from DiffSync to a corresponding ServiceNow data record."""
        record = existing_record or {}
        for mapping in mapping_entry.get("mappings", []):
            if mapping["field"] not in data:
                continue
            value = data[mapping["field"]]
            if "column" in mapping:
                record[mapping["column"]] = value
            elif "reference" in mapping:
                tablename = mapping["reference"]["table"]
                sys_id = None
                if "column" not in mapping["reference"]:
                    raise NotImplementedError
                column_name = mapping["reference"]["column"]
                if value is not None:
                    # Look in the cache first
                    sys_id = self._sys_id_cache.get(tablename, {}).get(column_name, {}).get(value, None)
                    if not sys_id:
                        target = self.diffsync.client.get_by_query(tablename, {mapping["reference"]["column"]: value})
                        if target is None:
                            self.diffsync.job.log_warning(message=f"Unable to find reference target in {tablename}")
                        else:
                            sys_id = target["sys_id"]
                            self._sys_id_cache.setdefault(tablename, {}).setdefault(column_name, {})[value] = sys_id

                record[mapping["reference"]["key"]] = sys_id
            else:
                raise NotImplementedError

        self.diffsync.job.log_debug(f"Mapped data {data} to record {record}")
        return record

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a new instance, data-driven by mappings."""
        entry = None
        for item in diffsync.mapping_data:
            if item["modelname"] == cls.get_type():
                entry = item
                break

        if not entry:
            raise RuntimeError(f"Did not find a mapping entry for {cls.get_type()}!")

        model = super().create(diffsync, ids=ids, attrs=attrs)

        sn_resource = diffsync.client.resource(api_path=f"/table/{entry['table']}")
        sn_record = model.map_data_to_sn_record(data=dict(**ids, **attrs), mapping_entry=entry)
        sn_resource.create(payload=sn_record)

        return model

    def update(self, attrs):
        """Update an existing instance, data-driven by mappings."""
        entry = None
        for item in self.diffsync.mapping_data:
            if item["modelname"] == self.get_type():
                entry = item
                break

        if not entry:
            raise RuntimeError("Did not find a mapping entry for {self.get_type()}!")

        sn_resource = self.diffsync.client.resource(api_path=f"/table/{entry['table']}")
        query = self.map_data_to_sn_record(data=self.get_identifiers(), mapping_entry=entry)
        try:
            record = sn_resource.get(query=query).one()
        except pysnow.exceptions.MultipleResults:
            self.diffsync.job.log_failure(
                message=f"Unsure which record to update, as query {query} matched more than one item in table {entry['table']}"
            )
            return None

        super().update(attrs)

        sn_record = self.map_data_to_sn_record(data=attrs, mapping_entry=entry, existing_record=record)
        sn_resource.update(query=query, payload=sn_record)

        return self

    # TODO delete() method


class Location(ServiceNowCRUDMixin, DiffSyncModel):
    """ServiceNow Location model."""

    _modelname = "location"
    _identifiers = ("name",)
    _attributes = ("parent_location_name",)
    _children = {
        "device": "devices",
    }

    name: str

    parent_location_name: Optional[str]
    contained_locations: List["Location"] = list()

    devices: List["Device"] = list()

    sys_id: Optional[str] = None
    region_pk: Optional[uuid.UUID] = None
    site_pk: Optional[uuid.UUID] = None


class Device(ServiceNowCRUDMixin, DiffSyncModel):
    """ServiceNow Device model."""

    _modelname = "device"
    _identifiers = ("name",)
    # For now we do not store more of the device fields in ServiceNow:
    # platform, model, role, vendor
    # ...as we would need to sync these data models to ServiceNow as well, and we don't do that yet.
    _attributes = ("location_name",)
    _children = {
        "interface": "interfaces",
    }

    name: str

    location_name: Optional[str]
    model: Optional[str]
    platform: Optional[str]
    role: Optional[str]
    vendor: Optional[str]

    interfaces: List["Interface"] = list()

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None


class Interface(ServiceNowCRUDMixin, DiffSyncModel):
    """ServiceNow Interface model."""

    _modelname = "interface"
    _identifiers = (
        "device_name",
        "name",
    )
    _shortname = ("name",)
    # ServiceNow currently stores very little data about interfaces that we are interested in
    _attributes = ()

    _children = {"ip_address": "ip_addresses"}

    name: str
    device_name: str

    access_vlan: Optional[int]
    active: Optional[bool]
    allowed_vlans: List[str] = list()
    description: Optional[str]
    is_virtual: Optional[bool]
    is_lag: Optional[bool]
    is_lag_member: Optional[bool]
    lag_members: List[str] = list()
    mode: Optional[str]  # TRUNK, ACCESS, L3, NONE
    mtu: Optional[int]
    parent: Optional[str]
    speed: Optional[int]
    switchport_mode: Optional[str]
    type: Optional[str]

    ip_addresses: List["IPAddress"] = list()

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None


class IPAddress(ServiceNowCRUDMixin, DiffSyncModel):
    """An IPv4 or IPv6 address."""

    _modelname = "ip_address"
    _identifiers = ("address",)
    _attributes = (
        "device_name",
        "interface_name",
    )

    address: str  # TODO: change to netaddr.IPAddress?

    device_name: Optional[str]
    interface_name: Optional[str]

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None


Location.update_forward_refs()
Device.update_forward_refs()
Interface.update_forward_refs()
