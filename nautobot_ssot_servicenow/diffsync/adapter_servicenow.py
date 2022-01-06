"""DiffSync adapter for ServiceNow."""
from base64 import b64encode
import json
import os

from diffsync import DiffSync
from diffsync.enum import DiffSyncFlags
from diffsync.exceptions import ObjectAlreadyExists
from jinja2 import Environment, FileSystemLoader
import yaml

from . import models


class ServiceNowDiffSync(DiffSync):
    """DiffSync adapter using pysnow to communicate with a ServiceNow server."""

    company = models.Company
    device = models.Device  # child of location
    interface = models.Interface  # child of device
    location = models.Location
    product_model = models.ProductModel  # child of company

    top_level = [
        "company",
        "location",
    ]

    DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))

    def __init__(self, *args, client=None, job=None, sync=None, **kwargs):
        """Initialize the ServiceNowDiffSync adapter."""
        super().__init__(*args, **kwargs)
        self.client = client
        self.job = job
        self.sync = sync
        self.sys_ids = {}
        self.mapping_data = []

        # Since a device may contain dozens or hundreds of interfaces,
        # to improve performance when a device is created/deleted, we use ServiceNow's bulk/batch API to
        # create or delete all of these interfaces in a single API call.
        self.interfaces_to_create_per_device = {}
        self.interfaces_to_delete_per_device = {}

    def load(self):
        """Load data via pysnow."""
        self.mapping_data = self.load_yaml_datafile("mappings.yaml")

        for entry in self.mapping_data:
            self.load_table(**entry)

    @classmethod
    def load_yaml_datafile(cls, filename, config=None):
        """Get the contents of the given YAML data file.

        Args:
          filename (str): Filename within the 'data' directory.
          config (dict): Data for Jinja2 templating.
        """
        file_path = os.path.join(cls.DATA_DIR, filename)
        if not os.path.isfile(file_path):
            raise RuntimeError(f"No data file found at {file_path}")
        if not config:
            config = {}
        env = Environment(loader=FileSystemLoader(cls.DATA_DIR), autoescape=True)
        template = env.get_template(filename)
        populated = template.render(config)
        return yaml.safe_load(populated)

    def load_table(self, modelname, table, mappings, **kwargs):
        """Load data from the ServiceNow "table" into the DiffSync model.

        Args:
          modelname (str): DiffSync model class identifier, such as "location" or "device".
          table (str): ServiceNow table name, such as "cmdb_ci_ip_switch"
          mappings (list): List of dicts, each stating how to populate a field in the model.
          **kwargs: Optional arguments, all of which default to False if unset:

            - parent (dict): Dict of {"modelname": ..., "field": ...} used to link table records back to their parents
        """
        model_cls = getattr(self, modelname)
        self.job.log_debug(f"Loading table `{table}` into {modelname} instances...")

        if "parent" not in kwargs:
            # Load the entire table
            for record in self.client.all_table_entries(table):
                self.load_record(table, record, model_cls, mappings, **kwargs)
        else:
            # Load items per parent object that we know/care about
            # This is necessary because, for example, the cmdb_ci_network_adapter table contains network interfaces
            # for ALL types of devices (servers, switches, firewalls, etc.) but we only have switches as parent objects
            for parent in self.get_all(kwargs["parent"]["modelname"]):
                for record in self.client.all_table_entries(table, {kwargs["parent"]["column"]: parent.sys_id}):
                    self.load_record(table, record, model_cls, mappings, **kwargs)

        self.job.log_info(message=f"Loaded {len(self.get_all(modelname))} records from table `{table}`")

    def load_record(self, table, record, model_cls, mappings, **kwargs):
        """Helper method to load_table()."""
        self.sys_ids.setdefault(table, {})[record["sys_id"]] = record

        ids_attrs = self.map_record_to_attrs(record, mappings)
        model = model_cls(**ids_attrs)
        modelname = model.get_type()

        try:
            self.add(model)
        except ObjectAlreadyExists:
            # TODO: the baseline data in ServiceNow has a number of duplicate Location entries. For now, continue
            self.job.log_debug(f'Duplicate object encountered for {modelname} "{model.get_unique_id()}"')

        if "parent" in kwargs:
            parent_uid = getattr(model, kwargs["parent"]["field"])
            if parent_uid is None:
                self.job.log_warning(
                    message=f'Model {modelname} "{model.get_unique_id}" does not have a parent uid value '
                    f"in field {kwargs['parent']['field']}"
                )
            else:
                parent_model = self.get(kwargs["parent"]["modelname"], parent_uid)
                parent_model.add_child(model)

    def map_record_to_attrs(self, record, mappings):  # TODO pylint: disable=too-many-branches
        """Helper method to load_table()."""
        attrs = {"sys_id": record["sys_id"]}
        for mapping in mappings:
            value = None
            if "column" in mapping:
                value = record[mapping["column"]]
            elif "reference" in mapping:
                # Reference by sys_id to a field in a record in another table
                table = mapping["reference"]["table"]
                if "key" in mapping["reference"]:
                    key = mapping["reference"]["key"]
                    if key not in record:
                        self.job.log_warning(message=f"Key `{key}` is not present in record `{record}`")
                    else:
                        sys_id = record[key]
                else:
                    raise NotImplementedError

                if sys_id:
                    if sys_id not in self.sys_ids.get(table, {}):
                        referenced_record = self.client.get_by_sys_id(table, sys_id)
                        if referenced_record is None:
                            self.job.log_warning(
                                message=f"Record `{record.get('name', record)}` field `{mapping['field']}` "
                                f"references sys_id `{sys_id}`, but that was not found in table `{table}`"
                            )
                        else:
                            self.sys_ids.setdefault(table, {})[sys_id] = referenced_record

                    if sys_id in self.sys_ids.get(table, {}):
                        value = self.sys_ids[table][sys_id][mapping["reference"]["column"]]
            else:
                raise NotImplementedError

            attrs[mapping["field"]] = value

        return attrs

    def sync_complete(self, source, diff, flags=DiffSyncFlags.NONE, logger=None):
        """Callback after the `sync_from` operation has completed and updated this instance.

        Note that this callback is **only** triggered if the sync actually resulted in data changes.
        If there are no detected changes, this callback will **not** be called.
        """
        self.job.log_info(message="Beginning potential bulk creation of device interfaces")
        sn_resource = self.client.resource(api_path="/v1/batch")
        sn_mapping_entry = None
        for item in self.mapping_data:
            if item["modelname"] == "interface":
                sn_mapping_entry = item
                break

        assert sn_mapping_entry is not None

        for request_id, device_name in enumerate(self.interfaces_to_create_per_device.keys()):
            sn_data = {
                "batch_request_id": str(request_id),
                "rest_requests": [],
            }
            for interface_index, interface in enumerate(self.interfaces_to_create_per_device[device_name]):
                request_payload = interface.map_data_to_sn_record(
                    data=dict(**interface.get_identifiers(), **interface.get_attrs()),
                    mapping_entry=sn_mapping_entry,
                )
                request_data = {
                    "id": str(interface_index),
                    "exclude_response_headers": True,
                    "headers": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Accept", "value": "application/json"},
                    ],
                    "url": f"/api/now/table/{sn_mapping_entry['table']}",
                    "method": "POST",
                    "body": b64encode(json.dumps(request_payload).encode("utf-8")).decode("utf-8"),
                }
                sn_data["rest_requests"].append(request_data)

            if not sn_data["rest_requests"]:
                self.job.log_info(message=f"No interfaces to create for {device_name}, continuing")
                continue

            self.job.log_info(
                message=f"Sending bulk API request to ServiceNow:\n```\n{json.dumps(sn_data, indent=4)}\n```\n"
            )

            sn_response = sn_resource.request(
                "POST",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                data=json.dumps(sn_data),
            )

            self.job.log_info(
                message=f"ServiceNow response: {sn_response._response.status_code} "
                f"\n```\n{sn_response._response.json()}\n```\n"
            )

        for device, interfaces in self.interfaces_to_delete_per_device.items():
            # TODO need delete implementation
            pass

        source.tag_involved_objects(target=self)
