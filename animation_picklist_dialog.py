# --- START OF FILE Warehouse-Path-Finder-main/animation_picklist_dialog.py ---

import sys
import csv
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QLabel, QPushButton, QDialogButtonBox, QMessageBox, QHeaderView,
    QCheckBox, QFormLayout # Added LineEdit, FormLayout
)
from PySide6.QtCore import Qt
from typing import List, Dict, Any, Optional # Added for better type hinting

MAX_PREVIEW_ROWS = 10

class AnimationPicklistDialog(QDialog):
    """Dialog to select columns for picklist animation, including time data."""
    def __init__(self, file_path: str, parent=None): # Added type hint for file_path
        super().__init__(parent)
        self.setWindowTitle("Select Animation Picklist Columns")
        self.file_path = file_path
        self.raw_first_row: List[str] = []
        self.num_columns: int = 0
        self.preview_data: List[List[str]] = []
        self.dialect: Optional[csv.Dialect] = None # Type hint
        self.has_header: bool = False # Initial detection state
        self.column_indices: Dict[str, int] = {'id': -1, 'start_loc': -1, 'end_loc': -1, 'start_time': -1, 'end_time': -1}


        if not self._load_preview():
            raise RuntimeError(f"Failed to load file preview for animation: {file_path}") # f-string

        self._setup_ui()
        self._update_combobox_options() # Initial population
        self.resize(700, 500) # Adjust size

    def _load_preview(self) -> bool: # Added return type hint
        """Loads first row, detects dialect/header, loads preview rows."""
        try:
            with open(self.file_path, 'r', newline='', encoding='utf-8-sig') as f:
                sample = f.read(2048)
                f.seek(0)
                try:
                    self.dialect = csv.Sniffer().sniff(sample, delimiters=',\t;| ')
                    self.has_header = csv.Sniffer().has_header(sample)
                except csv.Error:
                    # Fallback if sniffer fails (e.g. very simple file)
                    QMessageBox.warning(self, "CSV Detection",
                                        "Could not automatically detect CSV dialect/header. "
                                        "Assuming comma-separated. Please verify 'First row contains headers' checkbox.")
                    self.dialect = csv.excel # Default to comma separated
                    # A simple heuristic for header if sniffer fails
                    temp_reader = csv.reader(StringIO(sample), self.dialect) # Use StringIO for sample
                    try:
                        first_row_check = next(temp_reader)
                        if all(not item.replace('.', '', 1).isdigit() for item in first_row_check if item.strip()):
                            self.has_header = True
                        else:
                            self.has_header = False
                    except StopIteration:
                        self.has_header = False # Empty sample

                reader = csv.reader(f, self.dialect)
                try:
                    self.raw_first_row = next(reader)
                    self.num_columns = len(self.raw_first_row)
                except StopIteration:
                    QMessageBox.critical(self, "File Error", "File appears to be empty.")
                    return False

                # If header was not detected by sniffer, but checkbox is checked, or vice-versa,
                # the _on_header_checkbox_changed logic will adjust the preview table.
                # For initial load, respect sniffer or simple heuristic.
                if not self.has_header: # If no header, the first row read is data
                    self.preview_data.append(self.raw_first_row)
                # else: headers are in self.raw_first_row

                for i, row in enumerate(reader):
                    # Ensure we don't add more rows to preview_data than MAX_PREVIEW_ROWS
                    # including the potential first data row if no header.
                    if len(self.preview_data) >= MAX_PREVIEW_ROWS:
                        break
                    if len(row) == self.num_columns:
                        self.preview_data.append(row)
            return True
        except Exception as e:
            QMessageBox.critical(self, "File Error", f"Error reading file preview: {e}")
            return False

    def _setup_ui(self):
        main_layout = QVBoxLayout(self) # Changed layout to main_layout

        # --- Preview Table ---
        # Determine initial headers for table display based on detection
        table_headers: List[str] = [] # Type hint
        if self.has_header:
             table_headers = self.raw_first_row
        else:
             table_headers = [f"Column {i+1}" for i in range(self.num_columns)]

        preview_label = QLabel("File Preview (first rows):")
        self.preview_table = QTableWidget() # Removed row/col count here, set later
        self.preview_table.setColumnCount(self.num_columns)
        self.preview_table.setHorizontalHeaderLabels(table_headers)

        # Populate preview data (self.preview_data already excludes header if self.has_header)
        self.preview_table.setRowCount(len(self.preview_data))
        for r, row_data in enumerate(self.preview_data):
            for c, cell_data in enumerate(row_data):
                 if c < self.num_columns:
                     item = QTableWidgetItem(str(cell_data))
                     item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                     self.preview_table.setItem(r, c, item)

        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        main_layout.addWidget(preview_label)
        main_layout.addWidget(self.preview_table)

        # --- Header Checkbox ---
        self.header_checkbox = QCheckBox("First row contains headers")
        self.header_checkbox.setChecked(self.has_header)
        self.header_checkbox.stateChanged.connect(self._on_header_checkbox_changed) # Connect here
        main_layout.addWidget(self.header_checkbox)

        # --- Column Selection Combos ---
        combo_layout = QFormLayout() # Use FormLayout for better alignment

        self.id_combo = QComboBox() # Must be selected
        self.start_loc_combo = QComboBox()
        self.end_loc_combo = QComboBox()
        self.start_time_combo = QComboBox()
        self.end_time_combo = QComboBox()

        combo_layout.addRow("Picklist ID Column (Required):", self.id_combo)
        combo_layout.addRow("Start Location (Pick Aisle) Column (Required):", self.start_loc_combo)
        combo_layout.addRow("End Location (Staging) Column (Required):", self.end_loc_combo)
        combo_layout.addRow("Start Time Column (Required):", self.start_time_combo)
        combo_layout.addRow("End Time Column (Required):", self.end_time_combo)

        main_layout.addLayout(combo_layout)

        time_format_info = QLabel(
            "Note: Timestamps should be in a parseable format (e.g., YYYY-MM-DD HH:MM:SS or MM/DD/YYYY HH:MM)."
        )
        time_format_info.setWordWrap(True)
        main_layout.addWidget(time_format_info)

        # --- Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._validate_and_accept) # Changed to _validate_and_accept
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _on_header_checkbox_changed(self): # Renamed for clarity and removed state arg
        """Updates preview table and comboboxes when header checkbox changes."""
        self.has_header = self.header_checkbox.isChecked()

        # Update table headers and preview data content
        current_preview_row_count = self.preview_table.rowCount()

        if self.has_header:
            self.preview_table.setHorizontalHeaderLabels(self.raw_first_row)
            # If first row of preview_data is indeed the raw_first_row (meaning it was treated as data)
            if self.preview_data and current_preview_row_count > 0 and \
               all(self.preview_table.item(0,c).text() == str(self.raw_first_row[c]) for c in range(self.num_columns) if self.preview_table.item(0,c)):
                self.preview_table.removeRow(0)
                # self.preview_data.pop(0) # self.preview_data should not change its underlying source rows
        else: # First row is data
            self.preview_table.setHorizontalHeaderLabels([f"Column {i+1}" for i in range(self.num_columns)])
            # Check if the raw_first_row needs to be re-inserted as the first data row in preview
            if not any(all(self.preview_table.item(0,c).text() == str(self.raw_first_row[c]) for c in range(self.num_columns) if self.preview_table.item(0,c)) for r in range(current_preview_row_count) ):
                self.preview_table.insertRow(0)
                for c_idx, cell_data in enumerate(self.raw_first_row):
                     if c_idx < self.num_columns:
                         item = QTableWidgetItem(str(cell_data))
                         item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                         self.preview_table.setItem(0, c_idx, item)

        self._update_combobox_options()


    def _update_combobox_options(self):
        """Populates comboboxes based on header checkbox state."""
        options: List[str] = []
        if self.has_header: # Use self.has_header which is updated by checkbox
            options = [header.strip() for header in self.raw_first_row if header.strip()]
            if not options: # Fallback if header row is entirely empty or whitespace
                 QMessageBox.warning(self, "Header Warning", "Header row is blank. Using generic column names.")
                 options = [f"Column {i+1}" for i in range(self.num_columns)]
        else: # Use generic column names
            options = [f"Column {i+1}" for i in range(self.num_columns)]

        combos = [self.id_combo, self.start_loc_combo, self.end_loc_combo, self.start_time_combo, self.end_time_combo]
        current_texts = [c.currentText() for c in combos] # Store before clearing

        for combo in combos:
            combo.clear()
            combo.addItems([""] + options) # Add a blank option for "not selected"

        # Try to restore previous selection if still valid
        for combo, text in zip(combos, current_texts):
            if text in options:
                combo.setCurrentText(text)
            else:
                combo.setCurrentIndex(0) # Select blank if previous text not in new options

    def _validate_and_accept(self): # Renamed
        """Validate selections before accepting."""
        # Subtract 1 because of the blank "" item at index 0
        id_idx = self.id_combo.currentIndex() - 1
        start_loc_idx = self.start_loc_combo.currentIndex() - 1
        end_loc_idx = self.end_loc_combo.currentIndex() - 1
        start_time_idx = self.start_time_combo.currentIndex() - 1
        end_time_idx = self.end_time_combo.currentIndex() - 1

        # All fields are mandatory for animation
        indices = [id_idx, start_loc_idx, end_loc_idx, start_time_idx, end_time_idx]

        if any(idx == -1 for idx in indices):
             QMessageBox.warning(self, "Validation Error", "Please select a column for ALL required fields for animation.")
             return
        if len(set(indices)) != len(indices): # Check for uniqueness
            QMessageBox.warning(self, "Validation Error", "Please select unique columns for each field.")
            return

        self.column_indices['id'] = id_idx
        self.column_indices['start_loc'] = start_loc_idx
        self.column_indices['end_loc'] = end_loc_idx
        self.column_indices['start_time'] = start_time_idx
        self.column_indices['end_time'] = end_time_idx
        self.has_header = self.header_checkbox.isChecked() # Final check based on UI

        super().accept()

    def get_animation_selection_data(self) -> Optional[Dict[str, Any]]: # Added return type hint
        """Returns selected indices, dialect, and header status."""
        if self.result() == QDialog.DialogCode.Accepted:
            return {
                'indices': self.column_indices,
                'dialect': self.dialect,
                'has_header': self.has_header
            }
        else:
            return None

# Example Usage (for testing)
if __name__ == '__main__':
    # --- ADD THIS IMPORT ---
    from PySide6.QtWidgets import QApplication
    from io import StringIO # For testing with string-based CSV

    # Create a dummy CSV with time
    dummy_file_content_header = "ID,PICK_LOC,DROP_LOC,START_S,END_S\n101,A1,S1,0,60\n102,B2,S1,15,90\n103,C3,S2,30,120.5"
    dummy_file_content_no_header = "101,A1,S1,0,60\n102,B2,S1,15,90\n103,C3,S2,30,120.5"

    dummy_file_path = "dummy_anim_picklist_dialog_test.csv"

    app = QApplication(sys.argv)

    for content, has_header_expected in [(dummy_file_content_header, True), (dummy_file_content_no_header, False)]:
        print(f"\n--- Testing with header_expected={has_header_expected} ---")
        with open(dummy_file_path, 'w', newline='') as f:
            f.write(content)
        try:
            dialog = AnimationPicklistDialog(dummy_file_path)
            if dialog.exec():
                selected = dialog.get_animation_selection_data()
                print("Selected for Animation:", selected)
                if selected:
                    print(f"  Header checkbox was: {dialog.header_checkbox.isChecked()}, Final has_header: {selected['has_header']}")
            else:
                print("Animation Dialog cancelled.")
        except RuntimeError as e:
             print(f"Dialog creation failed: {e}")

    import os
    if os.path.exists(dummy_file_path):
        os.remove(dummy_file_path)
    sys.exit()
# --- END OF FILE Warehouse-Path-Finder-main/animation_picklist_dialog.py ---