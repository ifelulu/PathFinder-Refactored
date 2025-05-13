# --- START OF FILE Warehouse-Path-Finder-main/picklist_column_dialog.py ---

import sys
import csv
# import matplotlib.pyplot as plt # Not used in this dialog
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QLabel, QPushButton, QDialogButtonBox, QMessageBox, QHeaderView,
    QCheckBox, QApplication, QFormLayout  # <<< --- ADD QFormLayout HERE
)
from PySide6.QtCore import Qt
from typing import List, Dict, Any, Optional # For type hinting
from io import StringIO # For testing with string-based CSV

MAX_PREVIEW_ROWS = 10

class PicklistColumnDialog(QDialog):
    def __init__(self, file_path: str, parent=None): # Added type hint
        super().__init__(parent)
        self.setWindowTitle("Select Picklist Columns for Analysis")
        self.file_path = file_path
        self.preview_data: List[List[str]] = []
        self.column_indices: Dict[str, int] = {'id': -1, 'start': -1, 'end': -1, 'start_time': -1, 'end_time': -1}
        self.dialect: Optional[csv.Dialect] = None
        self.has_header: bool = False
        self.raw_first_row: List[str] = []
        self.num_columns: int = 0

        if not self._load_preview():
            raise RuntimeError(f"Failed to load file preview for: {file_path}") # f-string

        self._setup_ui()
        self._update_combobox_options()
        self.resize(700, 500) # Adjusted size slightly

    def _load_preview(self) -> bool: # Added return type hint
        try:
            with open(self.file_path, 'r', newline='', encoding='utf-8-sig') as f:
                sample = f.read(2048); f.seek(0)
                try:
                    self.dialect = csv.Sniffer().sniff(sample, delimiters=',\t;| ')
                    self.has_header = csv.Sniffer().has_header(sample)
                except csv.Error:
                    QMessageBox.warning(self, "CSV Detection", "Could not auto-detect CSV. Assuming comma-separated. Please verify header checkbox.")
                    self.dialect = csv.excel
                    temp_reader = csv.reader(StringIO(sample), self.dialect) # Use StringIO for sample
                    try:
                        first_row_check = next(temp_reader)
                        if all(not item.replace('.', '', 1).isdigit() for item in first_row_check if item.strip()): self.has_header = True
                        else: self.has_header = False
                    except StopIteration: self.has_header = False
                
                reader = csv.reader(f, self.dialect)
                try:
                    self.raw_first_row = next(reader)
                    self.num_columns = len(self.raw_first_row)
                except StopIteration: QMessageBox.critical(self, "File Error", "File empty."); return False

                if not self.has_header: self.preview_data.append(self.raw_first_row)
                for i, row in enumerate(reader):
                    if len(self.preview_data) >= MAX_PREVIEW_ROWS: break
                    if len(row) == self.num_columns: self.preview_data.append(row)
            return True
        except Exception as e: QMessageBox.critical(self, "File Error", f"Preview error: {e}"); return False

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        preview_label = QLabel("File Preview (first rows):")
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(self.num_columns)
        headers = self.raw_first_row if self.has_header else [f"Column {i+1}" for i in range(self.num_columns)]
        self.preview_table.setHorizontalHeaderLabels(headers)
        self.preview_table.setRowCount(len(self.preview_data))
        for r_idx, row_data in enumerate(self.preview_data):
            for c_idx, cell_data in enumerate(row_data):
                if c_idx < self.num_columns:
                    item = QTableWidgetItem(str(cell_data)); item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.preview_table.setItem(r_idx, c_idx, item)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        main_layout.addWidget(preview_label); main_layout.addWidget(self.preview_table)

        self.header_checkbox = QCheckBox("First row contains headers")
        self.header_checkbox.setChecked(self.has_header)
        self.header_checkbox.stateChanged.connect(self._on_header_checkbox_changed)
        main_layout.addWidget(self.header_checkbox)

        # --- Column Selection --- QFormLayout is defined now
        form_layout = QFormLayout()
        self.id_combo = QComboBox()
        self.start_combo = QComboBox()
        self.end_combo = QComboBox()
        self.start_time_combo = QComboBox()
        self.end_time_combo = QComboBox()

        form_layout.addRow("Picklist ID Column:", self.id_combo)
        form_layout.addRow("Start Location (Pick Aisle) Column:", self.start_combo)
        form_layout.addRow("End Location (Staging) Column:", self.end_combo)
        form_layout.addRow("Start Time Column (for date filtering):", self.start_time_combo)
        form_layout.addRow("End Time Column (optional):", self.end_time_combo)
        main_layout.addLayout(form_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _on_header_checkbox_changed(self):
        self.has_header = self.header_checkbox.isChecked()
        current_preview_row_count = self.preview_table.rowCount()
        if self.has_header:
            self.preview_table.setHorizontalHeaderLabels(self.raw_first_row)
            if self.preview_data and current_preview_row_count > 0 and \
               all(self.preview_table.item(0,c).text() == str(self.raw_first_row[c]) for c in range(self.num_columns) if self.preview_table.item(0,c)):
                self.preview_table.removeRow(0)
        else:
            self.preview_table.setHorizontalHeaderLabels([f"Column {i+1}" for i in range(self.num_columns)])
            is_first_row_data_missing = True
            if current_preview_row_count > 0:
                if all(self.preview_table.item(0,c).text() == str(self.raw_first_row[c]) for c in range(self.num_columns) if self.preview_table.item(0,c)):
                    is_first_row_data_missing = False
            
            if is_first_row_data_missing:
                self.preview_table.insertRow(0)
                for c_idx, cell_data in enumerate(self.raw_first_row):
                     if c_idx < self.num_columns:
                         item = QTableWidgetItem(str(cell_data)); item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                         self.preview_table.setItem(0, c_idx, item)
        self._update_combobox_options()

    def _update_combobox_options(self):
        options = self.raw_first_row if self.has_header else [f"Column {i+1}" for i in range(self.num_columns)]
        options = [opt.strip() for opt in options if opt.strip()]
        if not options and self.has_header:
            QMessageBox.warning(self, "Header Warning", "Header row blank. Using generic names.")
            options = [f"Column {i+1}" for i in range(self.num_columns)]
        
        combos = [self.id_combo, self.start_combo, self.end_combo, self.start_time_combo, self.end_time_combo]
        current_texts = [c.currentText() for c in combos]
        for combo in combos: combo.clear(); combo.addItems([""] + options)
        for combo, text in zip(combos, current_texts):
            if text in options: combo.setCurrentText(text)
            else: combo.setCurrentIndex(0)

    def _validate_and_accept(self):
        id_idx = self.id_combo.currentIndex() -1
        start_idx = self.start_combo.currentIndex() -1
        end_idx = self.end_combo.currentIndex() -1
        start_time_idx = self.start_time_combo.currentIndex() -1
        end_time_idx = self.end_time_combo.currentIndex() -1

        if any(idx == -1 for idx in [id_idx, start_idx, end_idx, start_time_idx]):
            QMessageBox.warning(self, "Validation Error", "ID, Start Location, End Location, and Start Time columns are required.")
            return
        
        selected_values = [idx for idx in [id_idx, start_idx, end_idx, start_time_idx, end_time_idx] if idx != -1]
        if len(set(selected_values)) != len(selected_values):
            QMessageBox.warning(self, "Validation Error", "Please select unique columns for the chosen fields.")
            return

        self.column_indices = {'id': id_idx, 'start': start_idx, 'end': end_idx, 'start_time': start_time_idx, 'end_time': end_time_idx}
        self.has_header = self.header_checkbox.isChecked()
        super().accept()

    def get_selected_columns(self) -> Optional[Dict[str, Any]]:
        if self.result() == QDialog.DialogCode.Accepted:
            return {'indices': self.column_indices, 'dialect': self.dialect, 'has_header': self.has_header}
        return None

# Example Usage
if __name__ == '__main__':
    dummy_file_content_header = "Order,Item,Aisle_Start,Qty,Staging_End,StartTime,EndTime\n1001,ABC,A1,5,S1,2023-01-01 09:00,2023-01-01 09:05"
    dummy_file_path = "dummy_picklist_dialog_test.csv"
    
    app = QApplication(sys.argv)

    with open(dummy_file_path, 'w', newline='') as f:
        f.write(dummy_file_content_header)
    try:
        dialog = PicklistColumnDialog(dummy_file_path)
        if dialog.exec():
            print("Selected Columns:", dialog.get_selected_columns())
        else:
            print("Dialog cancelled.")
    except RuntimeError as e: print(f"Dialog error: {e}")
    
    import os
    if os.path.exists(dummy_file_path): os.remove(dummy_file_path)
    sys.exit()
# --- END OF FILE Warehouse-Path-Finder-main/picklist_column_dialog.py ---