## Warehouse Path Finder - User Documentation

**(This is largely based on the README.md content)**

**1. Introduction**

Welcome to the Warehouse Path Finder! This application helps you visualize your warehouse layout, optimize paths, analyze picklist efficiency, and simulate warehouse operations.

**2. Core Features**

*   **Visualize:** Load and view PDF floor plans.
*   **Scale:** Calibrate the layout to real-world units (meters/feet).
*   **Define:** Interactively draw obstacles, staging areas (with travel penalties), **optional user-defined pathfinding boundaries**, pick aisles (start points), and staging locations (end points). Use line tools to quickly define multiple points.
*   **Pathfind:**
    *   Generates an internal grid based on your layout, which can be **cropped to the relevant area** for efficiency.
    *   Precomputes all shortest paths from pick aisles using Dijkstra's algorithm.
    *   Calculates and displays the shortest path and distance between any selected pick aisle and staging location.
*   **Analyze:**
    *   Import picklist data from CSV files.
    *   Calculate travel distance for each picklist item.
    *   View results, statistics, and histograms. Export enhanced CSVs.
*   **Animate:**
    *   Import timed picklist data (CSV).
    *   Visualize warehouse activity with moving "carts" or path lines.
    *   Control playback speed and filter by date/location.
*   **Save/Load:** Store and retrieve your entire project setup (layout, scale, settings, **including user pathfinding bounds**) in `.whp` files.

**3. Setup and Running**

1.  **Install Python:** Ensure you have Python 3.9 or newer installed.
2.  **Create Virtual Environment (Recommended):**
    ```bash
    # In your project directory
    python -m venv .venv
    # Activate it
    # Windows:
    .\.venv\Scripts\activate
    # macOS/Linux:
    source .venv/bin/activate
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Run:**
    ```bash
    python main.py
    ```

**4. Quick Start Guide**

1.  **Load PDF:** `File > Open PDF...`
2.  **Set Scale:** `Tools > Set Scale...` (Click two points, enter known distance).
3.  **Define Layout:** Use `Tools` menu options (`Draw Obstacle`, `Define Staging Area`, `Set Pick Aisle`, `Set Staging Location`, `Line Definition...`) to map your warehouse features onto the PDF.
4.  **(Optional) Define Pathfinding Area:** `Tools > Define Pathfinding Bounds`. Draw a polygon around your primary operational area. If you skip this, the system will try to determine the area from other elements or use the full PDF.
5.  **IMPORTANT - Precompute Paths:** `Tools > Precompute All Paths`. **Run this *after* setting the scale and *any* time you change the layout (add/move obstacles, points, etc.), adjust grid parameters, or change/define pathfinding bounds.** This enables path calculation, analysis, and animation.
6.  **Calculate Single Path:** Select start/end points in the main window and click "Calculate Path".
7.  **Analyze Picklist:** `Tools > Analyze Picklist...` Load CSV, map columns, view results.
8.  **Animate Picklist:** `Tools > Animate Picklist...` Load timed CSV, configure, and play.
9.  **Save Project:** `File > Save Project / Save Project As...`

**5. Troubleshooting**

*   **PDF Issues:** Check if PDF is valid and not password protected. Ensure `PyMuPDF` is installed correctly (`pip install pymupdf`).
*   **Pathfinding Errors:**
    *   Did you set the scale *before* drawing elements?
    *   Are points placed inside obstacles?
    *   Did you run `Precompute All Paths` after the latest layout change (including pathfinding bounds)?
    *   If using "Define Pathfinding Bounds", ensure it's large enough to include all necessary points and potential paths with some margin.
    *   Try adjusting the "Grid Factor" in the main window (lower value = finer grid, more accurate but slower; higher value = coarser grid, faster but less accurate).
*   **CSV Errors:** Ensure standard CSV format. Check date/time formats (e.g., `YYYY-MM-DD HH:MM:SS`, `MM/DD/YYYY HH:MM`). Use the column selection dialogs carefully.
*   **Slow Animation:** Filter data by date/cluster in Animation Controls. A higher "Grid Factor" can also help. 