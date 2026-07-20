"""Config flow entry point with the V8 physical-device options layer."""

from .config_flow_legacy import CastMetadataConfigFlow, ControllerOptionsFlow
from .v8_options import install_v8_options
from .v83_options import install_v83_options
from .v840_options import install_v840_options

# Patch the stable options class in release order so existing deep links and stored
# configuration remain compatible while the newest behavior wins conflicts.
install_v8_options(ControllerOptionsFlow)
install_v83_options(ControllerOptionsFlow)
install_v840_options(ControllerOptionsFlow)

__all__ = ["CastMetadataConfigFlow"]
