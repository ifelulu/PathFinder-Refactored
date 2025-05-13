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
OBSTACLE_DILATION_ITERATIONS = 2 # How many pixels to "thicken" obstacles
DEFAULT_RESOLUTION_FACTOR = 1.0
DEFAULT_STAGING_PENALTY = 10.0

def create_grid_from_obstacles(width: int, height: int, obstacles: list[QPolygonF],
                               resolution_factor: float = DEFAULT_RESOLUTION_FACTOR,
                               staging_areas: list[QPolygonF] | None = None,
                               staging_penalty: float = DEFAULT_STAGING_PENALTY) -> np.ndarray | None:
    """Creates a cost grid representation of the warehouse layout.

    Grid Values represent movement cost:
        - COST_EMPTY (e.g., 1.0): Base cost for free space.
        - COST_EMPTY + staging_penalty: Cost for entering a staging area cell.
        - COST_OBSTACLE (inf): Impassable obstacle cell.
    """
    if width <= 0 or height <= 0:
        print(f"[Pathfinding] Error: Invalid grid dimensions ({width}x{height}).")
        return None
    print(f"[Pathfinding] Creating cost grid ({width}x{height}) at {resolution_factor=:.1f} from {len(obstacles)} obstacles and {len(staging_areas or [])} staging areas...")

    try:
        # 1. Initialize grid with base cost (use float for inf/penalties)
        grid = np.full((height, width), COST_EMPTY, dtype=np.float32)

        scale_factor = 1.0 / resolution_factor
        transform = QTransform().scale(scale_factor, scale_factor)

        # 2. Rasterize Staging Areas (Apply penalty)
        if staging_areas:
            print(f"[Pathfinding] Rasterizing staging areas with penalty {staging_penalty}...")
            staging_cost = COST_EMPTY + staging_penalty
            # Use a boolean mask for efficiency
            staging_mask = np.zeros((height, width), dtype=bool)
            staging_image = QImage(width, height, QImage.Format_Mono) # Use Mono for boolean mask
            staging_image.fill(0) # 0 = False (not staging)
            painter = QPainter(staging_image)
            painter.setBrush(Qt.GlobalColor.color1) # 1 = True (is staging)
            painter.setPen(Qt.GlobalColor.color1)
            for polygon in staging_areas:
                scaled_polygon = transform.map(polygon)
                painter.drawPolygon(scaled_polygon)
            painter.end()

            # Convert QImage to numpy boolean mask
            # Pointer math might be faster but less portable/safe
            for r in range(height):
                for c in range(width):
                    if staging_image.pixelIndex(c, r) == 1:
                        staging_mask[r, c] = True
            grid[staging_mask] = staging_cost # Apply penalty where mask is True
            print("[Pathfinding] Staging areas rasterized.")

        # 3. Rasterize Obstacles (Apply infinite cost, overwrites staging)
        print("[Pathfinding] Rasterizing obstacles...")
        # Use a boolean mask for obstacles as well
        obstacle_mask = np.zeros((height, width), dtype=bool)
        obstacle_image = QImage(width, height, QImage.Format_Mono)
        obstacle_image.fill(0) # 0 = False (not obstacle)
        painter = QPainter(obstacle_image)
        painter.setBrush(Qt.GlobalColor.color1) # 1 = True (is obstacle)
        painter.setPen(Qt.GlobalColor.color1)
        for polygon in obstacles:
            scaled_polygon = transform.map(polygon)
            painter.drawPolygon(scaled_polygon)
        painter.end()

        # Convert QImage to numpy boolean mask
        for r in range(height):
            for c in range(width):
                if obstacle_image.pixelIndex(c, r) == 1:
                    obstacle_mask[r, c] = True

        print("[Pathfinding] Obstacles rasterized.")

        # 4. Dilate obstacles (optional thickening)
        if OBSTACLE_DILATION_ITERATIONS > 0:
            print(f"[Pathfinding] Dilating obstacles by {OBSTACLE_DILATION_ITERATIONS} iterations...")
            structure = generate_binary_structure(2, 2) # Allows diagonal dilation
            dilated_mask = binary_dilation(obstacle_mask, structure=structure, iterations=OBSTACLE_DILATION_ITERATIONS)
            print("[Pathfinding] Dilation complete.")
            grid[dilated_mask] = COST_OBSTACLE # Apply infinite cost to dilated areas
        else:
            grid[obstacle_mask] = COST_OBSTACLE # Apply infinite cost only to original obstacle areas
            print("[Pathfinding] Obstacle dilation skipped.")

        return grid

    except Exception as e:
        print(f"[Pathfinding] Error during grid creation: {e}")
        import traceback
        traceback.print_exc()
        return None


def dijkstra_precompute(grid: np.ndarray, start_cell: tuple[int, int]) -> tuple[np.ndarray, np.ndarray | None]:
    """Performs Dijkstra's algorithm from a start cell on a cost grid."""
    rows, cols = grid.shape
    if not (0 <= start_cell[0] < rows and 0 <= start_cell[1] < cols) or grid[start_cell] == COST_OBSTACLE:
        print(f"[Pathfinding] Error: Invalid start cell {start_cell} for Dijkstra.")
        # Return arrays indicating no path possible
        invalid_dist = np.full((rows, cols), np.inf, dtype=np.float32)
        invalid_pred = np.full((rows, cols, 2), -1, dtype=np.int32) # Use (row, col) pairs
        return invalid_dist, invalid_pred

    distance_grid = np.full((rows, cols), np.inf, dtype=np.float32)
    # Store predecessors as (row, col) tuples, use int32 for indices
    predecessor_grid = np.full((rows, cols, 2), -1, dtype=np.int32)

    distance_grid[start_cell] = 0
    pq = [(0.0, start_cell)] # Priority queue: (distance, (row, col))

    # Using 4 cardinal directions for grid movement
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    while pq:
        d, current_cell = heapq.heappop(pq)
        cr, cc = current_cell

        if d > distance_grid[cr, cc] + EPSILON: # Use tolerance for float comparison
            continue

        for dr, dc in directions:
            nr, nc = cr + dr, cc + dc
            neighbor_cell = (nr, nc)

            if 0 <= nr < rows and 0 <= nc < cols:
                move_cost = grid[nr, nc]
                # Check if neighbor is passable (cost is not infinite)
                if move_cost != COST_OBSTACLE:
                    new_distance = distance_grid[cr, cc] + move_cost
                    if new_distance < distance_grid[nr, nc] - EPSILON: # Use tolerance
                        distance_grid[nr, nc] = new_distance
                        predecessor_grid[nr, nc, 0] = cr # Store predecessor row
                        predecessor_grid[nr, nc, 1] = cc # Store predecessor col
                        heapq.heappush(pq, (new_distance, neighbor_cell))

    return distance_grid, predecessor_grid


def reconstruct_path(predecessor_grid: np.ndarray, start_cell: tuple[int, int], end_cell: tuple[int, int]) -> list[tuple[int, int]] | None:
    """Reconstructs the shortest path from the predecessor grid."""
    path = []
    current_r, current_c = end_cell

    # Check if end_cell is reachable (predecessor is not [-1, -1] unless it's the start cell itself)
    if predecessor_grid[current_r, current_c, 0] == -1 and (current_r, current_c) != start_cell:
        return None # End cell was not reached

    max_steps = predecessor_grid.shape[0] * predecessor_grid.shape[1] # Safety limit
    steps = 0

    while (current_r, current_c) != start_cell and steps < max_steps:
        path.append((current_r, current_c))
        pred_r, pred_c = predecessor_grid[current_r, current_c]

        if pred_r == -1: # Reached start or an invalid state
             print(f"[Pathfinding] Warning: Path reconstruction hit -1 predecessor before start cell at {(current_r, current_c)}")
             return None # Path broken

        current_r, current_c = pred_r, pred_c
        steps += 1

    if steps >= max_steps:
        print("[Pathfinding] Error: Path reconstruction exceeded max steps, possible loop.")
        return None

    if (current_r, current_c) == start_cell:
        path.append(start_cell) # Add the start cell
        return path[::-1] # Reverse to get path from start to end
    else:
        print("[Pathfinding] Warning: Path reconstruction did not reach start cell.")
        return None # Path reconstruction failed


# --- END OF FILE Warehouse-Path-Finder-main/pathfinding.py ---