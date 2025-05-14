# --- START OF FILE Warehouse-Path-Finder-main/pathfinding.py ---
# (Minor changes: Ensure COST_OBSTACLE is consistently np.inf, add comments)

import math
import numpy as np
from PySide6.QtCore import Qt, QPointF, QLineF
from PySide6.QtGui import QPolygonF, QImage, QPainter, QColor, QTransform # <<< QPolygonF from QtGui
# collections.deque is not used in the last version, heapq is.
import heapq
from scipy.ndimage import binary_dilation, generate_binary_structure

# Tolerance for floating point comparisons
EPSILON = 1e-6

# --- Constants for Grid Costs ---
COST_EMPTY = 1.0         # Base cost for moving through an empty cell
COST_OBSTACLE = np.inf   # Cost for impassable obstacle cells

# --- Geometric Helper Functions (Unchanged) ---
def on_segment(p: QPointF, q: QPointF, r: QPointF) -> bool:
    """Check if point q lies on segment pr."""
    # Check bounding box first for efficiency
    if (q.x() < min(p.x(), r.x()) - EPSILON or q.x() > max(p.x(), r.x()) + EPSILON or
            q.y() < min(p.y(), r.y()) - EPSILON or q.y() > max(p.y(), r.y()) + EPSILON):
        return False
    # Check collinearity using cross-product (should be close to zero)
    val = (q.y() - p.y()) * (r.x() - q.x()) - (q.x() - p.x()) * (r.y() - q.y())
    return abs(val) < EPSILON

def orientation(p: QPointF, q: QPointF, r: QPointF) -> int:
    """Find orientation of ordered triplet (p, q, r).
    Returns: 0 (Collinear), 1 (Clockwise), 2 (Counterclockwise).
    """
    val = (q.y() - p.y()) * (r.x() - q.x()) - (q.x() - p.x()) * (r.y() - q.y())
    if abs(val) < EPSILON: return 0
    return 1 if val > 0 else 2

def segments_intersect(p1: QPointF, q1: QPointF, p2: QPointF, q2: QPointF) -> bool:
    """Check if line segment 'p1q1' and 'p2q2' intersect."""
    o1 = orientation(p1, q1, p2)
    o2 = orientation(p1, q1, q2)
    o3 = orientation(p2, q2, p1)
    o4 = orientation(p2, q2, q1)

    if o1 != o2 and o3 != o4: return True # General case

    # Special Cases for collinear points lying on segments
    if o1 == 0 and on_segment(p1, p2, q1): return True
    if o2 == 0 and on_segment(p1, q2, q1): return True
    if o3 == 0 and on_segment(p2, p1, q2): return True
    if o4 == 0 and on_segment(p2, q1, q2): return True

    return False

def point_in_polygon(point: QPointF, polygon: list[QPointF]) -> bool:
    """Check if a point is inside a polygon using the Ray Casting algorithm."""
    n = len(polygon)
    if n < 3: return False
    inside = False
    p1x, p1y = polygon[0].x(), polygon[0].y()
    for i in range(n + 1):
        p2x, p2y = polygon[i % n].x(), polygon[i % n].y()
        if point.y() > min(p1y, p2y):
            if point.y() <= max(p1y, p2y):
                if point.x() <= max(p1x, p2x):
                    if abs(p1y - p2y) > EPSILON: # Avoid division by zero
                        xinters = (point.y() - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or point.x() <= xinters + EPSILON:
                            inside = not inside
                    elif point.x() <= p1x + EPSILON: # Handle horizontal edges
                        inside = not inside
        p1x, p1y = p2x, p2y
    # Check boundary inclusion separately if needed (original included it)
    # for i in range(n):
    #     if on_segment(polygon[i], point, polygon[(i + 1) % n]):
    #          return True # Point is on boundary
    return inside


# --- Grid Creation Parameters ---
OBSTACLE_DILATION_ITERATIONS = 2 # How many pixels to "thicken" obstacles (default is 2)
DEFAULT_RESOLUTION_FACTOR = 1.0
DEFAULT_STAGING_PENALTY = 10.0

def create_grid_from_obstacles(width: int, height: int, obstacles_pdf_list: list[QPolygonF],
                               resolution_factor: float, # Removed default
                               grid_origin_pdf: QPointF,                              
                               staging_areas_pdf_list: list[QPolygonF] | None = None,
                               staging_penalty: float = DEFAULT_STAGING_PENALTY) -> np.ndarray | None:
    """Creates a cost grid representation of the warehouse layout.

    Grid Values represent movement cost:
        - COST_EMPTY (e.g., 1.0): Base cost for free space.
        - COST_EMPTY + staging_penalty: Cost for entering a staging area cell.
        - COST_OBSTACLE (inf): Impassable obstacle cell.
    """
    if width <= 0 or height <= 0:
        print(f"[Pathfinding create_grid] Error: Invalid grid dimensions for QImage ({width}x{height}).")
        return None
    print(f"[Pathfinding create_grid] Creating cost grid ({width}x{height}) using Grayscale8 rasterization...")

    try:
        grid = np.full((height, width), COST_EMPTY, dtype=np.float32)
        scale_factor = 1.0 / resolution_factor
        
        # --- EXPLICIT TRANSFORM CONSTRUCTION ---
        # We want: x_img = scale_factor * x_pdf + (-scale_factor * grid_origin_pdf.x())
        #          y_img = scale_factor * y_pdf + (-scale_factor * grid_origin_pdf.y())
        
        m11 = scale_factor
        m12 = 0.0
        m13_dx = scale_factor * (-grid_origin_pdf.x()) # This is the effective dx

        m21 = 0.0
        m22 = scale_factor
        m23_dy = scale_factor * (-grid_origin_pdf.y()) # This is the effective dy

        m31 = 0.0 # Not used by QTransform.map for 2D points directly
        m32 = 0.0 # Not used by QTransform.map for 2D points directly
        m33 = 1.0

        pdf_to_grid_image_transform = QTransform(m11, m12, m13_dx,  # Qt uses m13 for dx in constructor sometimes
                                                 m21, m22, m23_dy,  # Qt uses m23 for dy in constructor sometimes
                                                 m31, m32, m33)
        # QTransform constructor: QTransform(qreal m11, qreal m12, qreal m13, qreal m21, qreal m22, qreal m23, qreal m31, qreal m32, qreal m33 = 1.0)
        # For 2D, m13 is dx, m23 is dy. m31, m32 are for perspective.
        # So we should use:
        pdf_to_grid_image_transform = QTransform(
            scale_factor, 0.0,  # m11, m12
            0.0, scale_factor, # m21, m22
            -grid_origin_pdf.x() * scale_factor,  # dx
            -grid_origin_pdf.y() * scale_factor   # dy
        )
        # This sets: x' = m11*x + m21*y + dx  => scale_factor*x + 0*y + (-origin_x*scale_factor)
        #            y' = m12*x + m22*y + dy  => 0*x + scale_factor*y + (-origin_y*scale_factor)

        # --- END EXPLICIT TRANSFORM ---
        
        print(f"[Pathfinding create_grid] PDF-to-GridImage Transform (Explicit Construction): ")
        print(f"  Grid Origin PDF: ({grid_origin_pdf.x():.2f}, {grid_origin_pdf.y():.2f}), Scale Factor: {scale_factor:.2f}")
        print(f"  Target dx: {-grid_origin_pdf.x() * scale_factor:.4f}, Target dy: {-grid_origin_pdf.y() * scale_factor:.4f}")
        print(f"  Actual Transform Matrix (from QTransform object):")
        print(f"    m11={pdf_to_grid_image_transform.m11():.4f}, m12={pdf_to_grid_image_transform.m12():.4f}, dx={pdf_to_grid_image_transform.dx():.4f}")
        print(f"    m21={pdf_to_grid_image_transform.m21():.4f}, m22={pdf_to_grid_image_transform.m22():.4f}, dy={pdf_to_grid_image_transform.dy():.4f}")


        paint_color = QColor(255, 255, 255) 
        background_color_val = 0

        # # --- DEBUG: Test rasterization of the FIRST obstacle ONLY ---
        # if obstacles_pdf_list: # Use the new parameter name
        #     # ... (debug print block as before, using this newly defined pdf_to_grid_image_transform) ...
        #     first_obstacle_from_input_list_pdf = obstacles_pdf_list[0]
            
        #     print(f"[Pathfinding DEBUG] First Obstacle from input list (PDF Coords): "
        #           f"{[(p.x(), p.y()) for p in first_obstacle_from_input_list_pdf]}")
            
        #     if not first_obstacle_from_input_list_pdf.isEmpty():
        #         p0_pdf = first_obstacle_from_input_list_pdf.at(0)
        #         manual_p0_transformed_x = (p0_pdf.x() - grid_origin_pdf.x()) * scale_factor
        #         manual_p0_transformed_y = (p0_pdf.y() - grid_origin_pdf.y()) * scale_factor
        #         print(f"[Pathfinding DEBUG] Manual transform of p0: PDF({p0_pdf.x():.2f}, {p0_pdf.y():.2f}) "
        #               f"-> Expected QImage Coords ({manual_p0_transformed_x:.2f}, {manual_p0_transformed_y:.2f})")
            
        #     first_obstacle_transformed_for_qimage = pdf_to_grid_image_transform.map(first_obstacle_from_input_list_pdf)
        #     print(f"[Pathfinding DEBUG] First Obstacle Transformed Coords (for QImage using QTransform.map): "
        #           f"{[(p.x(), p.y()) for p in first_obstacle_transformed_for_qimage]}")

        #     if width > 0 and height > 0:
        #         test_obstacle_image = QImage(width, height, QImage.Format.Format_Grayscale8)
        #         test_obstacle_image.fill(background_color_val)
        #         test_painter = QPainter(test_obstacle_image)
        #         test_painter.setPen(paint_color)
        #         test_painter.setBrush(paint_color)
        #         test_painter.drawPolygon(first_obstacle_transformed_for_qimage)
        #         test_painter.end()
        #         test_obstacle_image.save("debug_raster_FIRST_OBSTACLE_ONLY.png")
        #         print("[Pathfinding DEBUG] Saved debug_raster_FIRST_OBSTACLE_ONLY.png")
        #     else:
        #         print("[Pathfinding DEBUG] Cannot save FIRST_OBSTACLE_ONLY image due to invalid grid dimensions.")
        # # --- END DEBUG SECTION ---

        # 2. Rasterize Staging Areas
        if staging_areas_pdf_list:
            print(f"[Pathfinding create_grid] Rasterizing staging areas (Grayscale)...")
            staging_cost = COST_EMPTY + staging_penalty
            staging_mask = np.zeros((height, width), dtype=bool)
            staging_image = QImage(width, height, QImage.Format.Format_Grayscale8)
            staging_image.fill(background_color_val)
            painter = QPainter(staging_image)
            painter.setPen(paint_color)
            painter.setBrush(paint_color)
            for polygon in staging_areas_pdf_list:
                scaled_polygon = pdf_to_grid_image_transform.map(polygon)
                painter.drawPolygon(scaled_polygon)
            painter.end()
            for r_idx in range(height):
                for c_idx in range(width):
                    if staging_image.pixelColor(c_idx, r_idx).value() > 128:
                        staging_mask[r_idx, c_idx] = True
            grid[staging_mask] = staging_cost
            print(f"[Pathfinding create_grid] Staging areas rasterized. Mask sum: {np.sum(staging_mask)}")


        # 3. Rasterize Obstacles
        print("[Pathfinding create_grid] Rasterizing obstacles (Grayscale)...")
        obstacle_mask = np.zeros((height, width), dtype=bool)
        obstacle_image = QImage(width, height, QImage.Format.Format_Grayscale8)
        obstacle_image.fill(background_color_val)
        painter = QPainter(obstacle_image)
        painter.setPen(paint_color)
        painter.setBrush(paint_color)
        if obstacles_pdf_list:
            for polygon in obstacles_pdf_list:
                scaled_polygon = pdf_to_grid_image_transform.map(polygon)
                painter.drawPolygon(scaled_polygon)
        painter.end()
        for r_idx in range(height):
            for c_idx in range(width):
                if obstacle_image.pixelColor(c_idx, r_idx).value() > 128:
                    obstacle_mask[r_idx, c_idx] = True
        print(f"[Pathfinding create_grid] Obstacles rasterized. Mask sum: {np.sum(obstacle_mask)}")


        # 4. Dilate obstacles
        if OBSTACLE_DILATION_ITERATIONS > 0 and np.any(obstacle_mask):
            print(f"[Pathfinding create_grid] Dilating obstacles by {OBSTACLE_DILATION_ITERATIONS} iterations...")
            structure = generate_binary_structure(2, 2)
            dilated_mask = binary_dilation(obstacle_mask, structure=structure, iterations=OBSTACLE_DILATION_ITERATIONS)
            print(f"[Pathfinding create_grid] Dilation complete. Dilated mask sum: {np.sum(dilated_mask)}")
            grid[dilated_mask] = COST_OBSTACLE
        elif np.any(obstacle_mask):
            grid[obstacle_mask] = COST_OBSTACLE
            print("[Pathfinding create_grid] Obstacle dilation skipped, applied original obstacles.")
        else:
            print("[Pathfinding create_grid] No obstacles to dilate or apply.")

        return grid

    except Exception as e:
        print(f"[Pathfinding create_grid] Error during grid creation: {e}")
        import traceback
        traceback.print_exc()
        return None

# --- Other pathfinding functions ---
def dijkstra_precompute(grid: np.ndarray, start_cell: tuple[int, int]) -> tuple[np.ndarray, np.ndarray | None]:
    # ... (implementation as before) ...
    rows, cols = grid.shape
    if not (0 <= start_cell[0] < rows and 0 <= start_cell[1] < cols) or grid[start_cell] == COST_OBSTACLE:
        invalid_dist = np.full((rows, cols), np.inf, dtype=np.float32)
        invalid_pred = np.full((rows, cols, 2), -1, dtype=np.int32)
        return invalid_dist, invalid_pred
    distance_grid = np.full((rows, cols), np.inf, dtype=np.float32)
    predecessor_grid = np.full((rows, cols, 2), -1, dtype=np.int32)
    distance_grid[start_cell] = 0
    pq = [(0.0, start_cell)]
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    while pq:
        d, current_cell = heapq.heappop(pq)
        cr, cc = current_cell
        if d > distance_grid[cr, cc] + EPSILON:
            continue
        for dr, dc in directions:
            nr, nc = cr + dr, cc + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                move_cost = grid[nr, nc]
                if move_cost != COST_OBSTACLE:
                    new_distance = distance_grid[cr, cc] + move_cost
                    if new_distance < distance_grid[nr, nc] - EPSILON:
                        distance_grid[nr, nc] = new_distance
                        predecessor_grid[nr, nc, 0] = cr
                        predecessor_grid[nr, nc, 1] = cc
                        heapq.heappush(pq, (new_distance, (nr, nc)))
    return distance_grid, predecessor_grid

def reconstruct_path(predecessor_grid: np.ndarray, start_cell: tuple[int, int], end_cell: tuple[int, int]) -> list[tuple[int, int]] | None:
    # ... (implementation as before) ...
    path = []
    current_r, current_c = end_cell
    if predecessor_grid[current_r, current_c, 0] == -1 and (current_r, current_c) != start_cell:
        return None 
    max_steps = predecessor_grid.shape[0] * predecessor_grid.shape[1]
    steps = 0
    while (current_r, current_c) != start_cell and steps < max_steps:
        path.append((current_r, current_c))
        pred_r, pred_c = predecessor_grid[current_r, current_c]
        if pred_r == -1:
             return None
        current_r, current_c = pred_r, pred_c
        steps += 1
    if steps >= max_steps:
        return None
    if (current_r, current_c) == start_cell:
        path.append(start_cell)
        return path[::-1]
    else:
        return None

# --- END OF FILE Warehouse-Path-Finder-main/pathfinding.py ---