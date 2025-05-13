## Warehouse Path Finder - Design Document

**Version:** 2.0 (Based on Architecture.txt v2.0)

**1. Introduction & System Overview**

The Warehouse Path Finder is a Python desktop application using the PySide6 (Qt6) framework. It enables warehouse managers and logistics planners to optimize warehouse operations by:
*   Visualizing warehouse layouts from PDF floor plans.
*   Defining layout features: obstacles, pick aisles, staging locations, and staging areas with travel penalties.
*   Calculating optimal (shortest) paths between defined locations using Dijkstra's algorithm.
*   Analyzing picklist efficiency based on travel distances.
*   Animating warehouse activity over time based on timed picklists.

**2. Architectural Pattern: MVC + Services**

The application employs a Model-View-Controller (MVC) pattern enhanced with Service Layers to promote modularity, maintainability, and testability.

*   **Model (`model.py`):**
    *   `WarehouseModel`: The central data repository holding project state, layout definitions, pathfinding results, and settings.
    *   Emits Qt signals upon data changes to notify other components.
    *   Does not contain complex business logic.
*   **View (`pdf_viewer.py`, Dialogs):**
    *   Presents data to the user and captures input.
    *   `PdfViewer`: Custom `QGraphicsView` for rendering PDFs, displaying layout elements (obstacles, points, paths), handling drawing interactions (managed by `InteractionMode`), and showing animations.
    *   Dialogs: Provide specialized UIs for tasks like CSV column selection (`PicklistColumnDialog`), analysis results (`AnalysisResultsDialog`), animation control (`AnimationControlDialog`), etc.
*   **Controller/Presenter (`main.py`):**
    *   `MainWindow`: Orchestrates the application flow.
    *   Initializes Model, Services, and View components.
    *   Connects user actions (menu clicks, button presses) to Service methods or Model updates.
    *   Updates the View in response to signals from the Model and Services.
*   **Services (`services.py`):**
    *   Encapsulate domain-specific business logic, operating on the `WarehouseModel`.
    *   May modify the Model or emit signals for progress/completion.
    *   **Key Services:**
        *   `ProjectService`: Handles project file saving/loading (JSON format).
        *   `PathfindingService`: Manages grid creation, path precomputation (Dijkstra via `multiprocessing`), path retrieval, and distance calculation.
        *   `AnalysisService`: Processes picklist CSVs, calculates distances, generates statistics, and handles results export.
        *   `AnimationService`: Prepares timed picklist data for visualization.
*   **Core Logic (`pathfinding.py`):**
    *   Contains low-level pathfinding algorithms (grid generation from obstacles, Dijkstra implementation, path reconstruction) utilized by `PathfindingService`.
*   **Shared Enums (`enums.py`):**
    *   Defines common enumerations (`InteractionMode`, `PointType`, `AnimationMode`) for clarity and type safety.

**3. High-Level Component Interaction (See `Architecture.txt` for Diagram)**

User actions in the View (`MainWindow`, `PdfViewer`, Dialogs) trigger methods in the Controller (`MainWindow`). The Controller invokes methods on the appropriate Service. Services interact with the `WarehouseModel` to retrieve or update data and perform calculations (potentially using `pathfinding.py`). The `WarehouseModel` emits signals upon data change. Both the Controller and View components listen to these signals to update the UI accordingly.

**4. Data Flow Examples (See `Architecture.txt` for detailed flows)**

*   **Adding an Obstacle:** User draws -> `PdfViewer` emits signal -> `MainWindow` calls `model.add_obstacle()` -> `Model` updates & emits `layout_changed` -> `MainWindow`/`PdfViewer` update UI/redraw.
*   **Calculating Path:** User selects points & clicks button -> `MainWindow` calls `pathfinding_service.get_shortest_path()` -> `Service` retrieves/computes path from `Model` data -> `Service` returns result -> `MainWindow` calls `pdf_viewer.draw_path()` and updates status.

**5. Key Design Principles**

*   **Single Responsibility Principle (SRP):** Each class has a focused responsibility.
*   **Separation of Concerns (SoC):** Data, UI, and logic are distinctly separated.
*   **Loose Coupling:** Components interact via signals and defined interfaces.
*   **Testability:** Model and Service layers are more easily testable in isolation.

**6. Core Libraries & Technologies**

*   **Language:** Python 3.9+
*   **UI:** PySide6 (Qt6)
*   **PDF Handling:** PyMuPDF (fitz)
*   **Numerical Computation:** NumPy
*   **Image Processing:** SciPy (e.g., obstacle dilation)
*   **Plotting:** Matplotlib (for analysis histograms)
*   **Standard Libraries:** `csv`, `json`, `datetime`, `multiprocessing`

**7. Project Structure**

*   `main.py`: Main application entry point, `MainWindow` controller.
*   `model.py`: `WarehouseModel` data store.
*   `services.py`: Business logic services.
*   `pdf_viewer.py`: Core visualization component.
*   `pathfinding.py`: Pathfinding algorithms.
*   `enums.py`: Shared enumerations.
*   `*.py` (Dialogs): Specific UI dialogs.
*   `requirements.txt`: Dependencies.
*   `README.md`: Project overview and user guide.
*   `Architecture.txt`: Detailed architecture description (source for this document).
*   `Test/`: Directory for unit/integration tests (structure TBD). 