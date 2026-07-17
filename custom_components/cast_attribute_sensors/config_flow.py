"""Config flow entry point with the V8 physical-device options layer."""

from .config_flow_legacy import CastMetadataConfigFlow, ControllerOptionsFlow
from .v8_options import install_v8_options

install_v8_options(ControllerOptionsFlow)

__all__ = ["CastMetadataConfigFlow"]
