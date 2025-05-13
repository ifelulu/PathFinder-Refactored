# --- START OF FILE Warehouse-Path-Finder-main/services.py ---

import json
import math
import multiprocessing
import time
import csv
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
from PySide6.QtCore import QObject, Signal, QPointF, QRectF # Added QRectF for type hint
from PySide6.QtGui import QPolygonF, QTransform

# Assuming model and pathfinding are in the same directory or accessible
from model import WarehouseModel
# Import pathfinding functions (adjust path if needed)
from pathfinding import (create_grid_from_obstacles, dijkstra_precompute,
                         reconstruct_path, COST_OBSTACLE)

# --- Worker function for multiprocessing (needs to be top-level) ---
def _run_dijkstra_worker(args: Tuple[np.ndarray, Tuple[int, int], str]) -> Tuple[str, Optional[np.ndarray], Optional[np.ndarray]]:
    """Worker function for parallel Dijkstra precomputation."""
    grid, start_cell, start_name = args
    try:
        # Ensure necessary constants/imports are available here if running in separate process
        # COST_OBSTACLE is likely np.inf, check comparison
        if grid[start_cell] == COST_OBSTACLE: # Use COST_OBSTACLE which is np.inf
            print(f"[Worker] Skipping precomputation for '{start_name}': Start point is inside obstacle.")
            return start_name, None, None # Indicate failure

        dist_map, path_map = dijkstra_precompute(grid, start_cell)
        print(f"[Worker] Finished Dijkstra for '{start_name}'.")
        return start_name, dist_map, path_map
    except Exception as e:
        print(f"[Worker] Error during Dijkstra for '{start_name}': {e}")
        import traceback
        traceback.print_exc()
        return start_name, None, None

# --- Service Classes ---

class ProjectService(QObject):
    """Handles saving and loading warehouse project files."""

    project_load_failed = Signal(str)
    project_save_failed = Signal(str)
    project_operation_finished = Signal(str)

    def save_project(self, model: WarehouseModel, file_path: str) -> bool:
        """Saves the current model state to a JSON file."""
        print(f"[ProjectService] Saving project to: {file_path}")
        if not file_path.lower().endswith('.whp'):
            file_path += '.whp'

        project_data = {
            "version": "1.3",
            "pdf_path": model.current_pdf_path,
            "scale_info": {
                "pixels_per_unit": model.scale_pixels_per_unit,
                "calibration_unit": model.calibration_unit,
                "display_unit": model.display_unit
            },
            "grid_resolution_factor": model.grid_resolution_factor,
            "staging_area_penalty": model.staging_area_penalty,
            "animation_cart_width": model.animation_cart_width,
            "animation_cart_length": model.animation_cart_length,
            "obstacles": [[(p.x(), p.y()) for p in polygon] for polygon in model.obstacles],
            "staging_areas": [[(p.x(), p.y()) for p in polygon] for polygon in model.staging_areas],
            "pick_aisles": {name: (p.x(), p.y()) for name, p in model.pick_aisles.items()},
            "staging_locations": {name: (p.x(), p.y()) for name, p in model.staging_locations.items()},
        }
        try:
            with open(file_path, 'w') as f:
                json.dump(project_data, f, indent=4)
            print("[ProjectService] Project saved successfully.")
            self.project_operation_finished.emit(f"Project saved to {file_path}")
            return True
        except Exception as e:
            error_msg = f"Failed to save project file:\n{e}"
            print(f"[ProjectService] Error: {error_msg}")
            self.project_save_failed.emit(error_msg)
            return False

    def load_project(self, file_path: str) -> WarehouseModel | None:
        """Loads project state from a JSON file into a new WarehouseModel."""
        print(f"[ProjectService] Loading project from: {file_path}")
        try:
            with open(file_path, 'r') as f:
                project_data = json.load(f)

            if not isinstance(project_data, dict) or "version" not in project_data:
                raise ValueError("Invalid project file format (missing version).")

            model = WarehouseModel()
            model.set_current_project_path(file_path)
            model._current_pdf_path = project_data.get("pdf_path")
            pdf_bounds_data = project_data.get("pdf_bounds") # Assuming pdf_bounds might be stored
            if pdf_bounds_data: # Example how you might load bounds if stored
                 model._pdf_bounds = QRectF(pdf_bounds_data.get("x",0), pdf_bounds_data.get("y",0),
                                          pdf_bounds_data.get("width",0), pdf_bounds_data.get("height",0))


            scale_info = project_data.get("scale_info", {})
            model._scale_pixels_per_unit = scale_info.get("pixels_per_unit")
            model._calibration_unit = scale_info.get("calibration_unit")
            model._display_unit = scale_info.get("display_unit", "meters")

            model._grid_resolution_factor = project_data.get("grid_resolution_factor", 2.0)
            model._staging_area_penalty = project_data.get("staging_area_penalty", 10.0)
            model._animation_cart_width = project_data.get("animation_cart_width", 2.625)
            model._animation_cart_length = project_data.get("animation_cart_length", 5.458)

            model._obstacles = [QPolygonF([QPointF(px, py) for px, py in obs_points])
                                for obs_points in project_data.get("obstacles", [])]
            model._staging_areas = [QPolygonF([QPointF(px, py) for px, py in area_points])
                                    for area_points in project_data.get("staging_areas", [])]

            # --- Corrected/More Explicit Point Loading ---
            loaded_pick_aisles = project_data.get("pick_aisles", {})
            for name, point_coords_tuple in loaded_pick_aisles.items():
                # point_coords_tuple is expected to be (x, y)
                model._pick_aisles[name] = QPointF(point_coords_tuple[0], point_coords_tuple[1])

            loaded_staging_locations = project_data.get("staging_locations", {})
            for name, point_coords_tuple in loaded_staging_locations.items():
                model._staging_locations[name] = QPointF(point_coords_tuple[0], point_coords_tuple[1])
            # --- End of Correction ---

            print("[ProjectService] Project data loaded successfully.")
            model.mark_project_loaded()
            self.project_operation_finished.emit(f"Project '{model.current_project_path}' loaded.") # Use model's path
            return model

        except Exception as e:
            error_msg = f"Error loading project file:\n{e}"
            print(f"[ProjectService] Error: {error_msg}")
            import traceback
            traceback.print_exc()
            self.project_load_failed.emit(error_msg)
            return None


class PathfindingService(QObject):
    """Handles grid generation and pathfinding calculations."""
    grid_update_started = Signal()
    grid_update_finished = Signal(bool)
    precomputation_started = Signal(int)
    precomputation_progress = Signal(int, str)
    precomputation_finished = Signal(bool, list)

    def update_grid(self, model: WarehouseModel) -> bool:
        if not model.current_pdf_path or not model.is_scale_set or not model.pdf_bounds:
            msg = "[PathfindingService] Cannot update grid: PDF path, scale, or bounds not ready."
            print(msg); model.set_pathfinding_data(None); return False

        self.grid_update_started.emit()
        print("[PathfindingService] Updating pathfinding cost grid...")
        bounds = model.pdf_bounds
        grid_width = int(bounds.width() / model.grid_resolution_factor)
        grid_height = int(bounds.height() / model.grid_resolution_factor)

        if grid_width <= 0 or grid_height <= 0:
             print("[PathfindingService] Error: Invalid PDF dimensions for grid.")
             self.grid_update_finished.emit(False); return False
        try:
            grid = create_grid_from_obstacles(
                grid_width, grid_height, model.obstacles, model.grid_resolution_factor,
                staging_areas=model.staging_areas, staging_penalty=model.staging_area_penalty
            )
            if grid is None: raise ValueError("create_grid_from_obstacles returned None")
            model.set_pathfinding_data(grid)
            print("[PathfindingService] Grid updated successfully.")
            self.grid_update_finished.emit(True); return True
        except Exception as e:
            print(f"[PathfindingService] Error updating grid: {e}"); import traceback; traceback.print_exc()
            model.set_pathfinding_data(None); self.grid_update_finished.emit(False); return False

    def precompute_all_paths(self, model: WarehouseModel):
        if not model.can_precompute:
            print("[PathfindingService] Cannot precompute: Prerequisites not met.")
            self.precomputation_finished.emit(False, []); return

        if model.pathfinding_grid is None:
            if not self.update_grid(model) or model.pathfinding_grid is None:
                 print("[PathfindingService] Grid update failed, cannot precompute.")
                 self.precomputation_finished.emit(False, []); return

        start_points = model.pick_aisles
        if not start_points:
            print("[PathfindingService] No start points defined, skipping precomputation.")
            model.set_pathfinding_data(model.pathfinding_grid, {}, {}); self.precomputation_finished.emit(True, []); return

        self.precomputation_started.emit(len(start_points))
        print(f"[PathfindingService] Starting precomputation for {len(start_points)} points...")
        tasks, valid_start_names, initial_failed_points = [], [], []
        grid_h, grid_w = model.pathfinding_grid.shape
        for name, point_data in start_points.items():
            col = max(0, min(int(point_data.x() / model.grid_resolution_factor), grid_w - 1))
            row = max(0, min(int(point_data.y() / model.grid_resolution_factor), grid_h - 1))
            start_cell = (row, col)
            if model.pathfinding_grid[start_cell] == COST_OBSTACLE: initial_failed_points.append(f"{name} (in obstacle)")
            else: tasks.append((model.pathfinding_grid, start_cell, name)); valid_start_names.append(name)

        if not tasks:
            model.set_pathfinding_data(model.pathfinding_grid, {}, {}); self.precomputation_finished.emit(False, initial_failed_points); return

        start_time = time.time(); results_dist, results_path, final_failed_points, successful_count = {}, {}, initial_failed_points[:], 0
        try:
            num_workers = max(1, multiprocessing.cpu_count() - 1 if multiprocessing.cpu_count() > 1 else 1)
            chunksize = max(1, len(tasks) // num_workers if num_workers > 0 else 1)
            with multiprocessing.Pool(processes=num_workers) as pool:
                 for name, dist_map, path_map in pool.imap_unordered(_run_dijkstra_worker, tasks, chunksize=chunksize):
                    if dist_map is not None and path_map is not None:
                        results_dist[name] = dist_map; results_path[name] = path_map; successful_count += 1
                        self.precomputation_progress.emit(successful_count, name)
                    elif name in valid_start_names: final_failed_points.append(name)
                    QObject().thread().msleep(10) # Allow UI updates
            model.set_pathfinding_data(model.pathfinding_grid, results_dist, results_path)
            duration = time.time() - start_time; success = not bool(final_failed_points)
            print(f"[PathfindingService] Precomputation finished: {duration:.2f}s. Success: {success}. Failures: {final_failed_points}")
            self.precomputation_finished.emit(success, final_failed_points)
        except Exception as e:
            print(f"[PathfindingService] Multiprocessing error: {e}"); import traceback; traceback.print_exc()
            model.set_pathfinding_data(model.pathfinding_grid); self.precomputation_finished.emit(False, list(start_points.keys()))

    def get_shortest_path(self, model: WarehouseModel, start_name: str, end_name: str) -> tuple[list[QPointF] | None, float | None]:
        if not model.grid_is_valid or start_name not in model.path_maps or start_name not in model.distance_maps: return None, None
        start_point, end_point, grid = model.pick_aisles.get(start_name), model.staging_locations.get(end_name), model.pathfinding_grid
        if not all([start_point, end_point, grid is not None, model.is_scale_set]): return None, None

        gh, gw = grid.shape; res_f = model.grid_resolution_factor
        sc = max(0,min(int(start_point.x()/res_f),gw-1)); sr = max(0,min(int(start_point.y()/res_f),gh-1))
        ec = max(0,min(int(end_point.x()/res_f),gw-1)); er = max(0,min(int(end_point.y()/res_f),gh-1))
        s_cell, e_cell = (sr,sc), (er,ec)

        dist = model.distance_maps[start_name][er, ec]
        if dist == np.inf: return None, None
        path_cells = reconstruct_path(model.path_maps[start_name], s_cell, e_cell)
        if path_cells is None: return None, None

        hf = res_f / 2.0; path_pts = [QPointF(c*res_f+hf, r*res_f+hf) for r,c in path_cells]
        phys_dist_px = sum(math.sqrt((p2.x()-p1.x())**2 + (p2.y()-p1.y())**2) for p1,p2 in zip(path_pts, path_pts[1:]))
        dist_cal_unit = phys_dist_px / model.scale_pixels_per_unit
        disp_dist = self._convert_distance_units(dist_cal_unit, model.calibration_unit, model.display_unit)
        return path_pts, disp_dist

    def _convert_distance_units(self, value: float, from_unit: Optional[str], to_unit: Optional[str]) -> Optional[float]:
        if from_unit == to_unit or not from_unit or not to_unit: return value
        m_to_f = 3.28084
        if from_unit == "meters" and to_unit == "feet": return value * m_to_f
        if from_unit == "feet" and to_unit == "meters": return value / m_to_f
        print(f"[PathfindingService] Warn: Unsupported unit conversion {from_unit} to {to_unit}."); return None


class AnalysisService(QObject):
    """Handles loading and analyzing picklist data."""
    analysis_started = Signal(str) # filename
    analysis_complete = Signal(list, list, str, str) # detailed_results, warnings, unit, input_filename
    analysis_failed = Signal(str) # error message
    export_complete = Signal(str) # file_path
    export_failed = Signal(str) # error message

    def _parse_flexible_datetime(self, time_str: str) -> datetime | None:
        if not time_str: return None
        try: iso_str = time_str.replace(' ', 'T').replace('Z', '+00:00'); dt = datetime.fromisoformat(iso_str); return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError: pass
        for fmt in ["%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"]:
            try: dt = datetime.strptime(time_str, fmt); return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
            except ValueError: continue
        return None

    def load_and_analyze(self, model: WarehouseModel, file_path: str,
                         dialect: Any, has_header: bool, col_indices: dict):
        print(f"[AnalysisService] Starting analysis for: {file_path}")
        if not model.grid_is_valid: self.analysis_failed.emit("Pathfinding data not ready. Please Precompute."); return
        self.analysis_started.emit(file_path)
        results, warnings, proc_count, skip_count, no_start, no_end, no_path = [], [], 0,0,set(),set(),0
        id_idx,start_idx,end_idx,start_t_idx,end_t_idx = col_indices['id'],col_indices['start'],col_indices['end'],col_indices['start_time'],col_indices['end_time']
        path_svc = PathfindingService()
        try:
            with open(file_path, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.reader(f, dialect=dialect); row_num = 0
                if has_header: next(reader); row_num = 1
                for row_data in reader:
                    row_num+=1; proc_count+=1; p_id,s_name,e_name,s_t_str,e_t_str = f"R{row_num}","", "","",""
                    stat,p_date_str,dist_val = 'Pending',"",np.nan
                    try:
                        max_idx = max(id_idx,start_idx,end_idx,start_t_idx,end_t_idx)
                        if len(row_data)<=max_idx: raise IndexError("Short row")
                        p_id=row_data[id_idx].strip();s_name=row_data[start_idx].strip();e_name=row_data[end_idx].strip()
                        s_t_str=row_data[start_t_idx].strip();e_t_str=row_data[end_t_idx].strip()
                        p_dt=self._parse_flexible_datetime(s_t_str)
                        if p_dt: p_date_str=p_dt.strftime("%Y-%m-%d")
                        else: stat='DateParseErr'; warnings.append(f"R{row_num}({p_id}):Bad StartTime '{s_t_str}'")
                        if not s_name or not e_name: stat='MissingLoc'
                        elif s_name not in model.pick_aisles: no_start.add(s_name); stat='MissingStart'
                        elif e_name not in model.staging_locations: no_end.add(e_name); stat='MissingEnd'
                        elif s_name not in model.path_maps: stat=f'NoPrecomp:{s_name}'
                        else:
                            pts,d = path_svc.get_shortest_path(model,s_name,e_name)
                            if pts is None: no_path+=1; stat='Unreachable'; dist_val=np.inf
                            elif d is None: stat='Unit/ScaleErr'
                            else: dist_val=d; stat='Success'
                    except IndexError: stat='MalformedRow'; warnings.append(f"R{row_num}:Malformed")
                    except Exception as e: stat='ProcErr'; warnings.append(f"R{row_num}({p_id}):Err-{e}")
                    if stat!='Success': skip_count+=1
                    results.append({'id':p_id,'start':s_name,'end':e_name,'distance':dist_val,'status':stat,'date':p_date_str,'start_time':s_t_str,'end_time':e_t_str})
            warns = [f"Rows processed: {proc_count}"]
            if no_start: warns.append(f"Missing Starts: {','.join(sorted(list(no_start)))}")
            if no_end: warns.append(f"Missing Ends: {','.join(sorted(list(no_end)))}")
            if no_path > 0: warns.append(f"Unreachable: {no_path}")
            other_skips = skip_count - no_path # Adjust for more accurate "other" count
            if other_skips > 0: warns.append(f"Other Skipped/Error: {other_skips}")
            warns.extend(warnings)
            self.analysis_complete.emit(results, warns, model.display_unit, file_path)
        except Exception as e: self.analysis_failed.emit(f"Analysis failure: {e}")

    def export_results(self, results: list, unit: str, file_path: str):
        if not file_path.lower().endswith('.csv'): file_path += '.csv'
        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                hdr = ["Picklist ID", "Start Location", "End Location", f"Distance ({unit})", "Status", "Date", "Orig Start Time", "Orig End Time"]
                w = csv.writer(f); w.writerow(hdr)
                for r_d in results:
                    d = r_d.get('distance'); d_s = f"{d:.2f}" if pd.notna(d) and d!=np.inf else ("UNREACHABLE" if d==np.inf else "ERROR/SKIPPED")
                    w.writerow([r_d.get(k, '') for k in ['id','start','end']] + [d_s] + [r_d.get(k, '') for k in ['status','date','start_time','end_time']])
            self.export_complete.emit(file_path)
        except Exception as e: self.export_failed.emit(f"Export failed: {e}")


class AnimationService(QObject):
    """Handles preparation of data for animation."""
    preparation_started = Signal(str)
    preparation_complete = Signal(list, datetime) # Removed Optional from datetime
    preparation_failed = Signal(str)
    preparation_warning = Signal(str)

    def _parse_flexible_datetime(self, time_str: str) -> datetime | None:
        # (Same as in AnalysisService)
        if not time_str: return None
        try: iso_str = time_str.replace(' ', 'T').replace('Z', '+00:00'); dt = datetime.fromisoformat(iso_str); return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError: pass
        for fmt in ["%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"]:
            try: dt = datetime.strptime(time_str, fmt); return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
            except ValueError: continue
        return None

    def prepare_animation_data(self, model: WarehouseModel, file_path: str, selection_data: dict):
        if not model.grid_is_valid: self.preparation_failed.emit("Path data invalid. Precompute."); return
        self.preparation_started.emit(file_path)
        try: # Simplified selection data extraction
            dialect,has_header,indices = selection_data['dialect'],selection_data['has_header'],selection_data['indices']
            id_idx,s_loc_idx,e_loc_idx,s_time_idx,e_time_idx = indices['id'],indices['start_loc'],indices['end_loc'],indices['start_time'],indices['end_time']
        except KeyError as e: self.preparation_failed.emit(f"Missing selection key: {e}"); return

        temp_rows, earliest_dt, warnings = [], None, []
        path_svc = PathfindingService()

        try:
            with open(file_path, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.reader(f, dialect=dialect); row_num = 0
                if has_header: next(reader); row_num = 1
                for row in reader:
                    row_num+=1; temp_data={'row_num':row_num,'id':f"R{row_num}",'valid':False}
                    try:
                        max_idx = max(id_idx,s_loc_idx,e_loc_idx,s_time_idx,e_time_idx)
                        if len(row) <= max_idx: raise IndexError("Short row")
                        temp_data['id']=row[id_idx].strip(); s_name=row[s_loc_idx].strip(); e_name=row[e_loc_idx].strip()
                        s_t_str=row[s_time_idx].strip(); e_t_str=row[e_time_idx].strip()
                        if not all([s_name,e_name,s_t_str,e_t_str]): warnings.append(f"R{row_num}: Missing data"); temp_rows.append(temp_data); continue
                        if s_name not in model.pick_aisles or e_name not in model.staging_locations: warnings.append(f"R{row_num}: Loc not found"); temp_rows.append(temp_data); continue
                        s_dt=self._parse_flexible_datetime(s_t_str); e_dt=self._parse_flexible_datetime(e_t_str)
                        if not s_dt or not e_dt: warnings.append(f"R{row_num}: Invalid time"); temp_rows.append(temp_data); continue
                        if s_dt > e_dt: warnings.append(f"R{row_num}: Start after end"); temp_rows.append(temp_data); continue
                        cur_early = min(s_dt,e_dt)
                        if earliest_dt is None or cur_early < earliest_dt: earliest_dt = cur_early
                        temp_data.update({'start_name':s_name,'end_name':e_name,'start_dt':s_dt,'end_dt':e_dt,'valid':True}); temp_rows.append(temp_data)
                    except IndexError: warnings.append(f"R{row_num}: Malformed"); temp_rows.append(temp_data)
                    except Exception as e: warnings.append(f"R{row_num}({temp_data['id']}): Err-{e}"); temp_rows.append(temp_data)
            if earliest_dt is None: self.preparation_failed.emit("No valid timestamps."); return
        except Exception as e: self.preparation_failed.emit(f"File read error: {e}"); return

        anim_data = []
        for data in temp_rows:
            if not data.get('valid'): continue
            s_name,e_name,s_dt,e_dt,p_id,r_num = data['start_name'],data['end_name'],data['start_dt'],data['end_dt'],data['id'],data['row_num']
            try:
                s_time_s = max(0.0, (s_dt - earliest_dt).total_seconds())
                e_time_s = max(s_time_s, (e_dt - earliest_dt).total_seconds())
                pts, _ = path_svc.get_shortest_path(model, s_name, e_name)
                if pts is None: warnings.append(f"R{r_num}: No path {s_name}->{e_name}"); continue
                anim_data.append({'id':p_id,'start_name':s_name,'end_name':e_name,'start_time_s':s_time_s,'end_time_s':e_time_s,
                                     'start_dt':s_dt,'end_dt':e_dt,'path_points':pts})
            except Exception as e: warnings.append(f"R{r_num} (Pass 2): {e}")

        if not anim_data: self.preparation_failed.emit("No valid entries after path finding."); return
        if warnings: self.preparation_warning.emit(f"Processed with warnings. First: {warnings[0]}"); print("[AnimService] Warnings:", warnings)
        
        print(f"[AnimationService] Final prepared animation_data count: {len(anim_data)}")
        if anim_data:
            print(f"[AnimationService] First item in anim_data: {anim_data[0]}") # Print a sample
            # Check for 'start_dt' specifically
            if 'start_dt' in anim_data[0]:
                print(f"[AnimationService] First item start_dt: {anim_data[0]['start_dt']} (type: {type(anim_data[0]['start_dt'])})")
            else:
                print("[AnimationService] WARNING: 'start_dt' missing from first anim_data item!")
        print(f"[AnimationService] Emitting preparation_complete with earliest_dt: {earliest_dt}")
        
        self.preparation_complete.emit(anim_data, earliest_dt)

# --- END OF FILE Warehouse-Path-Finder-main/services.py ---