import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPolygonF

# Assuming model.py is in the same directory or python path
from model import WarehouseModel

@pytest.fixture
def fresh_model():
    """Provides a fresh WarehouseModel instance for each test."""
    return WarehouseModel()

def test_model_initial_state(fresh_model):
    assert fresh_model.current_pdf_path is None
    assert fresh_model.scale_pixels_per_unit is None
    assert fresh_model.display_unit == "meters"
    assert len(fresh_model.obstacles) == 0
    assert not fresh_model.grid_is_valid
    assert not fresh_model.is_saveable

def test_set_pdf_path(fresh_model, qtbot):
    test_path = "test.pdf"
    test_bounds = QRectF(0, 0, 100, 100)
    with qtbot.waitSignal(fresh_model.pdf_path_changed, timeout=100) as blocker:
        fresh_model.set_pdf_path_and_bounds(test_path, test_bounds)
    assert blocker.args == [test_path]
    assert fresh_model.current_pdf_path == test_path
    assert fresh_model.pdf_bounds == test_bounds
    assert fresh_model.is_saveable # Becomes saveable after PDF is set

def test_add_obstacle(fresh_model, qtbot):
    obstacle_poly = QPolygonF([QPointF(0,0), QPointF(10,0), QPointF(10,10)])
    with qtbot.waitSignals([fresh_model.layout_changed, fresh_model.grid_invalidated], timeout=100):
        fresh_model.add_obstacle(obstacle_poly)
    assert len(fresh_model.obstacles) == 1
    assert fresh_model.obstacles[0] == obstacle_poly
    assert not fresh_model.grid_is_valid # Grid should be invalidated

def test_add_pick_aisle(fresh_model, qtbot):
    point_name = "A1"
    point_pos = QPointF(50, 50)
    with qtbot.waitSignals([fresh_model.points_changed, fresh_model.grid_invalidated], timeout=100):
        assert fresh_model.add_pick_aisle(point_name, point_pos)
    assert point_name in fresh_model.pick_aisles
    assert fresh_model.pick_aisles[point_name] == point_pos
    assert not fresh_model.grid_is_valid

def test_set_scale(fresh_model, qtbot):
    with qtbot.waitSignals([fresh_model.scale_changed, fresh_model.grid_invalidated], timeout=100) as blocker:
        fresh_model.set_scale(10.5, "feet")
    assert blocker.args == [10.5, "feet", "meters"] # display_unit is still meters
    assert fresh_model.scale_pixels_per_unit == 10.5
    assert fresh_model.calibration_unit == "feet"
    assert not fresh_model.grid_is_valid

def test_model_reset(fresh_model, qtbot):
    fresh_model.set_pdf_path_and_bounds("dummy.pdf", QRectF(0,0,1,1))
    fresh_model.add_obstacle(QPolygonF())
    with qtbot.waitSignal(fresh_model.model_reset, timeout=100):
        fresh_model.reset()
    test_model_initial_state(fresh_model) # Should be back to initial state

# ... More tests for other setters, property logic, complex interactions ...