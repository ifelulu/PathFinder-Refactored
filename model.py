# --- START OF FILE Warehouse-Path-Finder-main/model.py ---

import numpy as np
from PySide6.QtCore import QObject, Signal, QFileInfo, QRectF, QPointF
from PySide6.QtGui import QPolygonF # <<< QPolygonF from QtGui
# QPolygonF was previously imported from QtGui, now from QtCore.
# QPointF was previously implicitly used or assumed to be from QtCore.

from typing import Optional, List, Dict, Any # For type hints if used

class WarehouseModel(QObject):
    """
    Encapsulates the data model for a warehouse project.
    Manages state related to the layout, definitions, and settings.
    Emits signals when data changes.
    """
    # --- Signals for data changes ---
    pdf_path_changed = Signal(str) # new_pdf_path or empty string
    pdf_bounds_set = Signal(QRectF) # bounds of the loaded PDF
    scale_changed = Signal(float, str, str) # pixels_per_unit, calibration_unit, display_unit
    layout_changed = Signal() # Obstacles, staging areas, OR pathfinding bounds changed
    points_changed = Signal() # Pick aisles or staging locations added/removed/moved
    grid_parameters_changed = Signal() # Resolution or staging penalty changed
    project_loaded = Signal() # Emitted after a project is successfully loaded
    model_reset = Signal() # Emitted when the model is cleared (e.g., new PDF/Project)
    grid_invalidated = Signal() # Emitted when grid/paths need recalculation
    cart_dimensions_changed = Signal(float, float) # width, length
    # Signal to specifically indicate data is ready for saving
    save_state_changed = Signal(bool) # True if saveable, False otherwise

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clear_data()

    def _clear_data(self):
        """Resets all model data to default values."""
        print("[Model] Clearing data")
        self._current_project_path: str | None = None
        self._current_pdf_path: str | None = None
        self._pdf_bounds: QRectF | None = None # Store PDF bounds
        self._scale_pixels_per_unit: float | None = None
        self._calibration_unit: str | None = None # Unit used during scale setting
        self._display_unit: str = "meters"       # Default unit FOR DISPLAY

        self._grid_resolution_factor: float = 2.0
        self._staging_area_penalty: float = 10.0
        self._animation_cart_width: float = 2.625 # Default width in project units
        self._animation_cart_length: float = 5.458 # Default length in project units

        self._obstacles: list[QPolygonF] = []          # Polygons defining impassable areas
        self._staging_areas: list[QPolygonF] = []      # Polygons defining penalty areas
        self._user_pathfinding_bounds: QPolygonF | None = None # Polygons defining pathfinding bounds
        self._pick_aisles: dict[str, QPointF] = {}      # {name: QPointF} Start points
        self._staging_locations: dict[str, QPointF] = {} # {name: QPointF} End points

        # --- Derived Data (Managed internally or by services) ---
        self._pathfinding_grid: np.ndarray | None = None
        self._grid_origin_pdf: QPointF | None = None
        self._distance_maps: dict[str, np.ndarray] = {} # {start_name: distance_grid}
        self._path_maps: dict[str, np.ndarray] = {}     # {start_name: predecessor_grid}
        self._grid_is_valid = False # Flag indicating if grid/paths are up-to-date

        print("[Model] Data cleared")
        self.model_reset.emit()
        self.save_state_changed.emit(False) # Cannot save initially

    def reset(self):
        """Public method to clear the model."""
        self._clear_data()

    # --- Getters ---
    @property
    def current_project_path(self) -> str | None: return self._current_project_path
    @property
    def current_pdf_path(self) -> str | None: return self._current_pdf_path
    @property
    def pdf_base_name(self) -> str | None:
        return QFileInfo(self._current_pdf_path).fileName() if self._current_pdf_path else None
    @property
    def pdf_bounds(self) -> QRectF | None: return self._pdf_bounds
    @property
    def scale_pixels_per_unit(self) -> float | None: return self._scale_pixels_per_unit
    @property
    def calibration_unit(self) -> str | None: return self._calibration_unit
    @property
    def display_unit(self) -> str: return self._display_unit
    @property
    def grid_resolution_factor(self) -> float: return self._grid_resolution_factor
    @property
    def staging_area_penalty(self) -> float: return self._staging_area_penalty
    @property
    def animation_cart_width(self) -> float: return self._animation_cart_width
    @property
    def animation_cart_length(self) -> float: return self._animation_cart_length
    @property
    def obstacles(self) -> list[QPolygonF]: return self._obstacles[:] # Return copy
    @property
    def staging_areas(self) -> list[QPolygonF]: return self._staging_areas[:] # Return copy
    @property
    def pick_aisles(self) -> dict[str, QPointF]: return self._pick_aisles.copy()
    @property
    def staging_locations(self) -> dict[str, QPointF]: return self._staging_locations.copy()
    @property
    def pathfinding_grid(self) -> np.ndarray | None: return self._pathfinding_grid # Allow direct access (or add setter)
    @property
    def grid_origin_pdf(self) -> QPointF | None: # Public getter property
        return self._grid_origin_pdf    
    @property
    def distance_maps(self) -> dict[str, np.ndarray]: return self._distance_maps # Allow direct access
    @property
    def path_maps(self) -> dict[str, np.ndarray]: return self._path_maps # Allow direct access
    @property
    def grid_is_valid(self) -> bool: # Physical grid and its origin are ready
        return self._pathfinding_grid is not None and self._grid_origin_pdf is not None
    @property
    def path_data_is_valid(self) -> bool: # Precomputed paths are ready
        return self.grid_is_valid and (not self.has_pick_aisles or bool(self._path_maps))    
    @property
    def is_scale_set(self) -> bool: return self._scale_pixels_per_unit is not None
    @property
    def has_pick_aisles(self) -> bool: return bool(self._pick_aisles)
    @property
    def has_staging_locations(self) -> bool: return bool(self._staging_locations)
    @property
    def can_calculate_paths(self) -> bool:
        return self.is_scale_set and self.has_pick_aisles and self.has_staging_locations
    @property
    def can_precompute(self) -> bool:
        # Can precompute if scale is set, PDF is loaded, and pick aisles exist.
        # The grid itself will be generated by the precomputation process if needed.
        return self.is_scale_set and self.has_pick_aisles and self._current_pdf_path is not None
    @property
    def can_analyze_or_animate(self) -> bool:
        # Needs everything: calculable paths (which implies points), and valid path data (precomputed maps)
        return self.can_calculate_paths and self.path_data_is_valid # Use new property
    @property
    def is_saveable(self) -> bool:
        # Project is saveable if a PDF is loaded (minimum requirement)
        return self._current_pdf_path is not None
    @property
    def user_pathfinding_bounds(self) -> QPolygonF | None: return self._user_pathfinding_bounds

    # --- Setters and Modifiers ---

    def set_current_project_path(self, path: str | None):
        if self._current_project_path != path:
            self._current_project_path = path
            self.save_state_changed.emit(self.is_saveable) # Update save state based on PDF presence

    def set_pdf_path_and_bounds(self, path: str | None, bounds: QRectF | None):
        """Sets the PDF path and its bounds, clearing old data."""
        if self._current_pdf_path != path:
            self._clear_data() # Clear everything when PDF changes
            self._current_pdf_path = path
            self._pdf_bounds = bounds
            print(f"[Model] PDF path set to: {path}")
            print(f"[Model] PDF bounds set to: {bounds}")
            self.pdf_path_changed.emit(path if path else "")
            if bounds:
                self.pdf_bounds_set.emit(bounds)
            self.save_state_changed.emit(self.is_saveable)

    def set_scale(self, pixels_per_unit: float, calibration_unit: str):
        changed = self._scale_pixels_per_unit != pixels_per_unit or self._calibration_unit != calibration_unit
        if changed:
            print(f"[Model] Scale set: {pixels_per_unit:.2f} px/{calibration_unit}")
            self._scale_pixels_per_unit = pixels_per_unit
            self._calibration_unit = calibration_unit
            self._invalidate_grid()
            self.scale_changed.emit(self._scale_pixels_per_unit, self._calibration_unit, self._display_unit)
            self.save_state_changed.emit(self.is_saveable) # Scale setting makes it saveable

    def set_display_unit(self, unit: str):
        if unit in ["meters", "feet"] and self._display_unit != unit:
            print(f"[Model] Display unit set to: {unit}")
            self._display_unit = unit
            if self._scale_pixels_per_unit is not None:
                 self.scale_changed.emit(self._scale_pixels_per_unit, self._calibration_unit, self._display_unit)

    def set_grid_resolution_factor(self, factor: float):
        if self._grid_resolution_factor != factor:
            print(f"[Model] Grid resolution factor set to: {factor}")
            self._grid_resolution_factor = factor
            self._invalidate_grid()
            self.grid_parameters_changed.emit()
            self.save_state_changed.emit(self.is_saveable) # Change makes it saveable

    def set_staging_area_penalty(self, penalty: float):
        if self._staging_area_penalty != penalty:
            print(f"[Model] Staging area penalty set to: {penalty}")
            self._staging_area_penalty = penalty
            self._invalidate_grid()
            self.grid_parameters_changed.emit()
            self.save_state_changed.emit(self.is_saveable)

    def set_animation_cart_dimensions(self, width: float, length: float):
        changed = False
        if self._animation_cart_width != width:
            self._animation_cart_width = width
            changed = True
        if self._animation_cart_length != length:
            self._animation_cart_length = length
            changed = True
        if changed:
            print(f"[Model] Cart dimensions set: W={width}, L={length}")
            self.cart_dimensions_changed.emit(width, length)
            self.save_state_changed.emit(self.is_saveable)

    def add_obstacle(self, polygon: QPolygonF):
        print("[Model] Adding obstacle")
        self._obstacles.append(polygon)
        self._invalidate_grid()
        self.layout_changed.emit()
        self.save_state_changed.emit(self.is_saveable)

    def set_user_pathfinding_bounds(self, polygon: QPolygonF | None):
        """Sets or clears the user-defined pathfinding bounds."""
        # Convert None to empty polygon for consistent type checking later if needed
        new_bounds = polygon if polygon is not None else QPolygonF()
        current_bounds = self._user_pathfinding_bounds if self._user_pathfinding_bounds is not None else QPolygonF()

        if new_bounds != current_bounds: # Compare polygons
            print(f"[Model] Setting user pathfinding bounds.")
            self._user_pathfinding_bounds = polygon # Store None or the actual polygon
            self._invalidate_grid() # Grid needs recalculation based on new bounds
            self.layout_changed.emit() # Signal that layout (including bounds) changed
            self.save_state_changed.emit(self.is_saveable)

    def add_obstacle(self, polygon: QPolygonF):
        print("[Model] Adding obstacle")
        self._obstacles.append(polygon)
        self._invalidate_grid()
        self.layout_changed.emit()
        self.save_state_changed.emit(self.is_saveable)       

    def remove_obstacle_by_ref(self, polygon_ref: QPolygonF):
        """Removes an obstacle using its reference."""
        if polygon_ref in self._obstacles:
            self._obstacles.remove(polygon_ref)
            print("[Model] Removed obstacle")
            self._invalidate_grid()
            self.layout_changed.emit()
            self.save_state_changed.emit(self.is_saveable)
        else:
            print("[Model] Warning: Tried to remove obstacle not found in list.")

    def update_obstacle(self, old_polygon_ref: QPolygonF, new_polygon: QPolygonF):
        """Updates an existing obstacle using its old reference."""
        try:
            # Find by reference (identity) rather than value equality
            for i, existing_poly in enumerate(self._obstacles):
                 if existing_poly is old_polygon_ref:
                     self._obstacles[i] = new_polygon
                     print("[Model] Updated obstacle")
                     self._invalidate_grid()
                     self.layout_changed.emit()
                     self.save_state_changed.emit(self.is_saveable)
                     return
            print("[Model] Warning: Tried to update obstacle not found by reference.")
        except Exception as e: # Catch potential issues during update
             print(f"[Model] Error updating obstacle: {e}")

    def add_staging_area(self, polygon: QPolygonF):
        print("[Model] Adding staging area")
        self._staging_areas.append(polygon)
        self._invalidate_grid()
        self.layout_changed.emit()
        self.save_state_changed.emit(self.is_saveable)

    def remove_staging_area_by_ref(self, polygon_ref: QPolygonF):
        """Removes a staging area using its reference."""
        if polygon_ref in self._staging_areas:
            self._staging_areas.remove(polygon_ref)
            print("[Model] Removed staging area")
            self._invalidate_grid()
            self.layout_changed.emit()
            self.save_state_changed.emit(self.is_saveable)
        else:
            print("[Model] Warning: Tried to remove staging area not found in list.")

    def update_staging_area(self, old_polygon_ref: QPolygonF, new_polygon: QPolygonF):
        """Updates an existing staging area using its old reference."""
        try:
            for i, existing_poly in enumerate(self._staging_areas):
                 if existing_poly is old_polygon_ref:
                     self._staging_areas[i] = new_polygon
                     print("[Model] Updated staging area")
                     self._invalidate_grid()
                     self.layout_changed.emit()
                     self.save_state_changed.emit(self.is_saveable)
                     return
            print("[Model] Warning: Tried to update staging area not found by reference.")
        except Exception as e:
             print(f"[Model] Error updating staging area: {e}")

    def add_pick_aisle(self, name: str, pos: QPointF) -> bool:
        if name in self._pick_aisles:
            print(f"[Model] Warning: Pick Aisle '{name}' already exists.")
            return False
        print(f"[Model] Adding pick aisle: {name} at {pos}")
        self._pick_aisles[name] = pos
        self._invalidate_grid()
        self.points_changed.emit()
        self.save_state_changed.emit(self.is_saveable)
        return True

    def remove_pick_aisle(self, name: str) -> bool:
        if name in self._pick_aisles:
            print(f"[Model] Removing pick aisle: {name}")
            del self._pick_aisles[name]
            # Remove associated paths if they exist
            if name in self._distance_maps: del self._distance_maps[name]
            if name in self._path_maps: del self._path_maps[name]
            # Grid remains valid unless ALL start points are gone AND it was valid before
            if not self._pick_aisles and self._grid_is_valid:
                 self._invalidate_grid() # No start points left, invalidate
            elif not self._path_maps and self._grid_is_valid: # No paths left, invalidate
                 self._invalidate_grid()
            self.points_changed.emit()
            self.save_state_changed.emit(self.is_saveable)
            return True
        return False

    def update_pick_aisle(self, name: str, new_pos: QPointF) -> bool:
         if name in self._pick_aisles:
             if self._pick_aisles[name] != new_pos:
                 print(f"[Model] Updating pick aisle: {name} to {new_pos}")
                 self._pick_aisles[name] = new_pos
                 self._invalidate_grid()
                 self.points_changed.emit()
                 self.save_state_changed.emit(self.is_saveable)
             return True
         return False

    def add_staging_location(self, name: str, pos: QPointF) -> bool:
        if name in self._staging_locations:
            print(f"[Model] Warning: Staging Location '{name}' already exists.")
            return False
        print(f"[Model] Adding staging location: {name} at {pos}")
        self._staging_locations[name] = pos
        self.points_changed.emit()
        self.save_state_changed.emit(self.is_saveable)
        return True

    def remove_staging_location(self, name: str) -> bool:
        if name in self._staging_locations:
            print(f"[Model] Removing staging location: {name}")
            del self._staging_locations[name]
            self.points_changed.emit()
            self.save_state_changed.emit(self.is_saveable)
            return True
        return False

    def update_staging_location(self, name: str, new_pos: QPointF) -> bool:
        if name in self._staging_locations:
            if self._staging_locations[name] != new_pos:
                 print(f"[Model] Updating staging location: {name} to {new_pos}")
                 self._staging_locations[name] = new_pos
                 self.points_changed.emit()
                 self.save_state_changed.emit(self.is_saveable)
            return True
        return False

    # --- Derived Data Management ---
    def _invalidate_grid(self):
        """Marks the grid and path maps as invalid."""
        if self._grid_is_valid:
            print("[Model] Invalidating pathfinding grid and maps.")
            self._pathfinding_grid = None
            self._distance_maps.clear()
            self._path_maps.clear()
            self._grid_is_valid = False
            self.grid_invalidated.emit()

    def set_pathfinding_data(self, grid: np.ndarray | None,
                             grid_origin_pdf: QPointF | None,
                             distance_maps: dict[str, np.ndarray] | None = None,
                             path_maps: dict[str, np.ndarray] | None = None):
        """Updates the derived pathfinding data. Should be called by PathfindingService."""
        print(f"[Model] Updating pathfinding data (grid, origin, maps). Grid is None: {grid is None}, Origin is None: {grid_origin_pdf is None}")
        self._pathfinding_grid = grid
        self._grid_origin_pdf = grid_origin_pdf
        self._distance_maps = distance_maps if distance_maps is not None else {}
        self._path_maps = path_maps if path_maps is not None else {}
        
        # _grid_is_valid is now determined by the property based on _pathfinding_grid and _grid_origin_pdf
        # We don't set it directly here anymore.
        # The act of setting these will make the grid_is_valid property evaluate correctly.
        
        print(f"[Model] After update: grid_is_valid={self.grid_is_valid}, path_data_is_valid={self.path_data_is_valid}")
        self.grid_parameters_changed.emit() # Still useful to trigger UI updates like granularity label

    def mark_project_loaded(self):
        """Signals that project loading is complete."""
        self._invalidate_grid() # Grid needs recomputing after loading layout changes
        self.project_loaded.emit()
        self.save_state_changed.emit(self.is_saveable) # Update save state

# --- END OF FILE Warehouse-Path-Finder-main/model.py ---