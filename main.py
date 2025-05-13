# --- START OF FILE Warehouse-Path-Finder-main/main.py ---

import sys
import math
import multiprocessing
import time # For timing operations if needed
from typing import List, Dict, Any, Optional, Tuple # Updated typing imports

# PySide6 imports
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QFileDialog, QMenuBar, QMessageBox,
    QInputDialog, QMenu, QHBoxLayout, QComboBox, QPushButton, QLabel, QSizePolicy, QDoubleSpinBox,
    QGraphicsItem, QGraphicsPolygonItem, QGraphicsEllipseItem
)
# QAction, QActionGroup, QColor, QFont, QTransform, QPolygonF are in QtGui
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QFont, QTransform,
    QPolygonF  # <<< QPolygonF MOVED BACK HERE
)
from PySide6.QtCore import (
    Qt, QFileInfo, Signal, Slot, QTimer, QRectF,
    QPointF, QLineF # QPolygonF removed from here
)

# Datetime imports
from datetime import datetime, timezone, timedelta # datetime class is now directly available

# PyMuPDF (fitz)
import fitz # For reading PDF metadata (bounds)

# Application-specific refactored modules
from model import WarehouseModel
from services import (ProjectService, PathfindingService, AnalysisService, AnimationService)
from pdf_viewer import PdfViewer, POINT_MARKER_RADIUS # Import constant from PdfViewer
from enums import InteractionMode, PointType, AnimationMode

# Dialogs
from line_definition_dialog import LineDefinitionDialog
from picklist_column_dialog import PicklistColumnDialog
from analysis_results_dialog import AnalysisResultsDialog
from animation_picklist_dialog import AnimationPicklistDialog
from animation_control_dialog import AnimationControlDialog, _get_cluster_from_name

import re


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Warehouse Path Finder")
        self.setGeometry(100, 100, 1200, 800)

        # --- Initialize Model and Services ---
        self.model = WarehouseModel(self)
        self.project_service = ProjectService(self)
        self.pathfinding_service = PathfindingService(self)
        self.analysis_service = AnalysisService(self)
        self.animation_service = AnimationService(self)

        # --- UI Elements ---
        self.pdf_viewer = PdfViewer()
        self.start_combo = QComboBox()
        self.end_combo = QComboBox()
        self.calculate_button = QPushButton("Calculate Path")
        self.resolution_spinbox = QDoubleSpinBox()
        self.penalty_spinbox = QDoubleSpinBox()
        self.granularity_label = QLabel("Path Detail Granularity: N/A")

        # Animation related
        self.animation_timer = QTimer(self)
        self.animation_control_dialog: Optional[AnimationControlDialog] = None
        self.current_animation_time_s: float = 0.0
        self.animation_speed_multiplier: float = 1.0
        self._animation_data_prepared: List[Dict[str, Any]] = []
        self._animation_earliest_dt_prepared: Optional[datetime] = None # Correct type hint
        self._animation_mode_current = AnimationMode.CARTS
        self._path_visibility_duration_s_current = 300
        self._keep_paths_visible_current = False
        self._animation_active_start_clusters: set[str] = set()
        self._animation_active_end_clusters: set[str] = set()
        self._animation_selected_date_filter: str = "All Dates" # Default
        self._filtered_min_time_s: Optional[float] = None
        self._filtered_max_time_s: Optional[float] = None
        self._filtered_earliest_dt: Optional[datetime] = None # Correct type hint

        # Cache for last analysis
        self._last_analysis_detailed_results: Optional[List[Dict[str, Any]]] = None
        self._last_analysis_warnings: Optional[List[str]] = None
        self._last_analysis_unit: Optional[str] = None
        self._last_analysis_input_filename: Optional[str] = None

        self._setup_ui()
        self._connect_signals()
        self._update_all_ui_states()

        self.statusBar().showMessage("Ready. Open a PDF or Project to start.")
        print("[MainWindow] Initialization complete.")

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5); main_layout.setSpacing(5)

        left_panel_widget = QWidget(); left_panel_widget.setFixedWidth(300)
        left_panel_layout = QVBoxLayout(left_panel_widget)
        left_panel_layout.setContentsMargins(0,0,0,0); left_panel_layout.setSpacing(10)

        path_controls_layout = QVBoxLayout()
        start_layout = QHBoxLayout(); start_layout.addWidget(QLabel("Pick Aisle (Start):")); start_layout.addWidget(self.start_combo)
        end_layout = QHBoxLayout(); end_layout.addWidget(QLabel("Staging Location (End):")); end_layout.addWidget(self.end_combo)
        path_controls_layout.addLayout(start_layout); path_controls_layout.addLayout(end_layout)

        resolution_layout = QVBoxLayout()
        resolution_layout.addWidget(QLabel("Grid Factor (Higher = Faster/Coarser):"))
        self.resolution_spinbox.setMinimum(1.0); self.resolution_spinbox.setMaximum(50.0)
        self.resolution_spinbox.setSingleStep(0.5); self.resolution_spinbox.setDecimals(1)
        resolution_layout.addWidget(self.resolution_spinbox)

        penalty_layout = QVBoxLayout()
        penalty_layout.addWidget(QLabel("Staging Area Penalty Cost:"))
        self.penalty_spinbox.setMinimum(1.0); self.penalty_spinbox.setMaximum(1000.0)
        self.penalty_spinbox.setSingleStep(1.0); self.penalty_spinbox.setDecimals(1)
        penalty_layout.addWidget(self.penalty_spinbox)

        left_panel_layout.addLayout(path_controls_layout)
        left_panel_layout.addWidget(self.calculate_button)
        left_panel_layout.addSpacing(15)
        left_panel_layout.addLayout(resolution_layout); left_panel_layout.addLayout(penalty_layout)
        left_panel_layout.addWidget(self.granularity_label); left_panel_layout.addStretch()

        main_layout.addWidget(left_panel_widget); main_layout.addWidget(self.pdf_viewer)
        main_layout.setStretchFactor(self.pdf_viewer, 1)
        self._create_menu_bar()
        self._update_spinbox_values_from_model()

    def _create_menu_bar(self):
        # (Menu creation code remains largely the same as provided in previous main.py,
        #  just ensure action names are consistent with self.action_name attributes used in _connect_signals)
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        self.open_pdf_action = QAction("&Open PDF...", self); file_menu.addAction(self.open_pdf_action)
        self.open_project_action = QAction("Open P&roject...", self); file_menu.addAction(self.open_project_action)
        file_menu.addSeparator()
        self.save_project_action = QAction("&Save Project", self); file_menu.addAction(self.save_project_action)
        self.save_as_project_action = QAction("Save Project &As...", self); file_menu.addAction(self.save_as_project_action)
        file_menu.addSeparator()
        exit_action = QAction("&Exit", self); exit_action.triggered.connect(self.close); file_menu.addAction(exit_action)

        tools_menu = menu_bar.addMenu("&Tools")
        self.set_scale_action = QAction("Set &Scale...", self); tools_menu.addAction(self.set_scale_action)
        units_menu = tools_menu.addMenu("&Units"); self.unit_group = QActionGroup(self); self.unit_group.setExclusive(True)
        self.meters_action = QAction("Meters", self, checkable=True); units_menu.addAction(self.meters_action); self.unit_group.addAction(self.meters_action)
        self.feet_action = QAction("Feet", self, checkable=True); units_menu.addAction(self.feet_action); self.unit_group.addAction(self.feet_action)
        tools_menu.addSeparator()
        self.draw_obstacle_action = QAction("Draw &Obstacle", self); tools_menu.addAction(self.draw_obstacle_action)
        self.define_staging_area_action = QAction("Define Staging &Area", self); tools_menu.addAction(self.define_staging_area_action)
        self.set_start_point_action = QAction("Set Pick &Aisle (Start)", self); tools_menu.addAction(self.set_start_point_action)
        self.set_end_point_action = QAction("Set Staging &Location (End)", self); tools_menu.addAction(self.set_end_point_action)
        tools_menu.addSeparator()
        self.define_aisle_line_action = QAction("Define Pick Aisle &Line...", self); tools_menu.addAction(self.define_aisle_line_action)
        self.define_staging_line_action = QAction("Define Staging Location Li&ne...", self); tools_menu.addAction(self.define_staging_line_action)
        tools_menu.addSeparator()
        self.edit_mode_action = QAction("&Select/Move/Delete Items", self, checkable=True); tools_menu.addAction(self.edit_mode_action)
        self.precompute_paths_action = QAction("&Precompute All Paths", self); tools_menu.addAction(self.precompute_paths_action)
        tools_menu.addSeparator()
        self.analyze_picklist_action = QAction("Analyze Picklis&t...", self); tools_menu.addAction(self.analyze_picklist_action)
        self.view_last_analysis_action = QAction("&View Last Analysis Results", self); tools_menu.addAction(self.view_last_analysis_action)
        self.export_last_analysis_action = QAction("&Export Last Analysis Results...", self); tools_menu.addAction(self.export_last_analysis_action)
        tools_menu.addSeparator()
        self.animate_picklist_action = QAction("Animate Pick&list...", self); tools_menu.addAction(self.animate_picklist_action)


    def _connect_signals(self):
        # Model Signals
        self.model.pdf_path_changed.connect(self._handle_pdf_loaded_in_model)
        self.model.scale_changed.connect(self._handle_scale_changed_in_model)
        self.model.layout_changed.connect(self._handle_layout_or_points_changed_in_model)
        self.model.points_changed.connect(self._handle_layout_or_points_changed_in_model)
        self.model.grid_parameters_changed.connect(self._handle_grid_params_changed_in_model)
        self.model.project_loaded.connect(self._handle_project_loaded_in_model)
        self.model.model_reset.connect(self._handle_model_reset)
        self.model.grid_invalidated.connect(self._handle_grid_invalidated_in_model)
        self.model.cart_dimensions_changed.connect(self._handle_cart_dimensions_changed_in_model)
        self.model.save_state_changed.connect(self._update_action_states)

        # PdfViewer Signals
        self.pdf_viewer.scale_line_drawn.connect(self._handle_scale_line_drawn)
        self.pdf_viewer.polygon_drawn.connect(self._handle_polygon_drawn)
        self.pdf_viewer.point_placement_requested.connect(self._handle_point_placement_requested)
        self.pdf_viewer.line_definition_requested.connect(self._handle_line_definition_requested)
        self.pdf_viewer.delete_items_requested.connect(self._handle_delete_items_requested)
        self.pdf_viewer.item_moved_in_edit.connect(self._handle_item_moved_in_edit)
        self.pdf_viewer.status_update.connect(self.statusBar().showMessage)

        # Service Signals
        self.project_service.project_operation_finished.connect(lambda msg: self.statusBar().showMessage(msg, 5000))
        self.project_service.project_load_failed.connect(lambda err: QMessageBox.critical(self, "Load Error", err))
        self.project_service.project_save_failed.connect(lambda err: QMessageBox.critical(self, "Save Error", err))
        self.pathfinding_service.grid_update_started.connect(lambda: self.statusBar().showMessage("Updating grid...", 0))
        self.pathfinding_service.grid_update_finished.connect(self._handle_grid_update_finished)
        self.pathfinding_service.precomputation_started.connect(lambda count: self.statusBar().showMessage(f"Precomputing paths for {count} points...", 0))
        self.pathfinding_service.precomputation_progress.connect(lambda done, name: self.statusBar().showMessage(f"Precomputed {done} paths (current: {name})...", 0))
        self.pathfinding_service.precomputation_finished.connect(self._handle_precomputation_finished)
        self.analysis_service.analysis_started.connect(lambda fp: self.statusBar().showMessage(f"Analyzing: {QFileInfo(fp).fileName()}...", 0))
        self.analysis_service.analysis_complete.connect(self._handle_analysis_complete)
        self.analysis_service.analysis_failed.connect(lambda err: QMessageBox.critical(self, "Analysis Error", err))
        self.analysis_service.export_complete.connect(lambda fp: QMessageBox.information(self, "Export Successful", f"Results exported to {fp}"))
        self.analysis_service.export_failed.connect(lambda err: QMessageBox.critical(self, "Export Error", err))
        self.animation_service.preparation_started.connect(lambda fp: self.statusBar().showMessage(f"Preparing animation: {QFileInfo(fp).fileName()}...",0))
        self.animation_service.preparation_complete.connect(self._handle_animation_data_prepared)
        self.animation_service.preparation_failed.connect(lambda err: QMessageBox.critical(self, "Animation Prep Error", err))
        self.animation_service.preparation_warning.connect(lambda warn: QMessageBox.warning(self, "Animation Prep Warning", warn))

        # UI Element Signals
        self.open_pdf_action.triggered.connect(self._handle_open_pdf_action)
        self.open_project_action.triggered.connect(self._handle_open_project_action)
        self.save_project_action.triggered.connect(self._handle_save_project_action)
        self.save_as_project_action.triggered.connect(self._handle_save_project_as_action)
        self.set_scale_action.triggered.connect(lambda: self.pdf_viewer.set_mode(InteractionMode.SET_SCALE_START))
        self.draw_obstacle_action.triggered.connect(lambda: self.pdf_viewer.set_mode(InteractionMode.DRAW_OBSTACLE))
        self.define_staging_area_action.triggered.connect(lambda: self.pdf_viewer.set_mode(InteractionMode.DEFINE_STAGING_AREA))
        self.set_start_point_action.triggered.connect(lambda: self.pdf_viewer.set_mode(InteractionMode.SET_START_POINT))
        self.set_end_point_action.triggered.connect(lambda: self.pdf_viewer.set_mode(InteractionMode.SET_END_POINT))
        self.define_aisle_line_action.triggered.connect(lambda: self.pdf_viewer.set_mode(InteractionMode.DEFINE_AISLE_LINE_START))
        self.define_staging_line_action.triggered.connect(lambda: self.pdf_viewer.set_mode(InteractionMode.DEFINE_STAGING_LINE_START))
        self.edit_mode_action.toggled.connect(self._toggle_edit_mode) # Use toggled for checkable action
        self.meters_action.triggered.connect(lambda: self.model.set_display_unit("meters"))
        self.feet_action.triggered.connect(lambda: self.model.set_display_unit("feet"))
        self.resolution_spinbox.valueChanged.connect(self.model.set_grid_resolution_factor)
        self.penalty_spinbox.valueChanged.connect(self.model.set_staging_area_penalty)
        self.calculate_button.clicked.connect(self._handle_calculate_single_path)
        self.precompute_paths_action.triggered.connect(lambda: self.pathfinding_service.precompute_all_paths(self.model))
        self.analyze_picklist_action.triggered.connect(self._trigger_picklist_analysis)
        self.view_last_analysis_action.triggered.connect(self._view_last_analysis_results_dialog)
        self.export_last_analysis_action.triggered.connect(self._export_last_analysis_results_dialog)
        self.animate_picklist_action.triggered.connect(self._trigger_picklist_animation)
        self.animation_timer.timeout.connect(self._handle_animation_tick)

    # --- Model Signal Handlers ---
    @Slot()
    def _handle_model_reset(self):
        print("[MainWindow] Model has been reset.")
        self.pdf_viewer._clear_scene_items(clear_pdf=True)
        self._update_all_ui_states()
        self.statusBar().showMessage("Model reset. Open a PDF or Project.")
        self.setWindowTitle("Warehouse Path Finder")
        self._last_analysis_detailed_results = None; self._last_analysis_warnings = None
        self._last_analysis_unit = None; self._last_analysis_input_filename = None
        self._stop_animation_and_close_dialog()

    @Slot(str)
    def _handle_pdf_loaded_in_model(self, pdf_path: str):
        print(f"[MainWindow] Model reports PDF path set: {pdf_path}")
        if pdf_path and self.model.pdf_bounds: # Check if bounds also exist
            success, _ = self.pdf_viewer.load_pdf(pdf_path) # Viewer loads its own copy
            if success:
                # Model already has bounds, just ensure viewer draws items
                self._redraw_viewer_from_model()
                self.statusBar().showMessage(f"Loaded PDF: {pdf_path}. Set scale.", 5000)
            else:
                QMessageBox.critical(self, "PDF Load Error", f"Failed to load PDF into viewer: {pdf_path}")
                self.model.reset()
        elif not pdf_path: # Model was reset, pdf_path is None
             self.pdf_viewer._clear_scene_items(clear_pdf=True)
        self._update_all_ui_states(); self._update_window_title()

    @Slot(float, str, str)
    def _handle_scale_changed_in_model(self, pixels_per_unit, calib_unit, disp_unit):
        self.statusBar().showMessage(f"Scale: {pixels_per_unit:.2f} px/{calib_unit}. Display: {disp_unit}. Ready for layout.", 5000)
        self._update_all_ui_states() # Updates granularity label and action states

    @Slot()
    def _handle_layout_or_points_changed_in_model(self):
        print("[MainWindow] Model layout or points changed. Redrawing viewer.")
        self._redraw_viewer_from_model()
        self._update_all_ui_states()

    def _redraw_viewer_from_model(self):
        """Clears and redraws all model-managed items in the PdfViewer."""
        self.pdf_viewer.clear_obstacles()
        for obs_poly in self.model.obstacles: self.pdf_viewer.add_obstacle_item(obs_poly)
        self.pdf_viewer.clear_staging_areas()
        for sa_poly in self.model.staging_areas: self.pdf_viewer.add_staging_area_item(sa_poly)
        self.pdf_viewer.clear_all_points()
        for name, pos in self.model.pick_aisles.items(): self.pdf_viewer.add_pick_aisle_item(name, pos)
        for name, pos in self.model.staging_locations.items(): self.pdf_viewer.add_staging_location_item(name, pos)
        self.pdf_viewer.clear_path() # Clear any old path if layout changed

    @Slot()
    def _handle_grid_params_changed_in_model(self):
        self._update_spinbox_values_from_model() # Ensure UI reflects model
        self._update_granularity_label()
        self._update_all_ui_states() # Actions might depend on this

    @Slot()
    def _handle_project_loaded_in_model(self):
        print("[MainWindow] Project loaded in model. Updating UI.")
        if self.model.current_pdf_path:
            success, bounds = self.pdf_viewer.load_pdf(self.model.current_pdf_path)
            if success and bounds:
                # If model didn't have bounds from project file, set them now from viewer
                if not self.model.pdf_bounds: self.model._pdf_bounds = bounds
            else:
                QMessageBox.warning(self, "Project Load", f"Could not load associated PDF: {self.model.current_pdf_path}")
        else: self.pdf_viewer._clear_scene_items(clear_pdf=True)
        self._redraw_viewer_from_model()
        self.statusBar().showMessage(f"Project '{QFileInfo(self.model.current_project_path).fileName()}' loaded.", 5000)
        self._update_window_title(); self._update_all_ui_states()

    @Slot()
    def _handle_grid_invalidated_in_model(self):
        print("[MainWindow] Model grid invalidated. Clearing visual path.")
        self.pdf_viewer.clear_path()
        self.statusBar().showMessage("Path data is stale. Re-calculate or Precompute.", 3000)
        self._update_all_ui_states()

    @Slot(float, float)
    def _handle_cart_dimensions_changed_in_model(self, width: float, length: float):
        if self.animation_control_dialog:
            self.animation_control_dialog.cart_width_spinbox.setValue(width)
            self.animation_control_dialog.cart_length_spinbox.setValue(length)

    # --- PdfViewer Signal Handlers ---
    @Slot(QPointF, QPointF)
    def _handle_scale_line_drawn(self, p1: QPointF, p2: QPointF):
        print(f"[MainWindow] _handle_scale_line_drawn called with p1: {p1}, p2: {p2}") # Debug print

        pixel_dist = math.dist(p1.toTuple(), p2.toTuple())
        print(f"[MainWindow] Calculated pixel_dist: {pixel_dist}") # Debug print

        if pixel_dist < 1e-6:
            self.statusBar().showMessage("Scale line too short. Please try again.", 3000)
            print("[MainWindow] Scale line too short, re-entering SET_SCALE_START mode.") # Debug print
            self.pdf_viewer.set_mode(InteractionMode.SET_SCALE_START)
            return

        unit_to_use = self.model.display_unit
        print(f"[MainWindow] Showing QInputDialog for scale with unit: {unit_to_use}") # Debug print

        real_dist_str, ok = QInputDialog.getText(self, "Set Scale",
                                               f"The drawn line is {pixel_dist:.2f} pixels long.\n"
                                               f"Enter its real-world distance (in {unit_to_use}):")
        
        print(f"[MainWindow] QInputDialog result: ok={ok}, text='{real_dist_str}'") # Debug print

        if ok and real_dist_str:
            try:
                real_dist = float(real_dist_str)
                if real_dist <= 0:
                    raise ValueError("Distance must be positive.")
                
                self.model.set_scale(pixel_dist / real_dist, unit_to_use)
                # Status message for scale set will be handled by _handle_scale_changed_in_model
            except ValueError:
                QMessageBox.warning(self, "Invalid Input", "Please enter a valid positive number for the distance.")
                print("[MainWindow] Invalid distance input, re-entering SET_SCALE_START mode.") # Debug print
                self.pdf_viewer.set_mode(InteractionMode.SET_SCALE_START) # Allow retry
        else:
            self.statusBar().showMessage("Scale setting cancelled by user.", 3000)
            print("[MainWindow] Scale setting cancelled by user.") # Debug print
        
        # Ensure mode is reset if not already handled or re-entered for retry
        if self.pdf_viewer.current_mode not in [InteractionMode.IDLE, InteractionMode.SET_SCALE_START]:
            print(f"[MainWindow] Explicitly setting PdfViewer mode to IDLE from _handle_scale_line_drawn (current: {self.pdf_viewer.current_mode.name})")
            self.pdf_viewer.set_mode(InteractionMode.IDLE)

    @Slot(InteractionMode, QPolygonF)
    def _handle_polygon_drawn(self, mode_type: InteractionMode, polygon: QPolygonF):
        if mode_type == InteractionMode.DRAW_OBSTACLE: self.model.add_obstacle(polygon)
        elif mode_type == InteractionMode.DEFINE_STAGING_AREA: self.model.add_staging_area(polygon)
        # Model changes will trigger PdfViewer redraw via _handle_layout_or_points_changed_in_model

    @Slot(PointType, QPointF)
    def _handle_point_placement_requested(self, point_type: PointType, pos: QPointF):
        title, prompt = f"New {point_type.value} Name", f"Enter name for this {point_type.value}:"
        name, ok = QInputDialog.getText(self, title, prompt)
        if ok and name:
            name = name.strip()
            if not name: QMessageBox.warning(self, "Invalid Name", f"{point_type.value} name empty."); return
            success = False
            if point_type == PointType.PICK_AISLE:
                if name in self.model.pick_aisles: QMessageBox.warning(self, "Duplicate", f"Pick Aisle '{name}' exists."); return
                success = self.model.add_pick_aisle(name, pos)
            elif point_type == PointType.STAGING_LOCATION:
                if name in self.model.staging_locations: QMessageBox.warning(self, "Duplicate", f"Staging Location '{name}' exists."); return
                success = self.model.add_staging_location(name, pos)
            if success: self.statusBar().showMessage(f"{point_type.value} '{name}' added.", 3000)
        else: self.statusBar().showMessage(f"Set {point_type.value} cancelled.", 3000)
        self.pdf_viewer.set_mode(InteractionMode.IDLE)

    @Slot(PointType, QPointF, QPointF)
    def _handle_line_definition_requested(self, point_type: PointType, p1: QPointF, p2: QPointF):
        dialog = LineDefinitionDialog(point_type.value, self)
        if dialog.exec():
            params = dialog.get_parameters()
            if params: self._generate_points_on_line_from_model(point_type, *params, p1, p2)
            else: QMessageBox.warning(self, f"Define {point_type.value} Line", "Invalid parameters.")
        # Viewer stays in its line drawing start mode unless user cancels it.

    @Slot(list)
    def _handle_delete_items_requested(self, items_to_delete_refs: List[QGraphicsItem]):
        if not items_to_delete_refs: return
        confirm = QMessageBox.question(self, "Confirm Deletion", f"Delete {len(items_to_delete_refs)} selected item(s)?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.No: self.pdf_viewer.scene().clearSelection(); return
        deleted_count = 0
        for item_ref in items_to_delete_refs:
            # Find by reference in PdfViewer's internal lists to get the model's polygon
            # This assumes PdfViewer's lists accurately mirror model's polygons' graphics items
            found_in_model = False
            for i, viewer_item in enumerate(self.pdf_viewer._obstacle_items):
                if viewer_item is item_ref:
                    if i < len(self.model.obstacles): self.model.remove_obstacle_by_ref(self.model.obstacles[i]); deleted_count+=1; found_in_model=True
                    break
            if found_in_model: continue
            for i, viewer_item in enumerate(self.pdf_viewer._staging_area_items):
                if viewer_item is item_ref:
                    if i < len(self.model.staging_areas): self.model.remove_staging_area_by_ref(self.model.staging_areas[i]); deleted_count+=1; found_in_model=True
                    break
            if found_in_model: continue

            item_data = item_ref.data(0) # For points
            if item_data and isinstance(item_data, dict):
                name, pt_type_str = item_data.get("name"), item_data.get("type")
                if name and pt_type_str:
                    if pt_type_str == PointType.PICK_AISLE.value and self.model.remove_pick_aisle(name): deleted_count +=1
                    elif pt_type_str == PointType.STAGING_LOCATION.value and self.model.remove_staging_location(name): deleted_count +=1
        if deleted_count > 0: self.statusBar().showMessage(f"Deleted {deleted_count} item(s).", 3000)
        self.pdf_viewer.scene().clearSelection()

    @Slot(QGraphicsItem, object) # object can be QPolygonF or QPointF
    def _handle_item_moved_in_edit(self, moved_item: QGraphicsItem, new_geometry: Any):
        item_updated_in_model = False
        # This logic is still tricky. PdfViewer needs to reliably map QGraphicsItem to original model data.
        # Using item.data(0) to store unique ID/name is best.
        item_data = moved_item.data(0) # Assume points have data set
        if isinstance(new_geometry, QPolygonF): # Obstacle or Staging Area
            # Try to find by reference in viewer's lists to update corresponding model polygon
            # This needs a more robust mapping strategy (e.g., unique IDs)
            for i, obs_item in enumerate(self.pdf_viewer._obstacle_items):
                if obs_item is moved_item:
                    if i < len(self.model.obstacles): self.model.update_obstacle(self.model.obstacles[i], new_geometry); item_updated_in_model = True
                    break
            if not item_updated_in_model:
                for i, sa_item in enumerate(self.pdf_viewer._staging_area_items):
                    if sa_item is moved_item:
                        if i < len(self.model.staging_areas): self.model.update_staging_area(self.model.staging_areas[i], new_geometry); item_updated_in_model = True
                        break
        elif isinstance(new_geometry, QPointF) and item_data and isinstance(item_data, dict): # Point
            name, pt_type_str = item_data.get("name"), item_data.get("type")
            if name and pt_type_str:
                if pt_type_str == PointType.PICK_AISLE.value: self.model.update_pick_aisle(name, new_geometry); item_updated_in_model = True
                elif pt_type_str == PointType.STAGING_LOCATION.value: self.model.update_staging_location(name, new_geometry); item_updated_in_model = True
        
        if item_updated_in_model: self.statusBar().showMessage(f"Item moved.", 2000)
        else: print(f"[MainWindow] Warn: Could not map moved item {moved_item} to model for update.")


    # --- UI Action Handlers ---
    def _handle_open_pdf_action(self):
        self._stop_animation_and_close_dialog()
        file_path, _ = QFileDialog.getOpenFileName(self, "Open PDF Layout", "", "PDF Files (*.pdf)")
        if file_path:
            temp_doc: Optional[fitz.Document] = None
            try:
                temp_doc = fitz.open(file_path) # fitz should be imported
                if temp_doc.page_count > 0:
                    page = temp_doc.load_page(0); rect = page.rect
                    pdf_bounds = QRectF(rect.x0, rect.y0, rect.width, rect.height)
                    self.model.set_pdf_path_and_bounds(file_path, pdf_bounds) # This will trigger model_reset then pdf_path_changed
                else: QMessageBox.warning(self, "PDF Error", "PDF has no pages.")
            except Exception as e: QMessageBox.critical(self, "PDF Error", f"Could not read PDF: {e}")
            finally:
                if temp_doc: temp_doc.close()
        else: self.statusBar().showMessage("Open PDF cancelled.", 3000)

    def _disconnect_model_signals(self):
        """Helper to disconnect signals from the current self.model instance."""
        if self.model: # Check if a model exists
            try:
                self.model.pdf_path_changed.disconnect(self._handle_pdf_loaded_in_model)
                self.model.scale_changed.disconnect(self._handle_scale_changed_in_model)
                self.model.layout_changed.disconnect(self._handle_layout_or_points_changed_in_model)
                self.model.points_changed.disconnect(self._handle_layout_or_points_changed_in_model)
                self.model.grid_parameters_changed.disconnect(self._handle_grid_params_changed_in_model)
                self.model.project_loaded.disconnect(self._handle_project_loaded_in_model)
                self.model.model_reset.disconnect(self._handle_model_reset)
                self.model.grid_invalidated.disconnect(self._handle_grid_invalidated_in_model)
                self.model.cart_dimensions_changed.disconnect(self._handle_cart_dimensions_changed_in_model)
                self.model.save_state_changed.disconnect(self._update_action_states) # Was _update_save_actions_state
                print("[MainWindow] Disconnected signals from old model.")
            except RuntimeError as e:
                # This can happen if signals were never connected or already disconnected
                print(f"[MainWindow] Info: Error disconnecting model signals (might be normal): {e}")
            except AttributeError as e:
                 print(f"[MainWindow] Info: AttributeError disconnecting model signals (model might be incomplete): {e}")


    def _connect_model_signals(self):
        """Helper to connect signals to the current self.model instance."""
        if self.model: # Check if a model exists
            self.model.pdf_path_changed.connect(self._handle_pdf_loaded_in_model)
            self.model.scale_changed.connect(self._handle_scale_changed_in_model)
            self.model.layout_changed.connect(self._handle_layout_or_points_changed_in_model)
            self.model.points_changed.connect(self._handle_layout_or_points_changed_in_model)
            self.model.grid_parameters_changed.connect(self._handle_grid_params_changed_in_model)
            self.model.project_loaded.connect(self._handle_project_loaded_in_model)
            self.model.model_reset.connect(self._handle_model_reset)
            self.model.grid_invalidated.connect(self._handle_grid_invalidated_in_model)
            self.model.cart_dimensions_changed.connect(self._handle_cart_dimensions_changed_in_model)
            self.model.save_state_changed.connect(self._update_action_states)
            print("[MainWindow] Connected signals to new model.")

    @Slot()
    def _handle_open_project_action(self):
        self._stop_animation_and_close_dialog() # Good practice to stop ongoing processes

        # TODO: Add check for unsaved changes in the current model before proceeding

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Warehouse Project", "", "Warehouse Project Files (*.whp)"
        )
        if file_path:
            loaded_model = self.project_service.load_project(file_path)
            if loaded_model:
                # Disconnect signals from the old model BEFORE replacing it
                self._disconnect_model_signals()
                
                self.model = loaded_model  # Replace current model with the newly loaded one
                self.model.setParent(self) # Ensure proper Qt object ownership if model is a QObject

                # Connect signals to the new model instance
                self._connect_model_signals()
                
                # Manually trigger project_loaded handling sequence for the new model.
                # The model.mark_project_loaded() in ProjectService will emit project_loaded,
                # which _handle_project_loaded_in_model will catch.
                # However, we might need to explicitly call some UI updates if the model instance truly changed.
                self._handle_project_loaded_in_model() # This will refresh viewer and UI states
                
                self.statusBar().showMessage(f"Project '{QFileInfo(file_path).fileName()}' loaded successfully.", 5000)
            # If loaded_model is None, project_service would have emitted project_load_failed signal
            # and MainWindow's slot for that signal would show an error message.
        else:
            self.statusBar().showMessage("Open Project cancelled.", 3000)

    def _handle_save_project_action(self):
        if self.model.current_project_path:
            self.project_service.save_project(self.model, self.model.current_project_path)
        else: self._handle_save_project_as_action()

    def _handle_save_project_as_action(self):
        if not self.model.is_saveable: QMessageBox.warning(self, "Save", "No data to save."); return
        sugg_name = (QFileInfo(self.model.current_pdf_path).baseName() if self.model.current_pdf_path else "untitled") + ".whp"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Project As", sugg_name, "Warehouse Project Files (*.whp)")
        if file_path:
            if self.project_service.save_project(self.model, file_path):
                self.model.set_current_project_path(file_path) # Update model's knowledge of its path
                self._update_window_title()

    def _toggle_edit_mode(self, checked: bool):
        self.pdf_viewer.set_mode(InteractionMode.EDIT if checked else InteractionMode.IDLE)
        # set_edit_mode_flags is now called within pdf_viewer.set_mode
        self.statusBar().showMessage("Edit Mode ON. Select items or use Rubberband. Uncheck to exit." if checked else "Edit Mode OFF.", 0 if checked else 3000)


    def _generate_points_on_line_from_model(self, point_type: PointType, cluster: str, start_num: int, end_num: int, p1: QPointF, p2: QPointF):
        # ... (logic as before, calling self.model.add_pick_aisle or self.model.add_staging_location)
        added_count, duplicates_skipped = 0, 0
        total_points_in_range = (end_num - start_num) + 1
        if point_type == PointType.PICK_AISLE:
            x, y_s, y_e = (p1.x()+p2.x())/2, min(p1.y(),p2.y()), max(p1.y(),p2.y())
            num_pairs = (total_points_in_range + 1) // 2; current_val = start_num
            if num_pairs < 1: return
            spacing = (y_e - y_s) / max(1, num_pairs - 1) if num_pairs > 1 else 0
            for i in range(num_pairs):
                y = y_s + i * spacing if num_pairs > 1 else (y_s + y_e) / 2
                for j in range(2):
                    if current_val + j <= end_num:
                        name = f"{cluster}{current_val + j}"
                        if self.model.add_pick_aisle(name, QPointF(x,y)): added_count += 1
                        else: duplicates_skipped += 1
                current_val += 2
        elif point_type == PointType.STAGING_LOCATION:
            y, x_s, x_e = (p1.y()+p2.y())/2, min(p1.x(),p2.x()), max(p1.x(),p2.x())
            num_points = total_points_in_range
            if num_points < 1: return
            spacing = (x_e - x_s) / max(1, num_points - 1) if num_points > 1 else 0
            for i in range(num_points):
                x = x_s + i * spacing if num_points > 1 else (x_s + x_e) / 2
                name = f"{cluster}{start_num + i}"
                if self.model.add_staging_location(name, QPointF(x,y)): added_count +=1
                else: duplicates_skipped +=1
        msg = f"Added {added_count} {point_type.value}(s)."; msg += f" Skipped {duplicates_skipped} duplicates." if duplicates_skipped else ""
        self.statusBar().showMessage(msg, 3000)

    def _handle_calculate_single_path(self):
        if not self.model.can_calculate_paths: QMessageBox.warning(self, "Error", "Set PDF, scale, and points."); return
        start_n, end_n = self.start_combo.currentText(), self.end_combo.currentText()
        if not start_n or not end_n: QMessageBox.warning(self, "Selection", "Select start and end points."); return

        if not self.model.grid_is_valid or start_n not in self.model.path_maps:
            QMessageBox.information(self, "Info", f"Path data for '{start_n}' needs precomputation. Run Tools > Precompute All Paths."); return

        self.statusBar().showMessage(f"Calculating path: {start_n} to {end_n}...", 0)
        QApplication.processEvents()
        path_pts, dist = self.pathfinding_service.get_shortest_path(self.model, start_n, end_n)
        self.pdf_viewer.draw_path(path_pts)
        if path_pts and dist is not None: self.statusBar().showMessage(f"Path: {dist:.2f} {self.model.display_unit}.", 5000)
        elif path_pts is None: QMessageBox.information(self, "No Path", f"No path: {start_n} to {end_n}."); self.statusBar().showMessage("No path found.", 5000)
        else: QMessageBox.warning(self, "Error", "Path found, but distance error."); self.statusBar().showMessage("Path found, distance error.", 5000)

    def _trigger_picklist_analysis(self):
        # ... (Logic remains similar, calls self.analysis_service.load_and_analyze) ...
        if not self.model.can_analyze_or_animate: QMessageBox.warning(self, "Analyze", "Set PDF, scale, points & precompute paths."); return
        fp, _ = QFileDialog.getOpenFileName(self, "Open Picklist for Analysis", "", "CSV (*.csv);;Text (*.txt)")
        if not fp: self.statusBar().showMessage("Analysis cancelled."); return
        try:
            dlg = PicklistColumnDialog(fp, self)
            if dlg.exec(): sel = dlg.get_selected_columns(); self.analysis_service.load_and_analyze(self.model, fp, sel['dialect'], sel['has_header'], sel['indices']) if sel else self.statusBar().showMessage("Col selection invalid.")
            else: self.statusBar().showMessage("Col selection cancelled.")
        except RuntimeError as e: QMessageBox.critical(self, "File Error", f"Cannot process picklist preview: {e}")


    def _view_last_analysis_results_dialog(self):
        # ... (Logic remains similar, instantiates AnalysisResultsDialog with cached data) ...
        if not self._last_analysis_detailed_results: QMessageBox.information(self, "View Results", "No analysis results."); return
        dates = sorted(list(set(r.get('date','') for r in self._last_analysis_detailed_results if r.get('date'))))
        dlg = AnalysisResultsDialog(self._last_analysis_input_filename or "N/A", self._last_analysis_warnings,
                                   self._last_analysis_detailed_results, self._last_analysis_unit or self.model.display_unit, dates, self)
        dlg.export_filtered_requested.connect(self._export_filtered_analysis_data)
        dlg.exec()

    def _export_last_analysis_results_dialog(self): # Renamed from _export_last_analysis_results
        if not self._last_analysis_detailed_results: QMessageBox.information(self, "Export", "No results to export."); return
        default_name = "analysis_results.csv"
        if self._last_analysis_input_filename: default_name = f"{QFileInfo(self._last_analysis_input_filename).baseName()}_analysis.csv"
        fp, _ = QFileDialog.getSaveFileName(self, "Export Analysis", default_name, "CSV (*.csv)")
        if fp: self.analysis_service.export_results(self._last_analysis_detailed_results, self._last_analysis_unit or self.model.display_unit, fp)

    @Slot(list, str) # Slot for the signal from AnalysisResultsDialog
    def _export_filtered_analysis_data(self, filtered_results: list, unit: str):
        default_name = "filtered_analysis_results.csv"
        if self._last_analysis_input_filename: default_name = f"{QFileInfo(self._last_analysis_input_filename).baseName()}_filtered_analysis.csv"
        fp, _ = QFileDialog.getSaveFileName(self, "Export Filtered Analysis", default_name, "CSV (*.csv)")
        if fp: self.analysis_service.export_results(filtered_results, unit, fp)


    def _trigger_picklist_animation(self):
        # ... (Logic remains similar, calls self.animation_service.prepare_animation_data) ...
        if not self.model.can_analyze_or_animate: QMessageBox.warning(self, "Animate", "Set PDF, scale, points & precompute."); return
        fp, _ = QFileDialog.getOpenFileName(self, "Open Picklist for Animation", "", "CSV (*.csv);;Text (*.txt)")
        if not fp: self.statusBar().showMessage("Animation cancelled."); return
        try:
            dlg = AnimationPicklistDialog(fp, self)
            if dlg.exec(): sel = dlg.get_animation_selection_data(); self.animation_service.prepare_animation_data(self.model, fp, sel) if sel else self.statusBar().showMessage("Anim col selection invalid.")
            else: self.statusBar().showMessage("Anim col selection cancelled.")
        except RuntimeError as e: QMessageBox.critical(self, "File Error", f"Cannot process animation file preview: {e}")


    # --- Animation Control & Loop ---
    def _stop_animation_and_close_dialog(self):
        self.animation_timer.stop()
        self.pdf_viewer.clear_animation_overlay()
        if self.animation_control_dialog:
            # Disconnect to prevent issues if dialog is already closing
            try: self.animation_control_dialog.rejected.disconnect(self._stop_animation_and_close_dialog)
            except RuntimeError: pass # Signal was not connected or already disconnected
            self.animation_control_dialog.close()
            self.animation_control_dialog = None
        self.current_animation_time_s = 0.0
        self._animation_data_prepared = []
        self._animation_earliest_dt_prepared = None
        print("[MainWindow] Animation stopped and dialog closed.")

    @Slot(bool)
    def _toggle_animation_playback(self, play: bool):
        if play and self._animation_data_prepared:
            if self._filtered_max_time_s is not None and self.current_animation_time_s >= self._filtered_max_time_s:
                self._reset_animation_state_and_frame()
            self.animation_timer.start()
            self.statusBar().showMessage("Animation Playing...", 0)
        else:
            self.animation_timer.stop()
            self.statusBar().showMessage("Animation Paused.", 3000)

    @Slot(bool) # Slot decorator, takes a boolean indicating success
    def _handle_grid_update_finished(self, success: bool):
        if success:
            self.statusBar().showMessage("Pathfinding grid updated successfully.", 3000)
            # Potentially enable actions that depend on a valid grid being present
            # if not self.model.grid_is_valid (though the service should set this if successful)
            # then self.model.grid_is_valid = True (or let service handle model's flag)
        else:
            QMessageBox.warning(self, "Grid Error", 
                                "Failed to update or generate the pathfinding grid. Path calculations may fail.")
            self.statusBar().showMessage("Grid update failed.", 5000)
        
        # Always update UI states that might depend on the grid's presence or validity
        self._update_all_ui_states() 
        # If precomputation was pending and grid update was a prerequisite,
        # this is where you might re-trigger precomputation or enable the action.
        # However, usually, precomputation is explicitly triggered by the user or
        # as part of another flow (like loading a project). 

    @Slot(bool, list) # Slot decorator: bool for success, list for failed_point_names
    def _handle_precomputation_finished(self, success: bool, failed_points: List[str]):
        if success:
            if failed_points:
                self.statusBar().showMessage(f"Precomputation finished with some issues. {len(failed_points)} point(s) failed.", 7000)
                QMessageBox.warning(self, "Precomputation Issues",
                                    f"Path precomputation completed, but issues were encountered for the following points (they might be inside obstacles):\n\n"
                                    f"{', '.join(failed_points)}")
            else:
                self.statusBar().showMessage("Path precomputation complete for all valid points.", 5000)
        else:
            # This case might occur if the whole multiprocessing step failed, or no valid tasks.
            error_message = "Path precomputation failed."
            if failed_points: # If some points were identified as problematic before/during parallel run
                error_message += f" Issues for: {', '.join(failed_points)}."
            QMessageBox.critical(self, "Precomputation Error", error_message)
            self.statusBar().showMessage("Precomputation failed.", 5000)
        
        # Crucially, update UI states as precomputation affects what can be done next
        self._update_all_ui_states()       

    @Slot(list, list, str, str) # Slot: detailed_results, warnings_list, unit_str, input_filename_str
    def _handle_analysis_complete(self,
                                  detailed_results: List[Dict[str, Any]],
                                  warnings_list: List[str],
                                  unit: str,
                                  input_filename: str):
        
        file_base_name = QFileInfo(input_filename).fileName()
        self.statusBar().showMessage(f"Analysis of '{file_base_name}' complete.", 5000)

        # Cache the results for "View Last Analysis" and "Export Last Analysis"
        self._last_analysis_detailed_results = detailed_results
        self._last_analysis_warnings = warnings_list
        self._last_analysis_unit = unit
        self._last_analysis_input_filename = input_filename # Store the original full path

        self._update_all_ui_states() # Update actions like "View Last Analysis"

        # Automatically show the results dialog
        if detailed_results: # Only show if there's something to show
            self._view_last_analysis_results_dialog()
        elif warnings_list: # If no results but there are warnings, maybe still show them
            QMessageBox.information(self, "Analysis Info",
                                    "Analysis complete, but no data rows were successfully processed.\n\n" +
                                    "\n".join(warnings_list[:5]) + ("..." if len(warnings_list) > 5 else ""))
        else:
            QMessageBox.information(self, "Analysis Info", "Analysis complete. No data processed and no warnings.")

    @Slot(list, object) 
    def _handle_animation_data_prepared(self, animation_data_from_signal: List[Dict[str, Any]], earliest_dt_from_signal: Optional[datetime]):
        print(f"[MainWindow] _handle_animation_data_prepared received {len(animation_data_from_signal)} items.")
        if animation_data_from_signal:
            print(f"[MainWindow] Sample received animation data item: {animation_data_from_signal[0]}")
            if 'start_dt' in animation_data_from_signal[0]:
                print(f"[MainWindow] Sample item start_dt: {animation_data_from_signal[0]['start_dt']} (type: {type(animation_data_from_signal[0]['start_dt'])})")
            else:
                print("[MainWindow] WARNING: Received anim_data item MISSING 'start_dt'!")
        print(f"[MainWindow] Received earliest_dt: {earliest_dt_from_signal}")

        # 1. Stop any existing animation and close its dialog FIRST
        self._stop_animation_and_close_dialog()

        # 2. Check if new data is valid
        if not animation_data_from_signal:
            QMessageBox.warning(self, "Animation Data", "No valid animation data could be prepared.")
            self.statusBar().showMessage("Animation data preparation resulted in no usable entries.", 5000)
            self._animation_data_prepared = [] # Ensure it's empty if new data is bad
            self._animation_earliest_dt_prepared = None
            self._update_all_ui_states()
            return

        # 3. Now assign the new data to instance variables
        self._animation_data_prepared = animation_data_from_signal
        self._animation_earliest_dt_prepared = earliest_dt_from_signal
        self.statusBar().showMessage("Animation data ready. Opening controls...", 3000)

        # 4. Extract clusters and dates from the newly set self._animation_data_prepared
        all_starts_set = set()
        all_ends_set = set()
        unique_dates_str_set = set()

        print(f"[MainWindow] Processing {len(self._animation_data_prepared)} items for dialog setup...")

        for idx, item in enumerate(self._animation_data_prepared): # Now this will use the new data
            start_name = item.get('start_name')
            end_name = item.get('end_name')
            item_start_dt = item.get('start_dt')

            if start_name:
                start_cluster = _get_cluster_from_name(start_name)
                if start_cluster: all_starts_set.add(start_cluster)
            if end_name:
                end_cluster = _get_cluster_from_name(end_name)
                if end_cluster: all_ends_set.add(end_cluster)
            if item_start_dt and isinstance(item_start_dt, datetime):
                unique_dates_str_set.add(item_start_dt.strftime("%Y-%m-%d"))
        
        sorted_unique_dates = sorted(list(unique_dates_str_set))
        
        print(f"[MainWindow] Extracted Start Clusters: {all_starts_set}")
        print(f"[MainWindow] Extracted End Clusters: {all_ends_set}")
        print(f"[MainWindow] Extracted Unique Dates (strings): {unique_dates_str_set}")
        print(f"[MainWindow] Sorted Unique Dates for Dialog: {sorted_unique_dates}")

        # 5. Create and show the dialog
        self.animation_control_dialog = AnimationControlDialog(
            all_starts_set,
            all_ends_set,
            sorted_unique_dates,
            self.model.animation_cart_width,
            self.model.animation_cart_length,
            self.model.display_unit,
            self
        )
        # ... (connections and showing the dialog) ...
        self.animation_control_dialog.play_pause_toggled.connect(self._toggle_animation_playback)
        self.animation_control_dialog.reset_clicked.connect(self._reset_animation_state_and_frame)
        self.animation_control_dialog.speed_changed.connect(self._set_animation_speed)
        self.animation_control_dialog.filters_changed.connect(self._apply_animation_filters)
        self.animation_control_dialog.cart_dimensions_changed.connect(self.model.set_animation_cart_dimensions)
        self.animation_control_dialog.rejected.connect(self._stop_animation_and_close_dialog)

        initial_date_filter = "All Dates"
        if sorted_unique_dates:
            initial_date_filter = sorted_unique_dates[0]
        
        # This will also call _apply_animation_filters which resets to the new range
        self.animation_control_dialog.select_date(initial_date_filter)
        
        # If select_date doesn't trigger filters_changed (e.g., if it's already the current text),
        # explicitly apply filters to ensure time ranges are set.
        # However, select_date in AnimationControlDialog *should* trigger currentTextChanged
        # if the index actually changes. If it's already on the desired text,
        # we need to ensure _apply_animation_filters is called.
        current_dialog_date = self.animation_control_dialog.date_combo.currentText()
        if initial_date_filter == current_dialog_date : # If select_date didn't cause a change signal
            self._apply_animation_filters(
                current_dialog_date,
                sorted(list(all_starts_set)),
                sorted(list(all_ends_set)),
                AnimationMode(self.animation_control_dialog.mode_combo.currentText()),
                self.animation_control_dialog.path_duration_spinbox.value(),
                self.animation_control_dialog.keep_paths_checkbox.isChecked()
            )
        
        self.animation_control_dialog.show()

    @Slot()
    def _reset_animation_state_and_frame(self):
        self.current_animation_time_s = self._filtered_min_time_s if self._filtered_min_time_s is not None else 0.0
        self._update_animation_frame() # Draw initial frame
        if self.animation_control_dialog:
            self.animation_control_dialog.update_time_display(self.current_animation_time_s, self._filtered_earliest_dt)
            self.animation_control_dialog.update_progress(self.current_animation_time_s, self._filtered_min_time_s or 0.0, self._filtered_max_time_s or 0.0)
            self.animation_control_dialog.play_pause_button.setChecked(False)
        self.animation_timer.stop() # Ensure stopped on reset
        self.statusBar().showMessage("Animation Reset.", 3000)

    @Slot(int)
    def _set_animation_speed(self, speed: int): self.animation_speed_multiplier = float(speed)

    @Slot(str, list, list, AnimationMode, int, bool)
    def _apply_animation_filters(self, date_str, start_clusters, end_clusters, mode, duration_min, keep_paths):
        self._animation_selected_date_filter = date_str
        self._animation_active_start_clusters = set(start_clusters)
        self._animation_active_end_clusters = set(end_clusters)
        self._animation_mode_current = mode
        self._path_visibility_duration_s_current = duration_min * 60
        self._keep_paths_visible_current = keep_paths
        self._recalculate_filtered_animation_time_range()
        self._reset_animation_state_and_frame()
        self.statusBar().showMessage(f"Animation filters updated. Mode: {mode.value}", 3000)

    def _recalculate_filtered_animation_time_range(self):
        if not self._animation_data_prepared: self._filtered_min_time_s=0.0; self._filtered_max_time_s=0.0; self._filtered_earliest_dt=None; return
        min_t, max_t, earliest_dt_filt, found = float('inf'), float('-inf'), None, False
        for item in self._animation_data_prepared:
            item_date_str = item['start_dt'].strftime("%Y-%m-%d")
            if self._animation_selected_date_filter == "All Dates" or item_date_str == self._animation_selected_date_filter:
                found=True; min_t=min(min_t,item['start_time_s']); max_t=max(max_t,item['end_time_s'])
                if earliest_dt_filt is None or item['start_dt'] < earliest_dt_filt: earliest_dt_filt = item['start_dt']
        if found: self._filtered_min_time_s=min_t; self._filtered_max_time_s=max_t if max_t>min_t else min_t; self._filtered_earliest_dt=earliest_dt_filt
        else: self._filtered_min_time_s=0.0; self._filtered_max_time_s=0.0; self._filtered_earliest_dt=None
        print(f"[MainWindow] Filtered anim range: [{self._filtered_min_time_s}, {self._filtered_max_time_s}] for date '{self._animation_selected_date_filter}'")

    @Slot()
    def _handle_animation_tick(self):
        if not self._animation_data_prepared or self._filtered_max_time_s is None: return
        time_increment = (self.animation_timer.interval()/1000.0) * self.animation_speed_multiplier
        self.current_animation_time_s += time_increment
        if self.current_animation_time_s >= self._filtered_max_time_s:
            self.current_animation_time_s = self._filtered_max_time_s; self.animation_timer.stop()
            if self.animation_control_dialog: self.animation_control_dialog.play_pause_button.setChecked(False)
            self.statusBar().showMessage("Animation Finished.", 3000)
        self._update_animation_frame()
        if self.animation_control_dialog:
            self.animation_control_dialog.update_time_display(self.current_animation_time_s, self._filtered_earliest_dt) # Pass filtered earliest dt
            self.animation_control_dialog.update_progress(self.current_animation_time_s, self._filtered_min_time_s or 0.0, self._filtered_max_time_s or 0.0)

    def _update_animation_frame(self):
        if not self._animation_data_prepared:
            return

        active_items_for_frame = []
        current_time_s = self.current_animation_time_s

        # Optional: Print current time only once per few ticks to reduce spam
        if not hasattr(self, '_anim_tick_count'):
            self._anim_tick_count = 0
        self._anim_tick_count = (self._anim_tick_count + 1) % 200 # Reset every 200 ticks (approx 10 seconds at 20fps)
        
        if self._anim_tick_count == 1: # Print status periodically
            print(f"[ANIM TICK STATUS] Global Time: {current_time_s:.2f}s. "
                  f"Filtered Range: [{self._filtered_min_time_s if self._filtered_min_time_s is not None else 'N/A'}, "
                  f"{self._filtered_max_time_s if self._filtered_max_time_s is not None else 'N/A'}]. "
                  f"Mode: {self._animation_mode_current.value}. "
                  f"Date Filter: '{self._animation_selected_date_filter}'")
            if self.model.scale_pixels_per_unit:
                print(f"    Scale is: {self.model.scale_pixels_per_unit:.2f} px/{self.model.calibration_unit}")
            else:
                print(f"    WARNING: Scale is NOT SET (model.scale_pixels_per_unit is None). Carts may not display correctly.")


        scale_px_per_unit = self.model.scale_pixels_per_unit if self.model.scale_pixels_per_unit is not None and self.model.scale_pixels_per_unit > 0 else 1.0

        for item_idx, item in enumerate(self._animation_data_prepared):
            item_start_dt = item.get('start_dt')
            if not isinstance(item_start_dt, datetime):
                if self._anim_tick_count == 1 and item_idx < 2 : print(f"[ANIM FRAME WARN] Item {item_idx} has invalid start_dt: {item_start_dt}")
                continue

            item_date_str = item_start_dt.strftime("%Y-%m-%d")
            
            # Date Filter Check
            date_match = (self._animation_selected_date_filter == "All Dates" or
                          item_date_str == self._animation_selected_date_filter)
            if not date_match:
                continue
            
            # Cluster Filter Check
            start_cluster = _get_cluster_from_name(item.get('start_name'))
            end_cluster = _get_cluster_from_name(item.get('end_name'))
            start_cluster_match = (not self._animation_active_start_clusters or
                                   (start_cluster and start_cluster in self._animation_active_start_clusters))
            end_cluster_match = (not self._animation_active_end_clusters or
                                 (end_cluster and end_cluster in self._animation_active_end_clusters))
            if not (start_cluster_match and end_cluster_match):
                continue

            item_start_s, item_end_s, path_points = item['start_time_s'], item['end_time_s'], item['path_points']
            item_id = item.get('id', f'Item_{item_idx}')

            if self._animation_mode_current == AnimationMode.CARTS:
                if item_start_s <= current_time_s <= item_end_s and len(path_points) > 1:
                    duration = item_end_s - item_start_s
                    progress = (current_time_s - item_start_s) / duration if duration > 1e-6 else 1.0
                    progress = max(0.0, min(1.0, progress))
                    
                    idx_float = progress * (len(path_points) -1)
                    seg_idx = int(idx_float); seg_prog = idx_float - seg_idx
                    seg_idx = min(seg_idx, len(path_points)-2) 
                    next_idx = min(seg_idx + 1, len(path_points) - 1)
                    
                    p1, p2 = path_points[seg_idx], path_points[next_idx]
                    pos = QPointF(p1.x()+(p2.x()-p1.x())*seg_prog, p1.y()+(p2.y()-p1.y())*seg_prog)
                    angle = math.degrees(math.atan2(p2.y()-p1.y(), p2.x()-p1.x()))
                    
                    cart_width_px = self.model.animation_cart_width * scale_px_per_unit
                    cart_length_px = self.model.animation_cart_length * scale_px_per_unit

                    if self._anim_tick_count == 1 and len(active_items_for_frame) < 2 :
                        print(f"  [CARTS Adding] Item '{item_id}': Prog: {progress:.2f}. Pos: ({pos.x():.1f},{pos.y():.1f}). SizePx: {cart_width_px:.1f}x{cart_length_px:.1f}")

                    if cart_width_px > 0.1 and cart_length_px > 0.1 :
                        active_items_for_frame.append({
                            'pos': pos, 'angle': angle,
                            'width': cart_width_px, 'length': cart_length_px
                        })

            elif self._animation_mode_current == AnimationMode.PATH_LINES:
                is_visible_this_tick = False; alpha = 255; draw_progress = 0.0
                if self._keep_paths_visible_current:
                    if item_start_s <= current_time_s: is_visible_this_tick = True; draw_progress = 1.0
                else: 
                    if item_start_s <= current_time_s <= (item_end_s + self._path_visibility_duration_s_current):
                        is_visible_this_tick = True
                        duration = item_end_s - item_start_s
                        draw_progress = (current_time_s-item_start_s)/duration if duration > 1e-6 else 1.0
                        draw_progress = max(0.0,min(1.0,draw_progress))
                        if current_time_s > item_end_s and self._path_visibility_duration_s_current > 1e-6:
                            fade_p = (current_time_s-item_end_s)/self._path_visibility_duration_s_current
                            alpha=int(255*(1.0-max(0.0,min(1.0,fade_p))))
                
                if is_visible_this_tick and alpha > 0 and len(path_points) > 1:
                    if self._anim_tick_count == 1 and len(active_items_for_frame) < 2 :
                        print(f"  [PATHLINES Adding] Item '{item_id}': DrawProg: {draw_progress:.2f}. Alpha: {alpha}. Cluster: {start_cluster}")
                    active_items_for_frame.append({
                        'id': item_id, 'points': path_points, 'draw_progress': draw_progress,
                        'alpha': alpha, 'start_cluster': start_cluster
                    })
        
        if self._anim_tick_count == 1 :
           if active_items_for_frame:
               print(f"[MainWindow _update_animation_frame] Sending {len(active_items_for_frame)} items to viewer. First item example: {active_items_for_frame[0]}")
           else:
               print(f"[MainWindow _update_animation_frame] No active items to draw at global time {current_time_s:.2f}s (filter: {self._animation_selected_date_filter})")
        
        self.pdf_viewer.update_animation_overlay(self._animation_mode_current, active_items_for_frame)
        self.pdf_viewer.viewport().update()

    # --- UI State Updaters ---
    def _update_all_ui_states(self):
        self._update_comboboxes(); self._update_action_states(); self._update_spinbox_values_from_model()
        self._update_granularity_label(); self._update_window_title(); self._update_unit_menu_state()

    def _update_comboboxes(self):
        start_t, end_t = self.start_combo.currentText(), self.end_combo.currentText()
        self.start_combo.clear(); self.start_combo.addItems(sorted(self.model.pick_aisles.keys()))
        self.end_combo.clear(); self.end_combo.addItems(sorted(self.model.staging_locations.keys()))
        self.start_combo.setCurrentText(start_t) if start_t in self.model.pick_aisles else self.start_combo.setPlaceholderText("Select Start...")
        self.end_combo.setCurrentText(end_t) if end_t in self.model.staging_locations else self.end_combo.setPlaceholderText("Select End...")

    def _update_action_states(self):
        pdf_ok, scale_ok, pts_ok, grid_ok = self.model.current_pdf_path is not None, self.model.is_scale_set, \
                                          self.model.has_pick_aisles and self.model.has_staging_locations, self.model.grid_is_valid
        self.save_project_action.setEnabled(self.model.is_saveable and bool(self.model.current_project_path))
        self.save_as_project_action.setEnabled(self.model.is_saveable)
        self.set_scale_action.setEnabled(pdf_ok); self.edit_mode_action.setEnabled(pdf_ok)
        for act in [self.draw_obstacle_action, self.define_staging_area_action, self.set_start_point_action,
                    self.set_end_point_action, self.define_aisle_line_action, self.define_staging_line_action]: act.setEnabled(scale_ok)
        self.calculate_button.setEnabled(self.model.can_calculate_paths and grid_ok)
        self.precompute_paths_action.setEnabled(self.model.can_precompute) # Grid can be generated if needed
        self.analyze_picklist_action.setEnabled(self.model.can_analyze_or_animate)
        self.animate_picklist_action.setEnabled(self.model.can_analyze_or_animate)
        self.view_last_analysis_action.setEnabled(self._last_analysis_detailed_results is not None)
        self.export_last_analysis_action.setEnabled(self._last_analysis_detailed_results is not None)

    def _update_spinbox_values_from_model(self):
        self.resolution_spinbox.blockSignals(True); self.penalty_spinbox.blockSignals(True)
        self.resolution_spinbox.setValue(self.model.grid_resolution_factor)
        self.penalty_spinbox.setValue(self.model.staging_area_penalty)
        self.resolution_spinbox.blockSignals(False); self.penalty_spinbox.blockSignals(False)

    def _update_granularity_label(self):
        if self.model.is_scale_set and self.model.scale_pixels_per_unit and self.model.scale_pixels_per_unit > 0: # Added > 0 check
            gran_px = self.model.grid_resolution_factor
            gran_cal_unit = gran_px / self.model.scale_pixels_per_unit
            disp_gran = self.pathfinding_service._convert_distance_units(gran_cal_unit, self.model.calibration_unit, self.model.display_unit)
            self.granularity_label.setText(f"Path Detail Granularity: ~ {disp_gran:.2f} {self.model.display_unit}" if disp_gran is not None else "Path Granularity: Unit Error")
        else: self.granularity_label.setText("Path Detail Granularity: N/A (Scale not set)")

    def _update_window_title(self):
        base = "Warehouse Path Finder"
        if self.model.current_project_path: self.setWindowTitle(f"{base} - {QFileInfo(self.model.current_project_path).fileName()}")
        elif self.model.current_pdf_path: self.setWindowTitle(f"{base} - {QFileInfo(self.model.current_pdf_path).fileName()}*")
        else: self.setWindowTitle(base)

    def _update_unit_menu_state(self):
        if self.model.display_unit == "meters": self.meters_action.setChecked(True)
        else: self.feet_action.setChecked(True)

    def closeEvent(self, event):
        # TODO: Check for unsaved changes
        self._stop_animation_and_close_dialog()
        super().closeEvent(event)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

# --- END OF FILE Warehouse-Path-Finder-main/main.py ---