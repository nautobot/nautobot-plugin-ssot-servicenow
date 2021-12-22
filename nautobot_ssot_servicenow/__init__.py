"""Plugin declaration for nautobot_ssot_servicenow."""

try:
    from importlib import metadata
except ImportError:
    # Running on pre-3.8 Python; use importlib-metadata package
    import importlib_metadata as metadata

__version__ = metadata.version(__name__)


from nautobot.extras.plugins import PluginConfig


class NautobotSSOTServiceNowConfig(PluginConfig):
    """Plugin configuration for the nautobot_ssot_servicenow plugin."""

    name = "nautobot_ssot_servicenow"
    verbose_name = "Nautobot SSoT ServiceNow"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot SSoT ServiceNow."
    base_url = "ssot-servicenow"
    required_settings = []
    min_version = "1.2.0"
    max_version = "1.9999"
    default_settings = {}
    required_settings = []
    caching_config = {}

    config_view_name = "plugins:nautobot_ssot_servicenow:config"


config = NautobotSSOTServiceNowConfig  # pylint:disable=invalid-name
