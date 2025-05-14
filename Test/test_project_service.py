import pytest
import os
import json
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPolygonF

from model import WarehouseModel
from services import ProjectService

@pytest.fixture
def populated_model():
    model = WarehouseModel()
    model._current_pdf_path = "test_layout.pdf"
    model._pdf_bounds = QRectF(0,0,1000,800)
    model.set_scale(10.0, "meters")
    model.set_display_unit("feet")
    model.set_grid_resolution_factor(1.5)
    model.set_staging_area_penalty(15.0)
    model.add_obstacle(QPolygonF([QPointF(10,10), QPointF(20,10), QPointF(10,20)]))
    model.add_staging_area(QPolygonF([QPointF(30,30), QPointF(40,30), QPointF(30,40)]))
    model.add_pick_aisle("A1", QPointF(5,5))
    model.add_staging_location("S1", QPointF(90,90))
    return model

@pytest.fixture
def project_service():
    return ProjectService()

def test_save_and_load_project(project_service, populated_model, tmp_path, qtbot):
    file_path = tmp_path / "test_project.whp"

    # Save
    with qtbot.waitSignal(project_service.project_operation_finished, timeout=500):
        assert project_service.save_project(populated_model, str(file_path))
    assert os.path.exists(file_path)

    # Verify content partially (optional, more thorough checks can be added)
    with open(file_path, 'r') as f:
        saved_data = json.load(f)
    assert saved_data["version"] == "1.3"
    assert saved_data["pdf_path"] == "test_layout.pdf"
    assert saved_data["scale_info"]["display_unit"] == "feet"
    assert len(saved_data["obstacles"]) == 1

    # Load
    with qtbot.waitSignal(project_service.project_operation_finished, timeout=500):
         loaded_model = project_service.load_project(str(file_path))

    assert loaded_model is not None
    assert loaded_model.current_pdf_path == populated_model.current_pdf_path
    assert loaded_model.scale_pixels_per_unit == populated_model.scale_pixels_per_unit
    assert loaded_model.display_unit == populated_model.display_unit
    assert len(loaded_model.obstacles) == len(populated_model.obstacles)
    assert len(loaded_model.staging_areas) == len(populated_model.staging_areas)
    assert "A1" in loaded_model.pick_aisles
    assert "S1" in loaded_model.staging_locations
    assert not loaded_model.grid_is_valid # Grid should be invalidated on load

def test_load_invalid_project(project_service, tmp_path, qtbot):
    invalid_file = tmp_path / "invalid.whp"
    with open(invalid_file, "w") as f:
        f.write("this is not json")

    with qtbot.waitSignal(project_service.project_load_failed, timeout=100):
        loaded_model = project_service.load_project(str(invalid_file))
    assert loaded_model is None

# ... More tests for edge cases, missing fields in JSON, etc. ...