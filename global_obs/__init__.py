import sys, os
sys.path.insert(0, os.path.dirname(__file__))

__all__ = [
    "update_picks",
    "mag_types",
    "generate_mag_model",
    "use_mag_models",
    # "update_AOI",
    "fusion",
    # "map_global",
]

from . import *