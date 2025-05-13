# --- START OF FILE Warehouse-Path-Finder-main/enums.py ---

from enum import Enum, auto

class InteractionMode(Enum):
    """Defines the possible interaction modes for the PdfViewer."""
    IDLE = auto()
    SET_SCALE_START = auto()
    SET_SCALE_END = auto()
    DRAW_OBSTACLE = auto()
    DEFINE_STAGING_AREA = auto()
    SET_START_POINT = auto()
    SET_END_POINT = auto()
    DEFINE_AISLE_LINE_START = auto()
    DEFINE_AISLE_LINE_END = auto()
    DEFINE_STAGING_LINE_START = auto()
    DEFINE_STAGING_LINE_END = auto()
    EDIT = auto()
    PANNING = auto()

class PointType(Enum):
    """Defines the types of points that can be added."""
    PICK_AISLE = "Pick Aisle"
    STAGING_LOCATION = "Staging Location"

class AnimationMode(Enum):
    """Defines the animation visualization modes."""
    CARTS = "Carts"
    PATH_LINES = "Path Lines"

# --- END OF FILE Warehouse-Path-Finder-main/enums.py ---