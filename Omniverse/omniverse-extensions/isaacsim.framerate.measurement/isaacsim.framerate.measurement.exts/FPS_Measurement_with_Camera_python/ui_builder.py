# SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import omni.ui as ui
import omni.kit.app
import omni.usd
import omni.kit.commands
import omni.kit.viewport.utility as vp_utility
from omni.kit.window.filepicker import FilePickerDialog
import omni.client  # Required for file I/O on Nucleus servers
from pxr import Usd, UsdGeom, Gf
import time
from datetime import datetime
import json
import os
import asyncio

class UIBuilder:
    """
    Main class for building the UI and handling the logic for the Camera Recorder extension.
    It manages recording camera transforms, replaying them with interpolation, 
    saving/loading data (Nucleus compatible), and calculating performance metrics.
    """
    def __init__(self):
        # List to hold UI elements to prevent garbage collection
        self.wrapped_ui_elements = []
        
        # --- UI Element References ---
        self._lbl_status = None         # Status label (Ready, Recording, Playing)
        self._lbl_count = None          # Frame count label
        self._vstack_history = None     # Vertical stack for history logs
        self._field_duration = None     # Auto-stop duration input
        self._field_filepath = None     # File path input string field
        self._txt_log_field = None      # Log message box
        
        # --- File Picker Reference ---
        self._file_picker = None
        
        # --- State Variables ---
        self._is_recording = False
        self._is_playing = False
        self._recorded_data = []        # List to store [{'pos': Vec3d, 'rot': Quatd}, ...]
        self._playback_index = 0        # Current index for playback
        self._playback_camera_path = "" # Path to the temporary camera used for playback
        self._current_cam_path = "/OmniverseKit_Persp" # To track viewport switches
        
        # --- Settings ---
        self._target_fps = 60.0
        self._record_interval = 1.0 / self._target_fps  # Interval for recording (approx 0.016s)
        self._last_record_time = 0.0    # Timestamp of the last recorded frame
        self._auto_stop_frames = 0      # Target frame count for auto-stop
        self._recording_start_time = 0.0

        # --- FPS Measurement Variables ---
        self._fps_history = []          # List of strings for the last 5 playback records
        self._total_run_count = 0       # Total number of playback runs (for logging indices)
        self._playback_start_time = 0.0 # Timestamp when playback started
        self._played_frame_count = 0    # Number of frames actually rendered during playback
        
        # --- Update Subscription ---
        # Subscribes to the main application update loop to execute logic every frame
        self._update_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(self._on_update_event)
        
        print(f"Camera Recorder Initialized. Target FPS: {self._target_fps}")

    def cleanup(self):
        """
        Called when the extension shuts down or reloads.
        Releases resources, unsubscribes from events, and cleans up the stage.
        """
        self._update_sub = None
        self._is_recording = False
        self._is_playing = False
        self._recorded_data = []
        self._lbl_status = None
        
        # Delete temporary cameras and reset viewport
        self._cleanup_playback_resources()
        
        # Hide and destroy file picker if open
        if self._file_picker:
            self._file_picker.hide()
            self._file_picker = None

    def build_ui(self):
        """
        Entry point for building the UI widgets.
        Arranges the Status UI and Recorder UI vertically.
        """
        with ui.VStack(spacing=2):
            self._create_status_ui()
            self._create_recorder_ui()

    def _create_status_ui(self):
        """
        Creates the 'System Log' collapsible frame at the top.
        Contains a read-only multi-line string field for logging messages.
        """
        self._status_frame = ui.CollapsableFrame("System Log", collapsed=False, height=0)
        with self._status_frame:
            with ui.VStack(height=0, spacing=2, style={"margin": 2}):
                self._txt_log_field = ui.StringField(
                    multiline=True,
                    read_only=True,
                    height=85, 
                    style={"background_color": 0xFF222222, "font_size": 12, "color": 0xFFAAAAAA} 
                )
                self._log_message("System Ready.")

    def _create_recorder_ui(self):
        """
        Creates the main 'Recorder Control' collapsible frame.
        Contains status labels, control buttons, file I/O, and history.
        """
        self._recorder_frame = ui.CollapsableFrame("Recorder Control", collapsed=False)
        with self._recorder_frame:
            with ui.VStack(height=0, spacing=4, style={"margin": 4}):
                
                # 1. Status Info Line
                with ui.HStack(height=20):
                    ui.Label("Status:", width=45, style={"color": 0xFFAAAAAA, "font_size": 14})
                    self._lbl_status = ui.Label("Ready", width=90, style={"color": 0xFFFFFFFF, "font_size": 14})
                    ui.Spacer(width=5)
                    ui.Label("Frames:", width=50, style={"color": 0xFFAAAAAA, "font_size": 14})
                    self._lbl_count = ui.Label("0", style={"color": 0xFFFFFFFF, "font_size": 14})

                ui.Separator(height=6)

                # 2. Controls Line (Auto-Stop | Start | Stop)
                with ui.HStack(height=24, spacing=4):
                    ui.Label("Auto-Stop:", width=65, tooltip="0=Manual", style={"font_size": 14})
                    # Float drag for duration input
                    self._field_duration = ui.FloatDrag(min=0, max=3600, step=0.5, width=45, style={"font_size": 14})
                    self._field_duration.model.set_value(0.0)
                    ui.Spacer(width=5)
                    
                    ui.Button("Start", clicked_fn=self._on_rec_start, height=24, style={"background_color": 0xFF4444AA, "font_size": 14})
                    ui.Button("Stop", clicked_fn=self._on_rec_stop, width=55, height=24, style={"background_color": 0xFFAA4444, "font_size": 14})

                # 3. Playback Controls Line
                with ui.HStack(height=24, spacing=4):
                    ui.Button("Play Recording", height=24, clicked_fn=self._on_rec_play, tooltip="Replay Synced", style={"font_size": 14})
                    
                    # Manual Delete Button (Dark Grey with Red/Purple text)
                    ui.Button(
                        "Delete Cams", 
                        width=90,
                        height=24, 
                        clicked_fn=self._on_manual_delete, 
                        style={"background_color": 0xFF333333, "color": 0xFF5555FF, "font_size": 12},
                        tooltip="Delete all Recorded_Cam prims"
                    )

                ui.Separator(height=6)

                # 4. File I/O Line
                with ui.HStack(height=22, spacing=4):
                    ui.Label("File:", width=30, style={"font_size": 14})
                    default_path = os.path.abspath("camera_path.json").replace("\\", "/")
                    self._field_filepath = ui.StringField(height=22, style={"font_size": 14})
                    self._field_filepath.model.set_value(default_path)
                    
                    ui.Button("Search", width=60, height=22, clicked_fn=self._on_open_file_picker, style={"font_size": 12})

                with ui.HStack(height=22, spacing=4):
                    ui.Button("Save JSON", height=22, clicked_fn=self._on_save_file, style={"font_size": 13})
                    ui.Button("Load JSON", height=22, clicked_fn=self._on_load_file, style={"font_size": 13})

                ui.Separator(height=6)
                
                # 5. History Section
                ui.Label("History (Last 5):", height=14, style={"color": 0xFF00AAFF, "font_size": 12})
                self._vstack_history = ui.VStack(spacing=2)

    # =================================================================================
    #  Helper: Log Message
    # =================================================================================
    def _log_message(self, msg: str):
        """
        Appends a timestamped message to the system log text field.
        """
        if not self._txt_log_field: return
        timestamp = datetime.now().strftime("%H:%M:%S")
        current_text = self._txt_log_field.model.get_value_as_string()
        
        # Append new message at the bottom
        if current_text:
            updated_text = f"{current_text}\n[{timestamp}] {msg}"
        else:
            updated_text = f"[{timestamp}] {msg}"
            
        self._txt_log_field.model.set_value(updated_text)

    # =================================================================================
    #  File Picker
    # =================================================================================
    def _on_open_file_picker(self):
        """Opens the standard Omniverse file picker dialog."""
        if self._file_picker:
            self._file_picker.show()
            return
        
        self._file_picker = FilePickerDialog(
            "Select Camera Data File",
            allow_multi_selection=False,
            apply_button_label="Select",
            click_apply_handler=self._on_file_picked,
            item_filter_options=["JSON Files (*.json)"]
        )
        self._file_picker.show()

    def _on_file_picked(self, filename: str, dirname: str):
        """Callback when a file is selected from the picker."""
        if not filename: return
        # Normalize path separators for Omniverse/USD compatibility
        full_path = f"{dirname}/{filename}".replace("\\", "/")
        self._field_filepath.model.set_value(full_path)
        self._file_picker.hide()
        self._log_message(f"Selected: {filename}")

    # =================================================================================
    #  Recorder Logic
    # =================================================================================

    def _on_rec_start(self):
        """
        Handles the 'Start' button click.
        Initializes recording state, clears previous data, and sets up auto-stop if configured.
        """
        if self._is_playing: 
            self._cleanup_playback_resources()

        self._is_recording = True
        self._is_playing = False
        self._recorded_data = []
        self._last_record_time = 0.0
        
        # Configure auto-stop
        duration = self._field_duration.model.get_value_as_float()
        if duration > 0:
            self._auto_stop_frames = int(duration * self._target_fps)
            self._recording_start_time = time.time()
            stop_msg = f"Auto: {int(duration)}s"
        else:
            self._auto_stop_frames = 0
            stop_msg = "Manual"
        
        self._log_message(f"Start Rec ({stop_msg})...")
        
        if self._lbl_status: self._lbl_status.text = f"🔴 Rec..."
        if self._lbl_count: self._lbl_count.text = "0"

    def _on_rec_stop(self):
        """
        Handles the 'Stop' button click.
        Stops both recording and playback.
        """
        was_playing = self._is_playing
        
        # If stopping playback, finalize FPS calculation and cleanup resources
        if was_playing:
            self._finalize_fps_record()
            self._cleanup_playback_resources()

        if self._is_recording:
            self._log_message(f"Stopped. Captured {len(self._recorded_data)} f.")
        elif was_playing:
            self._log_message("Playback Stopped.")

        self._is_recording = False
        self._is_playing = False
        
        if self._lbl_status: self._lbl_status.text = "Stopped"

    def _on_rec_play(self):
        """
        Handles the 'Play Recording' button click.
        Sets up the environment for playback (temp camera, viewport switch).
        """
        if not self._recorded_data:
            self._log_message("Error: No data.")
            if self._lbl_status: self._lbl_status.text = "⚠️ No Data"
            return
        
        # Clean up any existing playback resources first
        self._cleanup_playback_resources()
        
        stage = omni.usd.get_context().get_stage()
        
        # 1. Create a temporary camera for playback to avoid conflicting with the default cam
        base_path = "/World/Recorded_Cam"
        self._playback_camera_path = omni.usd.get_stage_next_free_path(stage, base_path, False)
        new_cam_prim = UsdGeom.Camera.Define(stage, self._playback_camera_path)
        
        # 2. Copy optical attributes (Focal Length, Aperture, etc.) from the source camera
        src_prim = stage.GetPrimAtPath("/OmniverseKit_Persp")
        if src_prim.IsValid(): 
            self._copy_camera_attributes(src_prim, new_cam_prim.GetPrim())
        
        # 3. Switch the active viewport to look through the new camera
        self._set_viewport_camera(self._playback_camera_path)
        
        # 4. Initialize playback state variables
        self._is_playing = True
        self._is_recording = False
        self._playback_start_time = time.time()
        self._played_frame_count = 0
        
        self._log_message(f"Playing...")
        if self._lbl_status: self._lbl_status.text = "🟢 Playing..."

    def _on_manual_delete(self):
        """
        Handles the 'Delete Cams' button click.
        Manually triggers the cleanup process.
        """
        self._cleanup_playback_resources()
        self._log_message("Deleted recorded cameras.")

    def _on_update_event(self, e):
        """
        Main loop called every frame by the application.
        Handles data collection (Recording) and camera updates (Playback).
        """
        stage = omni.usd.get_context().get_stage()
        if not stage: return
        current_time = time.time()

        # --- Recording Logic ---
        if self._is_recording:
            # Check if enough time has passed to record the next frame (Throttle to 60FPS)
            if current_time - self._last_record_time >= self._record_interval:
                cam_prim = stage.GetPrimAtPath("/OmniverseKit_Persp")
                if cam_prim.IsValid():
                    xform = UsdGeom.Xformable(cam_prim)
                    world = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                    
                    # Store position and rotation
                    self._recorded_data.append({
                        "pos": world.ExtractTranslation(),
                        "rot": world.ExtractRotationQuat()
                    })
                    self._last_record_time = current_time
                    
                    if self._lbl_count: self._lbl_count.text = str(len(self._recorded_data))
                    
                    # Check for auto-stop condition
                    if self._auto_stop_frames > 0 and len(self._recorded_data) >= self._auto_stop_frames:
                        self._log_message("Auto-stop reached.")
                        self._on_rec_stop()

        # --- Playback Logic ---
        elif self._is_playing:
            # Calculate elapsed time to sync playback speed with recording speed
            elapsed = current_time - self._playback_start_time
            float_idx = elapsed * self._target_fps
            idx0 = int(float_idx)
            idx1 = idx0 + 1
            t = float_idx - idx0  # Interpolation factor (0.0 to 1.0)

            # Check if playback is finished
            if idx0 >= len(self._recorded_data) - 1:
                self._on_rec_stop()
                if self._lbl_status: self._lbl_status.text = "Done"
                self._log_message("Playback Done.")
                return

            # Interpolation (Linear for Pos, Slerp for Rot)
            data0 = self._recorded_data[idx0]
            data1 = self._recorded_data[idx1]
            
            interp_pos = Gf.Lerp(t, data0["pos"], data1["pos"])
            interp_rot = Gf.Slerp(t, data0["rot"], data1["rot"])

            # Apply interpolated transform to the playback camera
            cam_prim = stage.GetPrimAtPath(self._playback_camera_path)
            if cam_prim.IsValid():
                xform = UsdGeom.Xformable(cam_prim)
                mat = Gf.Matrix4d(Gf.Rotation(interp_rot), interp_pos)
                
                xform_op = None
                for op in xform.GetOrderedXformOps():
                    if op.GetOpType() == UsdGeom.XformOp.TypeTransform:
                        xform_op = op
                        break
                if not xform_op:
                    xform_op = xform.AddXformOp(UsdGeom.XformOp.TypeTransform, UsdGeom.XformOp.PrecisionDouble)
                xform_op.Set(mat)
            
            self._played_frame_count += 1

    def _cleanup_playback_resources(self):
        """
        Cleans up resources after playback.
        1. Switches viewport back to Perspective.
        2. Deletes ALL prims in the stage that start with 'Recorded_Cam'.
        """
        # Switch viewport
        self._set_viewport_camera("/OmniverseKit_Persp")
        
        # Aggressive deletion of temp cameras
        stage = omni.usd.get_context().get_stage()
        if stage:
            world = stage.GetPrimAtPath("/World")
            if world.IsValid():
                to_delete = [str(c.GetPath()) for c in world.GetChildren() if c.GetName().startswith("Recorded_Cam")]
                if to_delete:
                    omni.kit.commands.execute("DeletePrims", paths=to_delete)
        
        self._playback_camera_path = ""

    def _finalize_fps_record(self):
        """
        Calculates the real FPS of the playback session and updates the history UI.
        """
        duration = time.time() - self._playback_start_time
        if duration <= 0: return
        
        real_fps = self._played_frame_count / duration
        self._total_run_count += 1
        
        record_str = f"#{self._total_run_count}: {real_fps:.1f} FPS ({duration:.2f}s)"
        self._fps_history.append(record_str)
        
        # Keep only the last 5 records
        if len(self._fps_history) > 5: self._fps_history.pop(0)
        
        if self._vstack_history:
            self._vstack_history.clear()
            with self._vstack_history:
                for rec in reversed(self._fps_history):
                    ui.Label(rec, height=14, style={"color": 0xFFDDDDDD, "font_size": 12})

    # --- [IMPORTANT] Nucleus & Local File I/O Logic ---
    def _on_save_file(self):
        """
        Saves the recorded data to a JSON file using omni.client.
        Supports both local paths and Nucleus server paths (omniverse://).
        """
        if not self._recorded_data:
            self._log_message("Save Failed: Empty.")
            return
        
        path = self._field_filepath.model.get_value_as_string()
        out = []
        
        # Convert Gf types to simple lists for JSON serialization
        for f in self._recorded_data:
            p, r = f["pos"], f["rot"]
            out.append({"p": (p[0],p[1],p[2]), "r": (r.GetReal(), r.GetImaginary()[0], r.GetImaginary()[1], r.GetImaginary()[2])})
        
        try:
            # Convert Python object to JSON string bytes
            json_str = json.dumps(out, indent=4)
            # Use omni.client for Nucleus compatibility
            result = omni.client.write_file(path, json_str.encode("utf-8"))
            
            if result != omni.client.Result.OK: 
                raise Exception(f"Omni Client Error: {result}")
            
            if self._lbl_status: self._lbl_status.text = "Saved"
            self._log_message(f"Saved: .../{path.split('/')[-1]}")
            
        except Exception as e: 
            self._log_message(f"Save Error: {e}")

    def _on_load_file(self):
        """
        Loads recorded data from a JSON file using omni.client.
        Supports both local paths and Nucleus server paths.
        """
        path = self._field_filepath.model.get_value_as_string()
        
        try:
            # Use omni.client to read file content
            result, version, content = omni.client.read_file(path)
            
            if result != omni.client.Result.OK:
                self._log_message(f"Load Failed: {result}")
                return
            
            # Decode bytes -> string -> parse JSON
            json_str = memoryview(content).tobytes().decode("utf-8")
            data = json.loads(json_str)
            
            self._recorded_data = []
            for d in data:
                p, r = d["p"], d["r"]
                # Reconstruct Gf types (Vec3d, Quatd)
                self._recorded_data.append({"pos": Gf.Vec3d(*p), "rot": Gf.Quatd(r[0], Gf.Vec3d(r[1],r[2],r[3]))})
            
            if self._lbl_status: self._lbl_status.text = f"Loaded {len(data)}"
            if self._lbl_count: self._lbl_count.text = str(len(data))
            self._log_message(f"Loaded {len(data)} f.")
            
        except Exception as e:
            self._log_message(f"Load Error: {e}")

    def _copy_camera_attributes(self, src_prim, dst_prim):
        """
        Copies camera lens attributes (Focal Length, Aperture, etc.)
        from the source prim to the destination prim.
        """
        src = UsdGeom.Camera(src_prim)
        dst = UsdGeom.Camera(dst_prim)
        if not src or not dst: return
        
        attrs = [src.GetFocalLengthAttr(), src.GetHorizontalApertureAttr(), src.GetVerticalApertureAttr(),
                 src.GetClippingRangeAttr(), src.GetFStopAttr(), src.GetFocusDistanceAttr()]
        
        for a in attrs:
            if a.IsValid():
                da = dst_prim.GetAttribute(a.GetName())
                if da.IsValid(): da.Set(a.Get())

    def _set_viewport_camera(self, path):
        """
        Switches the active viewport to the specified camera path.
        Logs the change if the camera is different from the previous one.
        """
        vp = vp_utility.get_active_viewport()
        if vp: 
            old_cam = self._current_cam_path
            old_name = old_cam.split("/")[-1] if "/" in old_cam else old_cam
            new_name = path.split("/")[-1] if "/" in path else path
            
            if old_name != new_name: 
                self._log_message(f"View: {old_name}->{new_name}")
            
            vp.camera_path = path
            self._current_cam_path = path

    # --- Required Callback Placeholders ---
    def on_menu_callback(self): pass
    def on_timeline_event(self, e): pass
    def on_physics_step(self, s): pass
    def on_stage_event(self, e): pass