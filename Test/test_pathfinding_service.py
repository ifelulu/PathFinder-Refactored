import pytest
import numpy as np
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPolygonF

from model import WarehouseModel
from services import PathfindingService # Assuming services.py is accessible
# from pathfinding import COST_OBSTACLE # If needed for direct grid checks

@pytest.fixture
def model_with_pdf_and_scale():
    model = WarehouseModel()
    # Simulate PDF loading and scale setting
    model._current_pdf_path = "dummy.pdf" # Internal set to bypass signals for fixture
    model._pdf_bounds = QRectF(0, 0, 800, 600)
    model._scale_pixels_per_unit = 10.0
    model._calibration_unit = "meters"
    return model

@pytest.fixture
def pathfinding_service():
    return PathfindingService()

def test_update_grid_no_pdf(pathfinding_service):
    model = WarehouseModel() # No PDF
    assert not pathfinding_service.update_grid(model)
    assert model.pathfinding_grid is None

def test_update_grid_no_scale(pathfinding_service):
    model = WarehouseModel()
    model._current_pdf_path = "dummy.pdf"
    model._pdf_bounds = QRectF(0,0,100,100)
    # No scale set
    assert not pathfinding_service.update_grid(model)
    assert model.pathfinding_grid is None

def test_update_grid_success(pathfinding_service, model_with_pdf_and_scale, qtbot):
    model = model_with_pdf_and_scale # Already has PDF, bounds, and scale
    with qtbot.waitSignal(pathfinding_service.grid_update_finished, timeout=500) as blocker:
        assert pathfinding_service.update_grid(model)
    assert blocker.args == [True]
    assert model.pathfinding_grid is not None
    assert model.pathfinding_grid.shape == (int(600 / model.grid_resolution_factor),
                                           int(800 / model.grid_resolution_factor))
    assert not model.grid_is_valid # Grid is made, but maps are not, so still not "fully" valid for calcs

def test_precompute_no_grid(pathfinding_service, model_with_pdf_and_scale, qtbot):
    # Model has PDF and scale, but grid not yet computed by service
    model_with_pdf_and_scale.add_pick_aisle("A1", QPointF(10,10)) # Need a start point
    
    with qtbot.waitSignal(pathfinding_service.precomputation_finished, timeout=1000) as blocker_precomp:
        # update_grid will be called internally by precompute_all_paths
        pathfinding_service.precompute_all_paths(model_with_pdf_and_scale)

    assert model_with_pdf_and_scale.pathfinding_grid is not None # Grid should have been made
    assert "A1" in model_with_pdf_and_scale.path_maps
    assert model_with_pdf_and_scale.grid_is_valid # Should be valid now
    assert blocker_precomp.args[0] is True # Success
    assert len(blocker_precomp.args[1]) == 0 # No failed points


def test_get_shortest_path_no_precomp(pathfinding_service, model_with_pdf_and_scale):
    model_with_pdf_and_scale.add_pick_aisle("A1", QPointF(10,10))
    model_with_pdf_and_scale.add_staging_location("S1", QPointF(100,100))
    # Grid and maps are not valid yet
    path, dist = pathfinding_service.get_shortest_path(model_with_pdf_and_scale, "A1", "S1")
    assert path is None
    assert dist is None

def test_get_shortest_path_simple(pathfinding_service, model_with_pdf_and_scale, qtbot):
    model = model_with_pdf_and_scale
    model.add_pick_aisle("A1", QPointF(10, 10))
    model.add_staging_location("S1", QPointF(50, 50))

    # Manually trigger grid update and precomputation
    assert pathfinding_service.update_grid(model) # First update grid
    with qtbot.waitSignal(pathfinding_service.precomputation_finished, timeout=1000):
        pathfinding_service.precompute_all_paths(model) # Then precompute

    path_points, distance = pathfinding_service.get_shortest_path(model, "A1", "S1")
    assert path_points is not None
    assert distance is not None
    assert distance > 0

# ... More tests for obstacles blocking paths, paths through staging areas (penalty), etc.
# ... Tests for multiprocessing (these are harder, may need to check emitted signals for progress)