# --- START OF FILE Warehouse-Path-Finder-main/animation_control_dialog.py ---
# (This one was already quite good from the previous iteration, just ensuring the test block import)
import sys
import math
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider,
    QListWidget, QListWidgetItem, QAbstractItemView, QDialogButtonBox, 
    QComboBox, QProgressBar, QDoubleSpinBox, QSpinBox, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, Slot, QDateTime, QTimeZone, QTimer # Added QTimer just in case
from datetime import datetime, timedelta, timezone
from typing import Set, List, Optional

# Assuming enums.py is accessible
from enums import AnimationMode

import re

def _get_cluster_from_name(name: Optional[str]) -> Optional[str]:
    """
    Extracts the leading alphabetic part of a name as the cluster.
    e.g., 'A' from 'A1', 'AA' from 'AA10', None from '123' or ''.
    """
    if not name or not isinstance(name, str): # Handle None or non-string inputs
        return None
    match = re.match(r"([a-zA-Z]+)", name)
    return match.group(1).upper() if match else None # Convert to uppercase for consistency

class AnimationControlDialog(QDialog):
    """Dialog to control picklist animation playback, filtering, and settings."""
    play_pause_toggled = Signal(bool) # True for play, False for pause
    reset_clicked = Signal()
    speed_changed = Signal(int) # Speed multiplier (1x to 256x)
    filters_changed = Signal(str, list, list, AnimationMode, int, bool) # date_str, start_clusters, end_clusters, mode, duration_min, keep_paths
    cart_dimensions_changed = Signal(float, float) # width, length (in project units)

    def __init__(self, all_start_clusters: Set[str], all_end_clusters: Set[str],
                 unique_dates: List[str], parent_cart_width: float, parent_cart_length: float,
                 parent_scale_unit: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Animation Controls")
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False) # Use Close button
        self.setMinimumWidth(550)

        self._is_playing = False
        self._current_mode = AnimationMode.CARTS
        self._current_path_duration_min = 5
        self._keep_paths_visible = False
        self._current_start_clusters = sorted(list(all_start_clusters))
        self._current_end_clusters = sorted(list(all_end_clusters))
        self._unique_dates = unique_dates # Already sorted by MainWindow
        self._selected_date_str = (unique_dates[0] if unique_dates else "All Dates") if "All Dates" not in unique_dates else "All Dates"


        self._setup_ui(all_start_clusters, all_end_clusters, unique_dates, parent_cart_width, parent_cart_length, parent_scale_unit)
        self._update_path_controls_visibility()

    def _setup_ui(self, all_start_clusters, all_end_clusters, unique_dates_list,
                  cart_width_val, cart_length_val, scale_unit_str):
        layout = QVBoxLayout(self)

        # Date Filter
        date_layout = QHBoxLayout(); date_layout.addWidget(QLabel("Filter Date:"))
        self.date_combo = QComboBox()
        # Ensure "All Dates" is an option, then add unique dates
        current_date_options = ["All Dates"]
        if unique_dates_list: current_date_options.extend(unique_dates_list)
        self.date_combo.addItems(current_date_options)
        if not unique_dates_list: self.date_combo.setPlaceholderText("No Dates in Data")
        # Set current text after populating
        if self._selected_date_str in current_date_options:
            self.date_combo.setCurrentText(self._selected_date_str)
        elif current_date_options:
            self.date_combo.setCurrentIndex(0) # Default to "All Dates" or first actual date

        date_layout.addWidget(self.date_combo); layout.addLayout(date_layout)

        # Time Display & Progress
        time_progress_layout = QVBoxLayout()
        self.time_label = QLabel("Time: N/A"); font = self.time_label.font(); font.setPointSize(12); font.setBold(True); self.time_label.setFont(font); self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar = QProgressBar(); self.progress_bar.setRange(0,1000); self.progress_bar.setValue(0); self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar {min-height: 18px; border: 1px solid grey; border-radius: 5px;} QProgressBar::chunk {background-color: #05B8CC; border-radius: 5px;}")
        time_progress_layout.addWidget(self.time_label); time_progress_layout.addWidget(self.progress_bar); layout.addLayout(time_progress_layout)

        # Playback Controls
        playback_layout = QHBoxLayout()
        self.play_pause_button = QPushButton("Play"); self.play_pause_button.setCheckable(True)
        self.reset_button = QPushButton("Reset")
        playback_layout.addWidget(self.play_pause_button); playback_layout.addWidget(self.reset_button); layout.addLayout(playback_layout)

        # Speed Control
        speed_layout = QHBoxLayout(); speed_layout.addWidget(QLabel("Speed:"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal); self.speed_slider.setMinimum(0); self.speed_slider.setMaximum(8); self.speed_slider.setValue(0) # Log scale: 2^0 to 2^8 = 1x to 256x
        self.speed_label = QLabel("1x")
        speed_layout.addWidget(self.speed_slider); speed_layout.addWidget(self.speed_label); layout.addLayout(speed_layout)

        # Animation Mode & Path Settings
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox(); self.mode_combo.addItems([am.value for am in AnimationMode])
        self.path_duration_label = QLabel("Path Visible (min):")
        self.path_duration_spinbox = QSpinBox(); self.path_duration_spinbox.setRange(1, 600); self.path_duration_spinbox.setValue(self._current_path_duration_min)
        self.keep_paths_checkbox = QCheckBox("Keep Paths Visible"); self.keep_paths_checkbox.setChecked(self._keep_paths_visible)
        mode_layout.addWidget(self.mode_combo); mode_layout.addSpacing(10)
        mode_layout.addWidget(self.path_duration_label); mode_layout.addWidget(self.path_duration_spinbox); mode_layout.addSpacing(5)
        mode_layout.addWidget(self.keep_paths_checkbox); mode_layout.addStretch(); layout.addLayout(mode_layout)

        # Cart Dimensions
        dims_layout = QHBoxLayout()
        self.cart_width_spinbox = QDoubleSpinBox(); self.cart_width_spinbox.setDecimals(3); self.cart_width_spinbox.setRange(0.1, 100.0); self.cart_width_spinbox.setSingleStep(0.1); self.cart_width_spinbox.setValue(cart_width_val)
        self.cart_length_spinbox = QDoubleSpinBox(); self.cart_length_spinbox.setDecimals(3); self.cart_length_spinbox.setRange(0.1, 100.0); self.cart_length_spinbox.setSingleStep(0.1); self.cart_length_spinbox.setValue(cart_length_val)
        dims_layout.addWidget(QLabel(f"Cart Width ({scale_unit_str}):")); dims_layout.addWidget(self.cart_width_spinbox)
        dims_layout.addWidget(QLabel(f"Cart Length ({scale_unit_str}):")); dims_layout.addWidget(self.cart_length_spinbox); layout.addLayout(dims_layout)

        # Cluster Filters
        filter_box_layout = QHBoxLayout()
        for title, cluster_list_attr, all_clusters_set in [
            ("Start Clusters:", "start_cluster_list", all_start_clusters),
            ("End Clusters:", "end_cluster_list", all_end_clusters)
        ]:
            cluster_layout = QVBoxLayout(); cluster_layout.addWidget(QLabel(title))
            list_widget = QListWidget(); list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            for cluster_name in sorted(list(all_clusters_set)):
                item = QListWidgetItem(cluster_name); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Checked)
                list_widget.addItem(item)
            setattr(self, cluster_list_attr, list_widget) # Store reference
            list_widget.itemChanged.connect(self._emit_filter_changes)
            cluster_layout.addWidget(list_widget); filter_box_layout.addLayout(cluster_layout)
        layout.addLayout(filter_box_layout)

        # Close Button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject); layout.addWidget(button_box)

        # Connect signals for controls that trigger filter changes
        self.date_combo.currentTextChanged.connect(self._emit_filter_changes)
        self.mode_combo.currentTextChanged.connect(self._emit_filter_changes)
        self.path_duration_spinbox.valueChanged.connect(self._emit_filter_changes)
        self.keep_paths_checkbox.stateChanged.connect(self._emit_filter_changes)
        self.play_pause_button.toggled.connect(self._on_play_pause_toggle)
        self.reset_button.clicked.connect(self._on_reset_click)
        self.speed_slider.valueChanged.connect(self._on_speed_change)
        self.cart_width_spinbox.valueChanged.connect(lambda v: self.cart_dimensions_changed.emit(v, self.cart_length_spinbox.value()))
        self.cart_length_spinbox.valueChanged.connect(lambda v: self.cart_dimensions_changed.emit(self.cart_width_spinbox.value(), v))

    @Slot(bool)
    def _on_play_pause_toggle(self, checked: bool):
        self._is_playing = checked
        self.play_pause_button.setText("Pause" if checked else "Play")
        self.play_pause_toggled.emit(checked)

    @Slot()
    def _on_reset_click(self):
        self.play_pause_button.setChecked(False)
        self.reset_clicked.emit()

    @Slot(int)
    def _on_speed_change(self, value: int):
        speed_multiplier = int(math.pow(2, value))
        self.speed_label.setText(f"{speed_multiplier}x")
        self.speed_changed.emit(speed_multiplier)

    @Slot()
    def _emit_filter_changes(self):
        self._selected_date_str = self.date_combo.currentText()
        self._current_start_clusters = [self.start_cluster_list.item(i).text() for i in range(self.start_cluster_list.count()) if self.start_cluster_list.item(i).checkState() == Qt.CheckState.Checked]
        self._current_end_clusters = [self.end_cluster_list.item(i).text() for i in range(self.end_cluster_list.count()) if self.end_cluster_list.item(i).checkState() == Qt.CheckState.Checked]
        
        try: # Robustly get enum from value
            self._current_mode = AnimationMode(self.mode_combo.currentText())
        except ValueError:
            self._current_mode = AnimationMode.CARTS # Fallback if text is somehow invalid

        self._current_path_duration_min = self.path_duration_spinbox.value()
        self._keep_paths_visible = self.keep_paths_checkbox.isChecked()
        self._update_path_controls_visibility()
        self.filters_changed.emit(self._selected_date_str, self._current_start_clusters, self._current_end_clusters,
                                  self._current_mode, self._current_path_duration_min, self._keep_paths_visible)

    def _update_path_controls_visibility(self):
        is_path_lines_mode = (self._current_mode == AnimationMode.PATH_LINES)
        self.path_duration_label.setVisible(is_path_lines_mode)
        self.path_duration_spinbox.setVisible(is_path_lines_mode)
        self.keep_paths_checkbox.setVisible(is_path_lines_mode)
        self.path_duration_spinbox.setEnabled(is_path_lines_mode and not self._keep_paths_visible)

    def update_time_display(self, current_sim_time_s: float, display_range_start_dt: Optional[datetime]):
        if display_range_start_dt:
            try:
                current_display_dt = display_range_start_dt + timedelta(seconds=current_sim_time_s)
                time_str = current_display_dt.strftime("%I:%M:%S %p").lstrip('0')
                if not time_str.strip(): time_str = current_display_dt.strftime("%H:%M:%S") # Fallback for some locales
                self.time_label.setText(f"Time: {time_str}")
            except Exception: self.time_label.setText(f"Time: {current_sim_time_s:.1f}s (Date Error)")
        else: self.time_label.setText(f"Time: {current_sim_time_s:.1f}s")

    def update_progress(self, current_sim_time_s: float, min_sim_time_s: float, max_sim_time_s: float):
        duration = max_sim_time_s - min_sim_time_s
        if duration > 1e-6: # Avoid division by zero
            progress_val = int(((current_sim_time_s - min_sim_time_s) / duration) * 1000)
            self.progress_bar.setValue(max(0, min(progress_val, 1000)))
        else:
            self.progress_bar.setValue(1000 if current_sim_time_s >= min_sim_time_s else 0)

    def select_date(self, date_str: str):
        idx = self.date_combo.findText(date_str)
        if idx >= 0: self.date_combo.setCurrentIndex(idx)
        elif self.date_combo.count() > 0 : self.date_combo.setCurrentIndex(0) # Default to first if not found

    def reject(self):
        if self._is_playing: self.play_pause_button.setChecked(False)
        super().reject()

# Example Usage
if __name__ == '__main__':
    # --- ADD THIS IMPORT ---
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dummy_starts = {"A", "B"}
    dummy_ends = {"S", "D"}
    dummy_dates = ["2023-01-01", "2023-01-02"]
    dialog = AnimationControlDialog(dummy_starts, dummy_ends, dummy_dates, 1.0, 2.0, "m")
    dialog.show()
    sys.exit(app.exec())
# --- END OF FILE Warehouse-Path-Finder-main/animation_control_dialog.py ---