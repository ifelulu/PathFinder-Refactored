# --- START OF FILE Warehouse-Path-Finder-main/pdf_viewer.py ---

import fitz  # PyMuPDF
import math
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsLineItem,
    QGraphicsPolygonItem, QGraphicsItem, QGraphicsEllipseItem, QGraphicsSimpleTextItem,
    QGraphicsPathItem, QMessageBox, QRubberBand, QGraphicsItemGroup, QGraphicsRectItem
)
from PySide6.QtGui import (
    QPixmap, QImage, QPen, QCursor, QBrush, QColor, QKeyEvent, QFont,
    QPainterPath, QTransform, QMouseEvent, QWheelEvent,
    QPolygonF
)
from PySide6.QtCore import (
    Qt, Signal, QRectF, QSize, QEvent,
    QPointF, QLineF
)

# Assuming enums.py is in the same directory or accessible in PYTHONPATH
from enums import InteractionMode, PointType, AnimationMode

# --- CORRECTED IMPORT HERE ---
from typing import Optional, List, Dict, Tuple, Any


# Configuration
OBSTACLE_SNAP_DISTANCE = 10.0 # Scene pixels for snapping polygon close
POINT_MARKER_RADIUS = 5
LABEL_OFFSET_X = 8
LABEL_OFFSET_Y = -POINT_MARKER_RADIUS
STAGING_AREA_ALPHA = int(255 * 0.25) # 25% opacity
ANIMATION_OVERLAY_Z_VALUE = 100
POINTS_Z_VALUE = 20
PATH_Z_VALUE = 15
OBSTACLES_Z_VALUE = 10
STAGING_AREAS_Z_VALUE = 9
PDF_Z_VALUE = 0
BOUNDS_Z_VALUE = 8 # Below staging areas but above PDF

# Set this to True if you need detailed per-frame logs again temporarily
DEBUG_ANIMATION_VERBOSE = False

class PdfViewer(QGraphicsView):
    # --- Signals for User Interactions and State Changes ---
    scale_line_drawn = Signal(QPointF, QPointF)
    polygon_drawn = Signal(InteractionMode, QPolygonF)
    point_placement_requested = Signal(PointType, QPointF)
    line_definition_requested = Signal(PointType, QPointF, QPointF)
    # item_moved_in_edit signal now emits new geometry (QPolygonF or QPointF)
    item_moved_in_edit = Signal(QGraphicsItem, object) # QGraphicsItem, (QPolygonF or QPointF) - 'object' is a generic fallback for Any
    delete_items_requested = Signal(list) # list of QGraphicsItem references
    status_update = Signal(str, int)
    view_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.pdf_document: Optional[fitz.Document] = None
        self.current_page_index = 0
        self.current_pdf_path: Optional[str] = None
        self.pixmap_item: Optional[QGraphicsItem] = None

        self.current_mode = InteractionMode.IDLE
        self._is_panning = False
        self._last_pan_pos = QPointF()
        self._item_being_moved_in_edit: Optional[QGraphicsItem] = None
        self._item_being_moved_in_edit_start_pos: QPointF = QPointF()

        self._temp_drawing_points: List[QPointF] = []
        self._temp_line_item: Optional[QGraphicsLineItem] = None
        self._temp_polygon_item: Optional[QGraphicsPolygonItem] = None

        self._pathfinding_bounds_item: Optional[QGraphicsPolygonItem] = None # Item to display bounds
        self._obstacle_items: List[QGraphicsPolygonItem] = []
        self._staging_area_items: List[QGraphicsPolygonItem] = []
        self._start_point_items: Dict[str, Tuple[QGraphicsEllipseItem, QGraphicsSimpleTextItem]] = {}
        self._end_point_items: Dict[str, Tuple[QGraphicsEllipseItem, QGraphicsSimpleTextItem]] = {}
        self._path_item: Optional[QGraphicsPathItem] = None
        self.animation_overlay_group: Optional[QGraphicsItemGroup] = None

        self._setup_styles()
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)

        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setInteractive(True)

    def _setup_styles(self):
        self._obstacle_pen = QPen(Qt.GlobalColor.darkRed, 1); self._obstacle_pen.setCosmetic(True)
        self._obstacle_brush = QBrush(QColor(255, 0, 0, 60))
        self._obstacle_preview_pen = QPen(Qt.GlobalColor.darkRed, 1, Qt.PenStyle.DashLine); self._obstacle_preview_pen.setCosmetic(True)

        self._staging_area_pen = QPen(QColor(0, 0, 200), 1); self._staging_area_pen.setCosmetic(True)
        self._staging_area_brush = QBrush(QColor(0, 0, 255, STAGING_AREA_ALPHA))
        self._staging_area_preview_pen = QPen(QColor(0, 150, 150), 1, Qt.PenStyle.DashLine); self._staging_area_preview_pen.setCosmetic(True)

        self._bounds_pen = QPen(QColor(128, 0, 128), 3, Qt.PenStyle.SolidLine) # Bold Purple
        self._bounds_pen.setCosmetic(True)
        self._bounds_brush = QBrush(Qt.GlobalColor.transparent) # Transparent fill
        self._bounds_preview_pen = QPen(QColor(128, 0, 128), 2, Qt.PenStyle.DashLine) # Dashed Purple preview
        self._bounds_preview_pen.setCosmetic(True)        

        self._line_def_pen = QPen(Qt.GlobalColor.magenta, 1, Qt.PenStyle.DashLine); self._line_def_pen.setCosmetic(True)
        self._scale_line_pen = QPen(Qt.GlobalColor.red, 1, Qt.PenStyle.DashLine); self._scale_line_pen.setCosmetic(True)

        self._start_point_pen = QPen(Qt.GlobalColor.green, 1); self._start_point_pen.setCosmetic(True)
        self._start_point_brush = QBrush(Qt.GlobalColor.green)
        self._end_point_pen = QPen(Qt.GlobalColor.blue, 1); self._end_point_pen.setCosmetic(True)
        self._end_point_brush = QBrush(Qt.GlobalColor.blue)
        self._path_pen = QPen(QColor(0, 100, 255), 2, Qt.PenStyle.SolidLine); self._path_pen.setCosmetic(True)
        self._label_font = QFont("Arial", 8)

    def _clear_scene_items(self, clear_pdf=True):
        # ... (rest of the method unchanged) ...
        print("[PdfViewer] Clearing scene items...")
        if clear_pdf and self.pixmap_item and self.pixmap_item.scene():
            self.scene().removeItem(self.pixmap_item)
            self.pixmap_item = None
        self.clear_obstacles()
        self.clear_staging_areas()
        self.clear_all_points()
        self.clear_pathfinding_bounds_item()
        self.clear_path()
        self.clear_animation_overlay()
        self._reset_temp_drawing_items()

    def load_pdf(self, file_path: str) -> tuple[bool, Optional[QRectF]]:
        # ... (rest of the method unchanged) ...
        self.set_mode(InteractionMode.IDLE)
        self._is_panning = False
        self._clear_scene_items(clear_pdf=True)
        try:
            self.pdf_document = fitz.open(file_path)
            if self.pdf_document.page_count > 0:
                self.current_pdf_path = file_path
                self.current_page_index = 0
                bounds = self._display_page(self.current_page_index)
                print(f"[PdfViewer] Loaded PDF: {file_path}")
                return True, bounds
            else: print("[PdfViewer] PDF has no pages."); self.pdf_document = None; self.current_pdf_path = None; return False, None
        except Exception as e:
            print(f"[PdfViewer] Error loading PDF: {e}"); self.pdf_document = None; self.current_pdf_path = None; return False, None


    def _display_page(self, page_number: int) -> Optional[QRectF]:
        if not self.pdf_document or not (0 <= page_number < self.pdf_document.page_count):
            print("[PdfViewer _display_page] Invalid document or page number.")
            return None

        print(f"[PdfViewer _display_page] Displaying page: {page_number}")

        # Clear existing PDF pixmap if any
        if self.pixmap_item and self.pixmap_item.scene():
            print("[PdfViewer _display_page] Removing old pixmap_item.")
            self.scene().removeItem(self.pixmap_item)
            self.pixmap_item = None

        page = self.pdf_document.load_page(page_number)
        zoom_matrix = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=zoom_matrix, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        self.pixmap_item = self.scene().addPixmap(QPixmap.fromImage(img))
        self.pixmap_item.setZValue(PDF_Z_VALUE)
        print(f"[PdfViewer _display_page] Added new pixmap_item with ZValue: {self.pixmap_item.zValue()}")

        # Recreate animation overlay group on top
        if self.animation_overlay_group and self.animation_overlay_group.scene():
            print("[PdfViewer _display_page] Removing old animation_overlay_group from scene.")
            # It's important to remove children if the group itself is not being deleted
            # but since we create a new one, removing the group is fine.
            self.scene().removeItem(self.animation_overlay_group)
        
        print("[PdfViewer _display_page] Creating new animation_overlay_group.")
        self.animation_overlay_group = QGraphicsItemGroup()
        self.animation_overlay_group.setZValue(ANIMATION_OVERLAY_Z_VALUE)
        # QGraphicsItemGroup is visible by default, no need for setVisible(True) explicitly on creation
        self.scene().addItem(self.animation_overlay_group)
        
        print(f"[PdfViewer _display_page] New animation_overlay_group added. ZValue: {self.animation_overlay_group.zValue()}, Visible: {self.animation_overlay_group.isVisible()}")
        print(f"[PdfViewer _display_page] Animation group pos: {self.animation_overlay_group.pos()}, sceneTransform: {self.animation_overlay_group.sceneTransform()}")
        # Ensure it has no unintended transformations from a previous state (shouldn't happen with new group)
        self.animation_overlay_group.setPos(0,0)
        self.animation_overlay_group.setTransform(QTransform())


        # Re-add other persistent items (obstacles, points, path) if they exist
        print("[PdfViewer _display_page] Re-adding persistent items to scene...")
        for item in self._obstacle_items:
            if item.scene() != self.scene(): # Add only if not already in this scene (e.g. if scene was cleared)
                self.scene().addItem(item)
                print(f"  Re-added obstacle: {item} Z: {item.zValue()}")
        for item in self._staging_area_items:
            if item.scene() != self.scene():
                self.scene().addItem(item)
                print(f"  Re-added staging area: {item} Z: {item.zValue()}")

        for name, (marker, label) in self._start_point_items.items():
            if marker.scene() != self.scene():
                self.scene().addItem(marker) # Label is child
                print(f"  Re-added start point marker: {name} Z: {marker.zValue()}")
        for name, (marker, label) in self._end_point_items.items():
            if marker.scene() != self.scene():
                self.scene().addItem(marker)
                print(f"  Re-added end point marker: {name} Z: {marker.zValue()}")

        if self._path_item and self._path_item.scene() != self.scene():
            self.scene().addItem(self._path_item)
            print(f"  Re-added path item: {self._path_item} Z: {self._path_item.zValue()}")

        pdf_rect = self.pixmap_item.boundingRect()
        self.setSceneRect(pdf_rect)
        self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        print("[PdfViewer _display_page] Page display complete.")
        return pdf_rect

    def set_mode(self, mode: InteractionMode):
        if self.current_mode == mode: return

        print(f"[PdfViewer] Mode: {self.current_mode.name} -> {mode.name}")

        # If exiting edit mode, disable movability on items
        if self.current_mode == InteractionMode.EDIT and mode != InteractionMode.EDIT:
            self.set_edit_mode_flags(False)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        
        # Reset temporary drawing items ONLY if transitioning TO a state that implies
        # a new drawing operation should start or if cancelling.
        # Or when explicitly going to IDLE/EDIT.
        if mode in [InteractionMode.IDLE, InteractionMode.EDIT,
                    InteractionMode.SET_SCALE_START, # Start of a new scale op
                    InteractionMode.DRAW_OBSTACLE,     # Start of new obstacle
                    InteractionMode.DEFINE_STAGING_AREA, # Start of new staging area
                    InteractionMode.DEFINE_AISLE_LINE_START, # Start of new aisle line
                    InteractionMode.DEFINE_STAGING_LINE_START]: # Start of new staging line
            self._reset_temp_drawing_items()

        self.current_mode = mode
        self._is_panning = (mode == InteractionMode.PANNING)
        # self._reset_temp_drawing_items() # <<<< --- MOVED THE CALL ---

        cursor_shape = Qt.CursorShape.ArrowCursor
        if mode in [InteractionMode.SET_SCALE_START, InteractionMode.SET_START_POINT, InteractionMode.SET_END_POINT,
                    InteractionMode.SET_SCALE_END, # Keep crosshair for second click
                    InteractionMode.DEFINE_AISLE_LINE_END, InteractionMode.DEFINE_STAGING_LINE_END]:
            cursor_shape = Qt.CursorShape.CrossCursor
        elif mode in [InteractionMode.DRAW_OBSTACLE, InteractionMode.DEFINE_STAGING_AREA]:
            cursor_shape = Qt.CursorShape.PointingHandCursor
        elif mode == InteractionMode.DEFINE_AISLE_LINE_START:
            cursor_shape = Qt.CursorShape.SizeVerCursor
        elif mode == InteractionMode.DEFINE_STAGING_LINE_START:
            cursor_shape = Qt.CursorShape.SizeHorCursor
        elif mode == InteractionMode.EDIT:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.set_edit_mode_flags(True)
        elif mode == InteractionMode.PANNING:
            cursor_shape = Qt.CursorShape.ClosedHandCursor
        elif mode == InteractionMode.DEFINE_PATHFINDING_BOUNDS: 
            cursor_shape = Qt.CursorShape.PointingHandCursor
            self.status_update.emit("Define Pathfinding Bounds: Click points to draw polygon. Click near start to close.", 0)
        
        if mode != InteractionMode.EDIT: # Reset drag mode if not entering edit mode
             self.setDragMode(QGraphicsView.DragMode.NoDrag)

        self.viewport().setCursor(cursor_shape)


    def set_edit_mode_flags(self, enabled: bool):
        """Sets the ItemIsMovable flag on managed items."""
        base_flags = QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        
        if enabled:
            current_flags = base_flags | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        else:
            current_flags = base_flags # Only selectable, not movable

        all_managed_polygons = self._obstacle_items + self._staging_area_items
        for item in all_managed_polygons:
            if item: # Ensure item is not None
                item.setFlags(current_flags)

        all_point_markers = [marker for marker, label in self._start_point_items.values() if marker] + \
                            [marker for marker, label in self._end_point_items.values() if marker]
        for marker in all_point_markers:
            if marker: # Ensure marker is not None
                marker.setFlags(current_flags)


    def _reset_temp_drawing_items(self):
        # ... (rest of the method unchanged) ...
        self._temp_drawing_points.clear()
        if self._temp_line_item and self._temp_line_item.scene(): self.scene().removeItem(self._temp_line_item)
        self._temp_line_item = None
        if self._temp_polygon_item and self._temp_polygon_item.scene(): self.scene().removeItem(self._temp_polygon_item)
        self._temp_polygon_item = None


    def mousePressEvent(self, event: QMouseEvent):
        # ... (rest of the method unchanged) ...
        scene_pos = self.mapToScene(event.pos())
        self._item_being_moved_in_edit = None

        if event.button() == Qt.MouseButton.MiddleButton:
            if self.current_mode in [InteractionMode.IDLE, InteractionMode.EDIT]:
                self.set_mode(InteractionMode.PANNING); self._last_pan_pos = event.position(); event.accept(); return

        if self.current_mode == InteractionMode.EDIT:
            item_under_cursor = self.itemAt(event.pos())
            if item_under_cursor and (item_under_cursor.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable):
                self._item_being_moved_in_edit = item_under_cursor
                self._item_being_moved_in_edit_start_pos = item_under_cursor.scenePos() 
            elif not item_under_cursor:
                self.rubber_band_origin = event.pos()
                self.rubber_band.setGeometry(QRectF(self.rubber_band_origin, QSize()).toRect().normalized())
                self.rubber_band.show()
            super().mousePressEvent(event); return

        if event.button() == Qt.MouseButton.LeftButton: self._handle_left_click(scene_pos)
        elif event.button() == Qt.MouseButton.RightButton: self._handle_right_click_cancel_drawing()
        else: super().mousePressEvent(event)


    def _handle_left_click(self, scene_pos: QPointF):
        # ... (rest of the method unchanged) ...
        mode_actions = {
            InteractionMode.SET_SCALE_START: lambda: self._start_line_draw(scene_pos, InteractionMode.SET_SCALE_END, self._scale_line_pen),
            InteractionMode.SET_SCALE_END: lambda: self._finish_line_draw(scene_pos, self.scale_line_drawn.emit),
            InteractionMode.DRAW_OBSTACLE: lambda: self._handle_polygon_point(scene_pos, InteractionMode.DRAW_OBSTACLE, self._obstacle_brush, self._obstacle_preview_pen),
            InteractionMode.DEFINE_STAGING_AREA: lambda: self._handle_polygon_point(scene_pos, InteractionMode.DEFINE_STAGING_AREA, self._staging_area_brush, self._staging_area_preview_pen),
            InteractionMode.DEFINE_PATHFINDING_BOUNDS: lambda: self._handle_polygon_point(scene_pos, InteractionMode.DEFINE_PATHFINDING_BOUNDS, self._bounds_brush, self._bounds_preview_pen),            
            InteractionMode.SET_START_POINT: lambda: self._request_point_placement(PointType.PICK_AISLE, scene_pos),
            InteractionMode.SET_END_POINT: lambda: self._request_point_placement(PointType.STAGING_LOCATION, scene_pos),
            InteractionMode.DEFINE_AISLE_LINE_START: lambda: self._start_line_draw(scene_pos, InteractionMode.DEFINE_AISLE_LINE_END, self._line_def_pen),
            InteractionMode.DEFINE_AISLE_LINE_END: lambda: self._finish_line_draw(scene_pos, lambda p1, p2: self.line_definition_requested.emit(PointType.PICK_AISLE, p1, p2)),
            InteractionMode.DEFINE_STAGING_LINE_START: lambda: self._start_line_draw(scene_pos, InteractionMode.DEFINE_STAGING_LINE_END, self._line_def_pen),
            InteractionMode.DEFINE_STAGING_LINE_END: lambda: self._finish_line_draw(scene_pos, lambda p1, p2: self.line_definition_requested.emit(PointType.STAGING_LOCATION, p1, p2)),
        }
        action = mode_actions.get(self.current_mode)
        if action: action()


    def _start_line_draw(self, scene_pos: QPointF, next_mode: InteractionMode, pen: QPen):
        print(f"[PdfViewer] _start_line_draw: pos={scene_pos}, next_mode={next_mode.name}") # Debug
        self._temp_drawing_points = [scene_pos]
        self._temp_line_item = QGraphicsLineItem(QLineF(scene_pos, scene_pos))
        self._temp_line_item.setPen(pen)
        self._temp_line_item.setZValue(PDF_Z_VALUE + 5) # Ensure visible above PDF for testing
        self.scene().addItem(self._temp_line_item)
        print(f"[PdfViewer] Temporary line item added to scene: {self._temp_line_item}") # Debug
        self.set_mode(next_mode)
        self.status_update.emit(f"{next_mode.name.replace('_END', '').replace('_', ' ').title()}: Click end point.", 0)

    def _finish_line_draw(self, scene_pos: QPointF, signal_emitter_func):
        if not self._temp_drawing_points:
            print("[PdfViewer] _finish_line_draw: No temp drawing points, returning.") # Debug
            return
        p1 = self._temp_drawing_points[0]; p2 = scene_pos
        print(f"[PdfViewer] _finish_line_draw: p1={p1}, p2={p2}. Emitting signal...") # Debug
        signal_emitter_func(p1, p2) # This is where scale_line_drawn.emit happens
        print("[PdfViewer] Signal emitted.") # Debug
        self._reset_temp_drawing_items()
        if self.current_mode == InteractionMode.SET_SCALE_END: self.set_mode(InteractionMode.IDLE)
        elif self.current_mode == InteractionMode.DEFINE_AISLE_LINE_END: self.set_mode(InteractionMode.DEFINE_AISLE_LINE_START)
        elif self.current_mode == InteractionMode.DEFINE_STAGING_LINE_END: self.set_mode(InteractionMode.DEFINE_STAGING_LINE_START)


    def _handle_polygon_point(self, scene_pos: QPointF, mode_type: InteractionMode, brush: QBrush, pen: QPen):
        # ... (rest of the method unchanged) ...
        is_closing = False
        if len(self._temp_drawing_points) > 2:
            if QLineF(scene_pos, self._temp_drawing_points[0]).length() < OBSTACLE_SNAP_DISTANCE:
                is_closing = True; scene_pos = self._temp_drawing_points[0]
        status_msg_base = mode_type.name.replace('_', ' ').replace("DEFINE ", "").title()        
        
        if is_closing:
            self.polygon_drawn.emit(mode_type, QPolygonF(self._temp_drawing_points))
            self._reset_temp_drawing_items()
            self.status_update.emit(f"{mode_type.name.replace('_', ' ')} polygon completed. Draw another or cancel.", 0)
            # Reset mode to IDLE after finishing bounds drawing
            if mode_type == InteractionMode.DEFINE_PATHFINDING_BOUNDS:
                 self.set_mode(InteractionMode.IDLE)
                 self.status_update.emit(f"{status_msg_base} defined.", 3000)
            else:
                 self.status_update.emit(f"{status_msg_base} polygon completed. Draw another or cancel.", 0)
        else:
            self._temp_drawing_points.append(scene_pos); n = len(self._temp_drawing_points)
            if n == 1:
                self._temp_polygon_item = QGraphicsPolygonItem(QPolygonF(self._temp_drawing_points)); self._temp_polygon_item.setBrush(brush); self._temp_polygon_item.setPen(pen); self.scene().addItem(self._temp_polygon_item)
                self._temp_line_item = QGraphicsLineItem(); self._temp_line_item.setPen(pen); self.scene().addItem(self._temp_line_item)
            elif self._temp_polygon_item: self._temp_polygon_item.setPolygon(QPolygonF(self._temp_drawing_points + [scene_pos] if n > 0 else [scene_pos])) 
            if self._temp_line_item and n > 1: self._temp_line_item.setLine(QLineF(self._temp_drawing_points[-1], scene_pos)) 

            self.status_update.emit(f"{mode_type.name.replace('_', ' ')}: Point {n} added. Click near start to close or Right-click/Esc to cancel.", 0)

    def _request_point_placement(self, point_type: PointType, scene_pos: QPointF):
        # ... (rest of the method unchanged) ...
        self.point_placement_requested.emit(point_type, scene_pos)
        self.set_mode(InteractionMode.IDLE)


    def mouseMoveEvent(self, event: QMouseEvent):
        # ... (rest of the method unchanged) ...
        scene_pos = self.mapToScene(event.pos())
        if self.current_mode == InteractionMode.PANNING and self._is_panning:
            delta = event.position() - self._last_pan_pos; self._last_pan_pos = event.position()
            hs_bar = self.horizontalScrollBar(); vs_bar = self.verticalScrollBar()
            hs_bar.setValue(hs_bar.value() - int(delta.x())); vs_bar.setValue(vs_bar.value() - int(delta.y()))
            event.accept(); return
        if self.current_mode == InteractionMode.EDIT and self.rubber_band.isVisible():
            self.rubber_band.setGeometry(QRectF(self.rubber_band_origin, event.pos()).normalized().toRect())
            super().mouseMoveEvent(event); return

        if self._temp_line_item and len(self._temp_drawing_points) == 1: self._temp_line_item.setLine(QLineF(self._temp_drawing_points[0], scene_pos))
        elif self._temp_polygon_item and self._temp_drawing_points:
            preview_poly_points = self._temp_drawing_points + [scene_pos]
            self._temp_polygon_item.setPolygon(QPolygonF(preview_poly_points))
            if len(self._temp_drawing_points) >= 1 and self._temp_line_item:
                 self._temp_line_item.setLine(QLineF(self._temp_drawing_points[-1], scene_pos))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.current_mode == InteractionMode.PANNING and event.button() == Qt.MouseButton.MiddleButton:
            self.set_mode(InteractionMode.IDLE); event.accept(); return
        if self.current_mode == InteractionMode.EDIT:
            if self.rubber_band.isVisible(): self.rubber_band.hide()
            if self._item_being_moved_in_edit and \
               self._item_being_moved_in_edit.scenePos() != self._item_being_moved_in_edit_start_pos:
                new_geometry: Any # This is where "Any" was needed
                if isinstance(self._item_being_moved_in_edit, QGraphicsPolygonItem):
                    local_poly = self._item_being_moved_in_edit.polygon()
                    new_geometry = self._item_being_moved_in_edit.sceneTransform().map(local_poly)
                elif isinstance(self._item_being_moved_in_edit, QGraphicsEllipseItem):
                    r = POINT_MARKER_RADIUS
                    new_top_left = self._item_being_moved_in_edit.scenePos()
                    new_geometry = QPointF(new_top_left.x() + r, new_top_left.y() + r)
                else: super().mouseReleaseEvent(event); self._item_being_moved_in_edit = None; return
                self.item_moved_in_edit.emit(self._item_being_moved_in_edit, new_geometry)
            self._item_being_moved_in_edit = None
            super().mouseReleaseEvent(event); return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        # ... (rest of the method unchanged) ...
        if event.key() == Qt.Key.Key_Escape: self._handle_right_click_cancel_drawing(); event.accept(); return
        if event.key() == Qt.Key.Key_Delete and self.current_mode == InteractionMode.EDIT:
            selected_items = self.scene().selectedItems()
            if selected_items: self.delete_items_requested.emit(selected_items)
            event.accept(); return
        super().keyPressEvent(event)

    def _handle_right_click_cancel_drawing(self):
        if self.current_mode not in [InteractionMode.IDLE, InteractionMode.EDIT, InteractionMode.PANNING]:
            mode_name_before_cancel = self.current_mode.name
            self._reset_temp_drawing_items() # Ensure temp items are cleared on cancel
            self.set_mode(InteractionMode.IDLE)
            self.status_update.emit(f"{mode_name_before_cancel.replace('_', ' ').title()} cancelled.", 3000)

    def wheelEvent(self, event: QWheelEvent): # Changed QEvent to QWheelEvent
        # ... (rest of the method unchanged) ...
        if self.current_mode != InteractionMode.IDLE and self.current_mode != InteractionMode.EDIT: event.ignore(); return
        if self._is_panning: event.ignore(); return
        zoom_factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.scale(zoom_factor, zoom_factor)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor) 
        self.view_changed.emit(); event.accept()

    # --- Public Methods to Add/Remove/Update Graphics ---

    def draw_pathfinding_bounds_item(self, polygon: QPolygonF):
        """Draws or updates the visual representation of the pathfinding bounds."""
        self.clear_pathfinding_bounds_item() # Clear previous one if exists
        if polygon and not polygon.isEmpty():
            self._pathfinding_bounds_item = QGraphicsPolygonItem(polygon)
            self._pathfinding_bounds_item.setPen(self._bounds_pen)
            self._pathfinding_bounds_item.setBrush(self._bounds_brush)
            self._pathfinding_bounds_item.setZValue(BOUNDS_Z_VALUE)
            self.scene().addItem(self._pathfinding_bounds_item)

    def clear_pathfinding_bounds_item(self):
        """Removes the visual pathfinding bounds item from the scene."""
        if self._pathfinding_bounds_item and self._pathfinding_bounds_item.scene():
            self.scene().removeItem(self._pathfinding_bounds_item)
        self._pathfinding_bounds_item = None    
    
    # Public Methods to Add/Remove/Update Graphics
    def add_obstacle_item(self, polygon: QPolygonF) -> QGraphicsPolygonItem:
        item = QGraphicsPolygonItem(polygon)
        item.setBrush(self._obstacle_brush)
        item.setPen(self._obstacle_pen)
        item.setZValue(OBSTACLES_Z_VALUE)
        item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable) # Default flags
        # Apply movable if currently in edit mode
        if self.current_mode == InteractionMode.EDIT:
             item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.scene().addItem(item)
        self._obstacle_items.append(item)
        return item

    def remove_obstacle_item(self, item_ref: QGraphicsPolygonItem):
        # ... (rest of the method unchanged) ...
        if item_ref in self._obstacle_items and item_ref.scene(): self.scene().removeItem(item_ref); self._obstacle_items.remove(item_ref)

    def add_staging_area_item(self, polygon: QPolygonF) -> QGraphicsPolygonItem:
        item = QGraphicsPolygonItem(polygon)
        item.setBrush(self._staging_area_brush)
        item.setPen(self._staging_area_pen)
        item.setZValue(STAGING_AREAS_Z_VALUE)
        item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable) # Default flags
        # Apply movable if currently in edit mode
        if self.current_mode == InteractionMode.EDIT:
             item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.scene().addItem(item)
        self._staging_area_items.append(item)
        return item

    def remove_staging_area_item(self, item_ref: QGraphicsPolygonItem):
        # ... (rest of the method unchanged) ...
        if item_ref in self._staging_area_items and item_ref.scene(): self.scene().removeItem(item_ref); self._staging_area_items.remove(item_ref)

    def _add_point_item(self, point_type: PointType, name: str, pos: QPointF):
        target_dict, pen, brush, prefix = (self._start_point_items, self._start_point_pen, self._start_point_brush, "Start") if point_type == PointType.PICK_AISLE else (self._end_point_items, self._end_point_pen, self._end_point_brush, "End")
        if name in target_dict:
            old_marker, _ = target_dict[name]
            if old_marker and old_marker.scene(): self.scene().removeItem(old_marker) # Label is child, will be removed too

        r = POINT_MARKER_RADIUS
        marker = QGraphicsEllipseItem(0, 0, 2 * r, 2 * r) # Origin at (0,0) for its own coordinate system
        marker.setPos(pos.x() - r, pos.y() - r) # Position its top-left in scene coordinates
        marker.setPen(pen); marker.setBrush(brush)
        marker.setToolTip(f"{prefix}: {name}")
        marker.setData(0, {"name": name, "type": point_type.value})
        marker.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable) # Default flags
        marker.setZValue(POINTS_Z_VALUE)
        # Apply movable if currently in edit mode
        if self.current_mode == InteractionMode.EDIT:
             marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        label = QGraphicsSimpleTextItem(name, parent=marker) # Child of marker
        label.setFont(self._label_font); label.setBrush(brush)
        label_rel_x = r + LABEL_OFFSET_X # Position relative to marker's local (0,0)
        label_rel_y = r + LABEL_OFFSET_Y
        label.setPos(label_rel_x, label_rel_y)

        self.scene().addItem(marker) # Adding parent marker adds child label too
        target_dict[name] = (marker, label)


    def add_pick_aisle_item(self, name: str, pos: QPointF): self._add_point_item(PointType.PICK_AISLE, name, pos)
    def add_staging_location_item(self, name: str, pos: QPointF): self._add_point_item(PointType.STAGING_LOCATION, name, pos)

    def remove_point_item(self, point_type: PointType, name: str):
        # ... (rest of the method unchanged) ...
        target_dict = self._start_point_items if point_type == PointType.PICK_AISLE else self._end_point_items
        if name in target_dict: marker, _ = target_dict[name]; (self.scene().removeItem(marker) if marker.scene() else None); del target_dict[name]

    def clear_all_points(self):
        # ... (rest of the method unchanged) ...
        for name in list(self._start_point_items.keys()): self.remove_point_item(PointType.PICK_AISLE, name)
        for name in list(self._end_point_items.keys()): self.remove_point_item(PointType.STAGING_LOCATION, name)

    def clear_obstacles(self): [self.remove_obstacle_item(item) for item in list(self._obstacle_items)]; self._obstacle_items.clear()
    def clear_staging_areas(self): [self.remove_staging_area_item(item) for item in list(self._staging_area_items)]; self._staging_area_items.clear()

    def draw_path(self, path_points: Optional[List[QPointF]]):
        # ... (rest of the method unchanged) ...
        self.clear_path()
        if not path_points or len(path_points) < 2: return
        path = QPainterPath(path_points[0]); [path.lineTo(p) for p in path_points[1:]]
        self._path_item = QGraphicsPathItem(path); self._path_item.setPen(self._path_pen); self._path_item.setZValue(PATH_Z_VALUE); self.scene().addItem(self._path_item)


    def clear_path(self):
        # ... (rest of the method unchanged) ...
        if self._path_item and self._path_item.scene(): self.scene().removeItem(self._path_item)
        self._path_item = None

    def clear_animation_overlay(self):
        if self.animation_overlay_group:
            # print(f"[PdfViewer clear_animation_overlay] Clearing {len(self.animation_overlay_group.childItems())} children from group.")
            # This is a standard way to clear a group's children
            for item in self.animation_overlay_group.childItems():
                self.scene().removeItem(item) # Removing from scene also removes from group
                # item.deleteLater() # Could be added if you suspect item leaks, but usually not needed
        # else:
        #     print("[PdfViewer clear_animation_overlay] Animation group is None, nothing to clear.")


    def update_animation_overlay(self, mode: AnimationMode, data: list):
        # print(f"[PdfViewer update_animation_overlay] Called with mode: {mode}, data count: {len(data)}")
        self.clear_animation_overlay() # Clear previous frame's items from the group
        if not self.animation_overlay_group:
            print("[PdfViewer update_animation_overlay] CRITICAL Error: Animation overlay group is None. Cannot draw.")
            return
        
        # Ensure group is visible, though it should be by default
        if not self.animation_overlay_group.isVisible():
            print("[PdfViewer update_animation_overlay] WARNING: Animation group was not visible, setting it visible.")
            self.animation_overlay_group.setVisible(True)

        # if data:
        #     print(f"[PdfViewer update_animation_overlay] Data for viewer: {data[0] if data else 'No data'}")

        if mode == AnimationMode.CARTS:
            self._draw_animation_carts(data)
        elif mode == AnimationMode.PATH_LINES:
            self._draw_animation_paths(data)
        
        # Optional: Force an update of the group's bounding rect if items changed significantly
        # self.animation_overlay_group.prepareGeometryChange()
        # self.scene().update() # May not be necessary, Qt usually handles this

    # ... (Keep _draw_animation_carts and _draw_animation_paths as debugged in the previous step)

    def _draw_animation_carts(self, active_carts_data: list):
        if not self.animation_overlay_group: return
        if not active_carts_data: return # Added check
        
        for i, cart_data in enumerate(active_carts_data):
            pos, angle, width_px, length_px = cart_data['pos'], cart_data['angle'], cart_data['width'], cart_data['length']
            
            if width_px <= 0.1 or length_px <= 0.1: # More lenient for small scales
                if i < 2: print(f"  Skipping cart {i} due to zero/small size.")
                continue

            cart_rect = QGraphicsRectItem(-length_px / 2, -width_px / 2, length_px, width_px)
            cart_rect.setBrush(QColor(255, 100, 0, 180)); cart_rect.setPen(Qt.PenStyle.NoPen)
            cart_rect.setTransform(QTransform().translate(pos.x(), pos.y()).rotate(angle))
            self.animation_overlay_group.addToGroup(cart_rect)


    def _draw_animation_paths(self, active_paths_data: list):
        if not self.animation_overlay_group: return
        if not active_paths_data: return # Added check

        if not hasattr(self, '_cluster_color_map'): self._cluster_color_map = {}
        # ... (cluster_colors list)
        cluster_colors = [QColor("blue"), QColor("red"), QColor("darkGreen"), QColor("purple"), QColor("orange"), QColor("teal"), QColor("maroon"), QColor("navy"), QColor("olive"), QColor("deeppink")]


        for i, path_data in enumerate(active_paths_data):
            points, draw_prog, alpha, cluster = path_data['points'], path_data['draw_progress'], path_data['alpha'], path_data.get('start_cluster', "default")

            if not points or len(points) < 2 or alpha <= 0:
                if i < 2: print(f"  Skipping path {i} due to no points/alpha.")
                continue

            # ... (rest of path drawing logic) ...
            if cluster not in self._cluster_color_map: self._cluster_color_map[cluster] = cluster_colors[len(self._cluster_color_map) % len(cluster_colors)]
            path_color = self._cluster_color_map[cluster]
            path_to_draw = QPainterPath(points[0])
            total_segments = len(points) - 1
            if total_segments == 0: continue
            length_to_draw_in_segments = draw_prog * total_segments
            for seg_idx in range(total_segments):
                current_segment_progress_val = length_to_draw_in_segments - seg_idx
                if current_segment_progress_val <= 0: break
                p_start, p_end = points[seg_idx], points[seg_idx+1]
                if current_segment_progress_val >= 1.0: path_to_draw.lineTo(p_end)
                else: path_to_draw.lineTo(p_start + (p_end - p_start) * current_segment_progress_val); break
            path_item = QGraphicsPathItem(path_to_draw)
            color_with_alpha = QColor(path_color); color_with_alpha.setAlpha(alpha)
            pen = QPen(color_with_alpha, 2); pen.setCosmetic(True); path_item.setPen(pen)
            self.animation_overlay_group.addToGroup(path_item)
        

# --- END OF FILE Warehouse-Path-Finder-main/pdf_viewer.py ---