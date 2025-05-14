# Warehouse Path Finder

## Introduction

The Warehouse Path Finder is a desktop application designed to assist warehouse managers and logistics analysts in optimizing warehouse operations. It enables users to:

*   Visualize warehouse layouts from PDF floor plans.
*   Define crucial layout features like obstacles, pick-up locations (Pick Aisles), and drop-off points (Staging Locations), including special zones like Staging Areas with travel penalties.
*   Calculate optimal (shortest) paths between defined locations using pathfinding algorithms.
*   Analyze the efficiency of historical or simulated picklists based on travel distances.
*   Visualize warehouse activity and traffic flow over time through picklist animation.

The application is built using Python and the PySide6 (Qt6) framework.

## Core Features

*   **PDF Layout Visualization:**
    *   Load, display, zoom, and pan warehouse floor plans from PDF files.
*   **Layout Scaling & Units:**
    *   Set real-world scale by calibrating a known distance on the PDF (in meters or feet).
    *   Display all calculated distances in user-selected units (meters or feet).
*   **Interactive Layout Definition:**
    *   **Obstacles:** Draw polygonal impassable obstacles (e.g., racks, machinery).
    *   **Staging Areas:** Define polygonal areas where travel is discouraged (configurable cost penalty).
    *   **User-Defined Pathfinding Bounds (Optional):** Draw a specific polygonal area to constrain pathfinding calculations, potentially speeding up precomputation for large PDFs with localized layouts.    
    *   **Pick Aisles:** Define named start points for path calculations.
    *   **Staging Locations:** Define named end points for path calculations.
    *   **Line-Based Point Generation:** Quickly generate series of named points along a drawn line (e.g., for defining multiple aisles or dock doors).
    *   **Edit Layout:** Select, move, or delete defined obstacles, staging areas, and points.
*   **Pathfinding:**
    *   **Grid Representation:** Generates a configurable 2D grid. The grid can be cropped to the relevant layout area (user-defined bounds or auto-calculated from elements) for improved performance.
    *   **Dijkstra-Based Precomputation:** Precomputes shortest paths from all defined Pick Aisles to all reachable grid cells using Dijkstra's algorithm (parallelized with `multiprocessing` for speed).
    *   **Single Path Calculation:** Calculates and displays the shortest path and its physical distance between a selected Pick Aisle and Staging Location using precomputed data.
    *   **Accurate Distance:** Physical distances are measured along the path segments, accounting for the actual route taken, even through staging areas.
*   **Picklist Analysis:**
    *   **CSV Import:** Import picklist data from CSV files with configurable column mapping for Pick ID, Start/End Locations, and Start/End Times.
    *   **Distance Calculation:** Calculates the shortest path distance for each picklist item using the precomputed path data.
    *   **Results & Visualization:** Displays analysis results including summary statistics (total distance, average, min/max) and a histogram of pick distances. Results are filterable by date.
    *   **CSV Export:** Export analysis results, including calculated distances, to a new CSV file.
*   **Picklist Animation:**
    *   **Timed CSV Import:** Import picklist data with timestamps for animating operations.
    *   **Playback Controls:** Animate picks with controls for play/pause, reset, and speed adjustment.
    *   **Visualization Modes:**
        *   **Carts:** Shows moving rectangles ("carts") traversing their calculated paths. Cart dimensions are configurable.
        *   **Path Lines:** Progressively draws path lines as picks occur. Lines can be configured to fade or persist and are color-coded by start location cluster to visualize traffic patterns.
    *   **Filtering:** Filter animations by date and start/end location clusters.
*   **Project Management:**
    *   **Save/Load:** Save the entire project state (PDF reference, scale, all layout definitions including **user pathfinding bounds**, settings) to a JSON-based project file (`.whp`) and load it back.

## Technical Architecture (v2.0)

The application follows a Model-View-Controller (MVC) pattern augmented with Service Layers:

*   **Model (`model.py`):** `WarehouseModel` class centralizes all application data (layout, settings, derived path data) and emits signals on changes.
*   **View (`pdf_viewer.py`, Dialogs):** `PdfViewer` handles PDF display and drawing interactions. Various dialogs manage specific user inputs and results display.
*   **Controller/Presenter (`main.py`):** `MainWindow` orchestrates UI events, interacts with services, and updates the View based on Model/Service feedback.
*   **Services (`services.py`):** Encapsulate business logic:
    *   `ProjectService`: Project file I/O.
    *   `PathfindingService`: Grid generation, Dijkstra precomputation, path calculation.
    *   `AnalysisService`: Picklist analysis logic and CSV processing.
    *   `AnimationService`: Animation data preparation.
*   **Pathfinding Logic (`pathfinding.py`):** Core algorithms (grid creation, Dijkstra).
*   **Enums (`enums.py`):** Defines shared enumerations like `InteractionMode`.

## Core Libraries Used

*   **Python:** 3.9+
*   **PySide6:** For the Qt6 graphical user interface.
*   **PyMuPDF (fitz):** For PDF rendering and handling.
*   **NumPy:** For efficient numerical operations, especially grid-based pathfinding.
*   **SciPy:** For image processing tasks like obstacle dilation.
*   **Matplotlib:** For generating histograms in the analysis results.
*   **Standard Libraries:** `csv`, `json`, `datetime`, `multiprocessing`.

## Setup and Running

1.  **Prerequisites:**
    *   Python 3.9 or newer.
    *   Ensure `pip` (Python package installer) is available.

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    *   Use the provided `requirements.txt` file:
        ```bash
        pip install -r requirements.txt
        ```

4.  **Run the Application:**
    *   Execute the main script from the project's root directory:
        ```bash
        python main.py
        ```

## Key Files

*   `main.py`: Main application window, controller logic.
*   `model.py`: `WarehouseModel` class for application data.
*   `services.py`: Houses `ProjectService`, `PathfindingService`, `AnalysisService`, `AnimationService`.
*   `pdf_viewer.py`: Custom `QGraphicsView` for PDF display and interactive drawing.
*   `pathfinding.py`: Core pathfinding algorithms (grid creation, Dijkstra).
*   `enums.py`: Defines application-wide enumerations.
*   Dialogs:
    *   `analysis_results_dialog.py`
    *   `animation_control_dialog.py`
    *   `animation_picklist_dialog.py`
    *   `picklist_column_dialog.py`
    *   `line_definition_dialog.py`
*   `requirements.txt`: Python package dependencies.
*   `README.md`: This file.
*   (Potentially) `Warehouse_Path_Finder_Design_Document.md`, `Warehouse_Path_Finder_Documentation.txt`: More detailed design and user docs.

## Using the Application (Quick Start)

1.  **File > Open PDF...**: Load your warehouse floor plan.
2.  **Tools > Set Scale...**: Click two points on the PDF, then enter their known real-world distance and unit.
3.  **Tools > Draw Obstacle / Define Staging Area**: Draw impassable regions or penalty zones.
4.  **(Optional) Tools > Define Pathfinding Bounds**: Draw a polygon around the area you want the pathfinding grid to focus on. If not defined, the application will try to determine a sensible area from your other layout elements, or use the full PDF.
5.  **Tools > Set Pick Aisle / Set Staging Location**: Define named start and end points for paths. (Use Line Definition tools for multiple points).
6.  **Tools > Precompute All Paths**: This is crucial for analysis and animation. It calculates paths from all Pick Aisles. Run this after any layout changes (obstacles, points, scale, grid factor, staging penalty, **pathfinding bounds**).
7.  **Tools > Calculate Path**: Select a start/end pair to see a single shortest path.
8.  **Tools > Analyze Picklist...**: Load a CSV, map columns, and view distance statistics.
9.  **Tools > Animate Picklist...**: Load a timed CSV to visualize warehouse activity.
10. **File > Save Project / Save Project As...**: Save your work.

## Troubleshooting Tips

*   **PDF Issues:** Ensure PDF is not corrupted or password-protected. `PyMuPDF` must be installed.
*   **Pathfinding Problems:**
    *   Ensure scale is set correctly *before* defining elements or pathfinding.
    *   Make sure Pick Aisles/Staging Locations are not inside obstacles.
    *   Run "Precompute All Paths" after any layout changes (obstacles, points, scale, grid factor, staging penalty, **pathfinding bounds**).
    *   If using "Define Pathfinding Bounds", ensure it encompasses all your pick/staging points and allows reasonable routes between them.
    *   Adjust "Grid Factor" in `MainWindow` for a trade-off between path precision and computation speed.
*   **CSV Import Errors:**
    *   Verify standard CSV format. Use column selection dialogs to map headers correctly.
    *   Ensure date/time formats are supported (e.g., `YYYY-MM-DD HH:MM:SS`, `MM/DD/YYYY HH:MM`).
*   **Animation Performance:** For large datasets, use date/cluster filters in the Animation Controls. A higher "Grid Factor" can also improve performance.

## Contributing

Contributions are welcome! Please refer to the `CONTRIBUTING.md` file (if available) or:

1.  **Fork** the repository.
2.  Create a **feature branch**.
3.  Make your changes.
4.  Submit a **pull request** with a clear description.

Please adhere to existing code style and add tests for new features.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details. 