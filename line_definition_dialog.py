# --- START OF FILE Warehouse-Path-Finder-main/line_definition_dialog.py ---

import sys # <<< --- ADD THIS IMPORT
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QDialogButtonBox, QSpinBox, QFormLayout,
    QMessageBox
)
from PySide6.QtCore import Qt
# Assuming enums.py is accessible
# from enums import PointType # If you decide to use the enum, otherwise keep str

class LineDefinitionDialog(QDialog):
    """Dialog to get parameters for defining a line of points (Pick Aisles or Staging Locations)."""
    def __init__(self, point_type_str: str = "Pick Aisle", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Define {point_type_str} Line Parameters")

        self.point_type_str = point_type_str
        is_aisle = "Aisle" in point_type_str

        # --- Widgets ---
        self.cluster_input = QLineEdit()
        self.cluster_input.setPlaceholderText("e.g., A, B, AA")
        self.cluster_input.textChanged.connect(self._validate_cluster_input)


        self.start_num_spinbox = QSpinBox()
        self.start_num_spinbox.setMinimum(1)
        self.start_num_spinbox.setMaximum(9999)
        self.start_num_spinbox.setValue(1)

        self.end_num_spinbox = QSpinBox()
        self.end_num_spinbox.setMinimum(1)
        self.end_num_spinbox.setMaximum(9999)
        self.end_num_spinbox.setValue(1)

        info_text = ""
        if is_aisle:
            info_text = ("Note: Creates pairs like A1/A2, A3/A4, etc. "
                         "Ensure End Number allows for full pairs if desired (e.g., if start is odd, end should be even).")
        self.info_label = QLabel(info_text)
        self.info_label.setWordWrap(True)
        self.info_label.setVisible(bool(info_text))

        # --- Layout ---
        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        form_layout.addRow("Cluster Prefix (e.g., A, B, AA):", self.cluster_input)
        form_layout.addRow("Start Number:", self.start_num_spinbox)
        form_layout.addRow("End Number:", self.end_num_spinbox)

        main_layout.addLayout(form_layout)
        if is_aisle:
            main_layout.addWidget(self.info_label)

        # --- Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        # --- Connections ---
        self.start_num_spinbox.valueChanged.connect(self._validate_numbers)
        self.end_num_spinbox.valueChanged.connect(self._validate_numbers)
        
        self.setMinimumWidth(380)
        self._validate_numbers() # Initial validation

    def _validate_cluster_input(self, text: str):
        valid_chars = []
        for char in text:
            if char.isalpha():
                valid_chars.append(char.upper())
            elif char.isdigit() or char == '-':
                valid_chars.append(char)
        
        valid_text = "".join(valid_chars)
        if text != valid_text:
            self.cluster_input.setText(valid_text)

    def _validate_numbers(self):
        start_val = self.start_num_spinbox.value()
        end_val = self.end_num_spinbox.value()
        if end_val < start_val:
            self.end_num_spinbox.setValue(start_val)

    def _validate_and_accept(self):
        """Validates inputs before accepting the dialog."""
        cluster = self.cluster_input.text().strip()
        if not cluster:
            QMessageBox.warning(self, "Input Error", "Cluster Prefix cannot be empty.")
            return
        
        start_num = self.start_num_spinbox.value()
        end_num = self.end_num_spinbox.value()
        if end_num < start_num:
            QMessageBox.warning(self, "Input Error", "End Number cannot be less than Start Number.")
            return
            
        is_aisle = "Aisle" in self.point_type_str
        if is_aisle:
            total_numbers = (end_num - start_num) + 1
            if total_numbers < 1 :
                 QMessageBox.warning(self, "Input Error", "Number range results in no points/pairs.")
                 return
        
        self.accept()

    def get_parameters(self) -> tuple[str, int, int] | None:
        """Returns the entered parameters if the dialog was accepted."""
        if self.result() == QDialog.DialogCode.Accepted:
            cluster = self.cluster_input.text().strip().upper()
            start_num = self.start_num_spinbox.value()
            end_num = self.end_num_spinbox.value()
            return cluster, start_num, end_num
        return None

# Example Usage (for testing)
if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication # Import for standalone test

    app = QApplication(sys.argv) # sys is now defined
    dialog_aisle = LineDefinitionDialog("Pick Aisle")
    print("Testing Pick Aisle Dialog:")
    if dialog_aisle.exec():
        params = dialog_aisle.get_parameters()
        print(f"Aisle Parameters: {params}")
    else:
        print("Aisle Dialog cancelled.")

    dialog_staging = LineDefinitionDialog("Staging Location")
    print("\nTesting Staging Location Dialog:")
    if dialog_staging.exec():
        params = dialog_staging.get_parameters()
        print(f"Staging Parameters: {params}")
    else:
        print("Staging Dialog cancelled.")
    sys.exit() # sys is now defined
# --- END OF FILE Warehouse-Path-Finder-main/line_definition_dialog.py ---