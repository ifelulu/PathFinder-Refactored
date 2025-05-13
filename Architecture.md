# Warehouse Path Finder - System Architecture (v2.0)

## 1. System Overview

The Warehouse Path Finder is a desktop application built with Python and PySide6 (Qt) that allows warehouse managers and logistics planners to visualize warehouse layouts, calculate optimal paths between locations, analyze picklists, and animate warehouse operations over time. The application handles PDF floor plans, user-defined obstacles, pick points, staging areas, and applies pathfinding algorithms to optimize warehouse operations.

This document describes the architecture after a significant refactoring aimed at improving modularity, maintainability, and testability through a clearer separation of concerns.

## 2. Architectural Pattern

The application now more closely follows a **Model-View-Controller (MVC)** pattern, augmented with **Service Layers** to encapsulate complex business logic.

*   **Model (`model.py`):** `WarehouseModel` class.
    *   Centralizes all application data (project state, layout definitions, settings).
    *   Emits Qt signals when data changes, allowing other components to react.
    *   Does not contain business logic for processing or transforming data (that's for services).
*   **View (`pdf_viewer.py`, Dialogs):**
    *   Responsible for presenting data to the user and capturing user input.
    *   `PdfViewer`: Displays the warehouse layout, obstacles, points, paths, and animations. Manages graphical items and user drawing interactions. Uses an `InteractionMode` enum.
    *   Dialogs: Provide specialized interfaces for tasks like column selection, parameter input, and results display.
*   **Controller/Presenter (`main.py` - `MainWindow`):**
    *   Orchestrates the application.
    *   Initializes the Model, Services, and UI components (View).
    *   Connects user actions from the View (e.g., menu clicks, button presses) to appropriate methods in the Service layers or directly to the Model for simple state changes.
    *   Listens to signals from the Model and Services to update the View (e.g., refresh comboboxes, update status bar, draw paths).
*   **Services (`services.py`):**
    *   Encapsulate distinct domains of business logic.
    *   Operate on data from the `WarehouseModel` and may return results or modify the model (usually via dedicated model methods if complex).
    *   Can emit signals for long-running tasks (e.g., progress, completion).
    *   **Components:**
        *   `ProjectService`: Handles saving and loading project files (JSON).
        *   `PathfindingService`: Manages grid creation, pathfinding algorithms (Dijkstra), path precomputation (including multiprocessing), and physical distance calculations.
        *   `AnalysisService`: Processes picklist CSV files for analysis, calculates distances, and handles results export.
        *   `AnimationService`: Prepares data from timed picklists for animation, including time normalization and path retrieval.

## 3. High-Level Component Diagram

```
                               +-----------------+
                               |   MainWindow    |
                               | (Controller/UI) |
                               +--------+--------+
                                        |
        +-------------------------------+-------------------------------+
        |                               |                               |
+-------v-------+              +--------v--------+              +-------v-------+
|  PdfViewer    |              |  WarehouseModel |              | Dialogs       |
|  (View)       |<-------------|  (Data State)   |------------->| (View/Input)  |
+---------------+              +--------+--------+              +---------------+
                                        ^
                                        | (Data Access, Signals)
                                        |
                           +------------+-------------+
                           |    Service Layer         |
                           | (`services.py`)          |
                           |                          |
                           |  - ProjectService        |
                           |  - PathfindingService    |
                           |  - AnalysisService       |
                           |  - AnimationService      |
                           +--------------------------+
                                        |
                                        | (Utilizes core algorithms)
                                        |
                             +----------v-----------+
                             | Pathfinding Logic    |
                             | (`pathfinding.py`)   |
                             | - Grid Generation    |
                             | - Dijkstra           |
                             +----------------------+
```


## 4. Component Design Details

### 4.1 `WarehouseModel` (`model.py`)
    *   **Purpose:** Central data store.
    *   **Key Data:** PDF path/bounds, scale info, obstacles, staging areas, pick aisles, staging locations, grid parameters, cart dimensions, derived pathfinding grid/maps, validity flags.
    *   **Key Signals:** `pdf_path_changed`, `scale_changed`, `layout_changed`, `points_changed`, `grid_parameters_changed`, `project_loaded`, `model_reset`, `grid_invalidated`.

### 4.2 `MainWindow` (`main.py`)
    *   **Purpose:** Application entry point, UI orchestration, event handling.
    *   **Responsibilities:**
        *   Initializes `WarehouseModel`, all services, `PdfViewer`, menus, and dialogs.
        *   Connects UI actions to service calls or model updates.
        *   Updates UI elements based on signals from model/services.
        *   Manages the overall application lifecycle.

### 4.3 `PdfViewer` (`pdf_viewer.py`)
    *   **Purpose:** Visual display and interaction with the warehouse layout.
    *   **Responsibilities:** PDF rendering, drawing tools (scale, obstacles, areas, points), path visualization, animation overlay, mouse/keyboard event handling for interactions. Uses `InteractionMode` enum for state management. Emits signals for user drawing actions.

### 4.4 `Dialogs` (various `.py` files)
    *   **Purpose:** Specialized UI for specific tasks.
    *   **Examples:** `AnalysisResultsDialog`, `AnimationControlDialog`, `PicklistColumnDialog`, `LineDefinitionDialog`.
    *   **Responsibilities:** Gather user input, display specific information/results.

### 4.5 `ProjectService` (`services.py`)
    *   **Purpose:** Manage project file I/O.
    *   **Methods:** `save_project(model, file_path)`, `load_project(file_path) -> WarehouseModel | None`.
    *   **Signals:** `project_load_failed`, `project_save_failed`, `project_operation_finished`.

### 4.6 `PathfindingService` (`services.py`)
    *   **Purpose:** Core pathfinding logic.
    *   **Methods:** `update_grid(model)`, `precompute_all_paths(model)`, `get_shortest_path(model, start_name, end_name)`.
    *   **Worker Function:** `_run_dijkstra_worker` for multiprocessing.
    *   **Signals:** `grid_update_started`, `grid_update_finished`, `precomputation_started`, `precomputation_progress`, `precomputation_finished`.

### 4.7 `AnalysisService` (`services.py`)
    *   **Purpose:** Picklist analysis.
    *   **Methods:** `load_and_analyze(model, file_path, dialect, has_header, col_indices)`, `export_results(results, unit, file_path)`.
    *   **Signals:** `analysis_started`, `analysis_complete`, `analysis_failed`, `export_complete`, `export_failed`.

### 4.8 `AnimationService` (`services.py`)
    *   **Purpose:** Data preparation for animation.
    *   **Methods:** `prepare_animation_data(model, file_path, selection_data)`.
    *   **Signals:** `preparation_started`, `preparation_complete`, `preparation_failed`, `preparation_warning`.

### 4.9 `pathfinding.py`
    *   **Purpose:** Low-level pathfinding algorithms and grid utility functions.
    *   **Key Functions:** `create_grid_from_obstacles`, `dijkstra_precompute`, `reconstruct_path`.
    *   (Largely unchanged by the structural refactoring, but now called by `PathfindingService`).

### 4.10 `enums.py`
    *   **Purpose:** Define shared enumerations for type safety and clarity.
    *   **Enums:** `InteractionMode`, `PointType`, `AnimationMode`.

## 5. Data Flow Examples

### 5.1 Adding an Obstacle:
1.  User selects "Draw Obstacle" tool in `MainWindow` (View).
2.  `MainWindow` sets `PdfViewer.current_mode` to `InteractionMode.DRAW_OBSTACLE`.
3.  User clicks points in `PdfViewer`. `PdfViewer` draws temporary lines/polygon.
4.  User completes polygon. `PdfViewer` emits `polygon_drawn(InteractionMode.DRAW_OBSTACLE, QPolygonF)`.
5.  `MainWindow` (Controller) slot receives signal. Calls `model.add_obstacle(polygon)`.
6.  `WarehouseModel` appends polygon, sets itself dirty (e.g., `_invalidate_grid()`), emits `layout_changed`.
7.  `MainWindow` slot connected to `layout_changed` might update UI (e.g., enable "Precompute Paths").
8.  `PdfViewer` slot connected to `layout_changed` (or a more specific signal from `MainWindow`) might redraw the persistent obstacle.

### 5.2 Calculating a Single Path:
1.  User selects start/end points in `MainWindow` comboboxes and clicks "Calculate Path".
2.  `MainWindow` slot (Controller) is triggered.
3.  It calls `pathfinding_service.get_shortest_path(self.model, start_name, end_name)`.
4.  `PathfindingService` checks if `model.grid_is_valid`. If not, it may call `self.update_grid(model)` first.
5.  `PathfindingService` uses precomputed data from `model.path_maps` and `model.distance_maps` to reconstruct the path and calculate its physical distance.
6.  `PathfindingService` returns `(path_points, display_distance)` to `MainWindow`.
7.  `MainWindow` calls `pdf_viewer.draw_path(path_points)` and updates the status bar with the distance.

## 6. Key Design Principles Applied

*   **Single Responsibility Principle (SRP):** Each class (Model, Services, View components) has a more focused set of responsibilities.
*   **Separation of Concerns (SoC):** Data (Model), UI (View), and application logic (Controller/Services) are more distinctly separated.
*   **Loose Coupling:** Components interact primarily through signals and defined interfaces (methods), reducing direct dependencies.
*   **Improved Testability:** Model and Service layers can be tested with less reliance on the full UI stack.

## 7. Future Considerations
*   Further refinement of signal/slot connections for optimal granularity.
*   Introducing a dedicated state management system for UI elements if complexity grows.
*   More comprehensive error handling and reporting via signals. 