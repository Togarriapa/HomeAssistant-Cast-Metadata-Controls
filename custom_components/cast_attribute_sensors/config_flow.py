"""Config flow entry point with the V8 physical-device options layer."""

from .config_flow_legacy import CastMetadataConfigFlow, ControllerOptionsFlow
from .v8_options import install_v8_options

# Patch the stable options class in place so existing non-grouping steps remain intact.
install_v8_options(ControllerOptionsFlow)

__all__ = ["CastMetadataConfigFlow"]
