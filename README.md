# Nautobot Single Source of Truth -- ServiceNow Data Target

A plugin for [Nautobot](https://github.com/nautobot/nautobot), building atop the [nautobot-ssot](https://github.com/nautobot/nautobot-plugin-ssot/) plugin.

## Installation

The plugin is available as a Python package in PyPI and can be installed with `pip`:

```shell
pip install nautobot-ssot-servicenow
```

> The plugin is compatible with Nautobot 1.0.3 and higher

To ensure nautobot-ssot-servicenow is automatically re-installed during future upgrades, create a file named `local_requirements.txt` (if not already existing) in the Nautobot root directory (alongside `requirements.txt`) and list the `nautobot-ssot-servicenow` package:

```no-highlight
# echo nautobot-ssot-servicenow >> local_requirements.txt
```

Once installed, the plugin needs to be enabled in your `nautobot_configuration.py`

```python
# In your configuration.py
PLUGINS = ["nautobot_ssot_servicenow"]

PLUGINS_CONFIG = {
    "nautobot_ssot_servicenow": {
        "instance": "dev12345",
        "username": os.getenv("SERVICENOW_USERNAME"),
        "password": os.getenv("SERVICENOW_PASSWORD"),
    }
}
```

The plugin behavior can be controlled with the following list of settings:

- `instance`: The ServiceNow instance to point to (as in `<instance>.servicenow.com`)
- `username`: Username to access this instance
- `password`: Password to access this instance

## Questions

For any questions or comments, please check the [FAQ](FAQ.md) first and feel free to swing by the [Network to Code slack channel](https://networktocode.slack.com/) (channel #networktocode).
Sign up [here](http://slack.networktocode.com/)

## Screenshots

TODO
