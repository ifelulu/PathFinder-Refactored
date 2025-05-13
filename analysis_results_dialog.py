# --- START OF FILE Warehouse-Path-Finder-main/analysis_results_dialog.py ---

import sys
import numpy as np
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QLabel, QGroupBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QTextEdit, QPushButton,
    QApplication
)
# --- CORRECTED IMPORT HERE ---
from PySide6.QtCore import Qt, Slot, Signal # Added Signal
from PySide6.QtGui import QFont
import pandas as pd
from typing import List, Dict, Any, Optional

# --- Matplotlib Integration ---
import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
# --- End Matplotlib ---

# --- ADD THIS IMPORT for the example usage block (if not already moved to top) ---
from PySide6.QtWidgets import QMessageBox


class MplCanvas(FigureCanvas):
    """Helper class for the Matplotlib canvas."""
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super().__init__(fig)
        self.setParent(parent)
        FigureCanvas.setSizePolicy(self, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        FigureCanvas.updateGeometry(self)

class AnalysisResultsDialog(QDialog):
    """Dialog to display picklist analysis statistics, warnings, and histogram, with dynamic date filtering."""
    export_filtered_requested = Signal(list, str) # This should now work

    def __init__(self, input_filename: str, warnings_list: Optional[List[str]],
                 all_detailed_results: List[Dict[str, Any]], unit: str, unique_dates: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Analysis Results: {input_filename}")
        self.setSizeGripEnabled(True)
        self.setMinimumSize(700, 750)

        self.all_detailed_results = all_detailed_results if all_detailed_results else []
        self.unit = unit
        self.unique_dates = unique_dates
        self.initial_warnings = warnings_list if warnings_list else []

        self._setup_ui()
        self._update_displays_for_filter()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- Date Filter ---
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter by Date:"))
        self.date_filter_combo = QComboBox()
        self.date_filter_combo.addItem("All Dates")
        if self.unique_dates: self.date_filter_combo.addItems(self.unique_dates)
        self.date_filter_combo.currentIndexChanged.connect(self._update_displays_for_filter)
        filter_layout.addWidget(self.date_filter_combo); filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # --- Statistics Table ---
        self.stats_group_box = QGroupBox("Summary Statistics (for filtered data)")
        stats_layout = QVBoxLayout()
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(2); self.stats_table.setHorizontalHeaderLabels(["Statistic", "Value"])
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.stats_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        stats_layout.addWidget(self.stats_table); self.stats_group_box.setLayout(stats_layout)
        layout.addWidget(self.stats_group_box)

        # --- Histogram ---
        self.plot_canvas = MplCanvas(self, width=5, height=3, dpi=100)
        layout.addWidget(self.plot_canvas, 1)

        # --- Warnings Area ---
        warnings_group = QGroupBox("Processing Warnings/Info")
        warnings_layout = QVBoxLayout()
        self.warnings_text_edit = QTextEdit()
        self.warnings_text_edit.setReadOnly(True); self.warnings_text_edit.setFont(QFont("Consolas", 9))
        self.warnings_text_edit.setText("\n".join(self.initial_warnings))
        warnings_layout.addWidget(self.warnings_text_edit); warnings_group.setLayout(warnings_layout)
        layout.addWidget(warnings_group)

        # --- Buttons ---
        self.export_filtered_button = QPushButton("Export Filtered Results...")
        self.export_filtered_button.clicked.connect(self._request_export_filtered)
        button_box = QDialogButtonBox()
        button_box.addButton(self.export_filtered_button, QDialogButtonBox.ButtonRole.ActionRole)
        button_box.addButton(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

    def _get_filtered_results(self) -> List[Dict[str, Any]]:
        selected_date = self.date_filter_combo.currentText()
        if selected_date == "All Dates": return self.all_detailed_results
        return [res for res in self.all_detailed_results if res.get('date') == selected_date]

    @Slot()
    def _update_displays_for_filter(self):
        filtered_results = self._get_filtered_results()
        self._update_stats_table(filtered_results)
        self._plot_histogram(filtered_results)

    def _update_stats_table(self, results_for_stats: List[Dict[str, Any]]):
        self.stats_table.setRowCount(0)
        self.stats_table.insertRow(0)
        filter_item_name = QTableWidgetItem("Current Filter"); filter_item_name.setFont(QFont("Arial", weight=QFont.Weight.Bold))
        filter_item_value = QTableWidgetItem(self.date_filter_combo.currentText()); filter_item_value.setFont(QFont("Arial", weight=QFont.Weight.Bold))
        self.stats_table.setItem(0, 0, filter_item_name); self.stats_table.setItem(0, 1, filter_item_value)
        valid_distances = [res['distance'] for res in results_for_stats if res.get('status') == 'Success' and pd.notna(res.get('distance')) and res.get('distance') != np.inf]
        stats_display_data = []
        if valid_distances:
            distances_np = np.array(valid_distances)
            stats_display_data = [
                ("Picklists Included", f"{len(distances_np):,}"), ("Minimum Distance", f"{np.min(distances_np):.2f} {self.unit}"),
                ("Maximum Distance", f"{np.max(distances_np):.2f} {self.unit}"), ("Mean Distance", f"{np.mean(distances_np):.2f} {self.unit}"),
                ("Median Distance", f"{np.median(distances_np):.2f} {self.unit}"), ("Std Deviation", f"{np.std(distances_np):.2f} {self.unit}"),
                ("Total Distance", f"{np.sum(distances_np):.2f} {self.unit}")
            ]
        else:
            stats_display_data = [("Picklists Included", "0 (No valid distances)")] + [(stat, "N/A") for stat in ["Minimum Distance", "Maximum Distance", "Mean Distance", "Median Distance", "Std Deviation", "Total Distance"]]
        for name, value in stats_display_data:
            row_pos = self.stats_table.rowCount(); self.stats_table.insertRow(row_pos)
            self.stats_table.setItem(row_pos, 0, QTableWidgetItem(name)); self.stats_table.setItem(row_pos, 1, QTableWidgetItem(value))
        self.stats_table.resizeRowsToContents()

    def _plot_histogram(self, results_for_plot: List[Dict[str, Any]]):
        ax = self.plot_canvas.axes; ax.clear()
        distances_to_plot = [res['distance'] for res in results_for_plot if res.get('status') == 'Success' and pd.notna(res.get('distance')) and res.get('distance') != np.inf]
        if distances_to_plot:
            ax.hist(distances_to_plot, bins='auto', color='skyblue', edgecolor='black')
            ax.set_title(f'Distribution of Path Distances ({self.date_filter_combo.currentText()})')
            ax.set_xlabel(f'Distance ({self.unit})'); ax.set_ylabel('Frequency'); ax.grid(axis='y', alpha=0.7)
        else:
            ax.text(0.5, 0.5, f'No data for filter "{self.date_filter_combo.currentText()}"', ha='center', va='center', transform=ax.transAxes)
        self.plot_canvas.draw()

    @Slot()
    def _request_export_filtered(self):
        filtered_data = self._get_filtered_results()
        if not filtered_data: QMessageBox.information(self, "Export", "No data in current filter."); return
        self.export_filtered_requested.emit(filtered_data, self.unit)

# Example Usage
if __name__ == '__main__':
    app = QApplication(sys.argv)
    example_filename = "test_picklist.csv"
    example_warnings = ["Warning: Point A99 not found.", "Info: 5 rows skipped due to errors."]
    example_detailed = [
        {'id': 'P1', 'start': 'A1', 'end': 'S1', 'distance': 25.6, 'status': 'Success', 'date': '2023-10-26', 'start_time': '09:00', 'end_time': '09:05'},
        {'id': 'P2', 'start': 'B2', 'end': 'S5', 'distance': np.inf, 'status': 'Unreachable', 'date': '2023-10-26', 'start_time': '09:10', 'end_time': '09:15'},
        {'id': 'P3', 'start': 'A1', 'end': 'S2', 'distance': 45.0, 'status': 'Success', 'date': '2023-10-27', 'start_time': '10:00', 'end_time': '10:05'},
    ]
    example_unit = "meters"
    example_unique_dates = ["2023-10-26", "2023-10-27"]
    dialog = AnalysisResultsDialog(example_filename, example_warnings, example_detailed, example_unit, example_unique_dates)
    dialog.export_filtered_requested.connect(lambda res, u: QMessageBox.information(dialog, "Export Triggered", f"Would export {len(res)} rows for unit '{u}'."))
    dialog.exec()
    sys.exit()

# --- END OF FILE Warehouse-Path-Finder-main/analysis_results_dialog.py ---