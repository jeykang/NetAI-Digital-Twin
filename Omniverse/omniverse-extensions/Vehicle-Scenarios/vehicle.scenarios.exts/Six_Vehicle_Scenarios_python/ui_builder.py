# SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import boto3
from typing import List
import omni.ui as ui
from isaacsim.gui.components.element_wrappers import (
    Button,
    CheckBox,
    CollapsableFrame,
    ColorPicker,
    DropDown,
    FloatField,
    IntField,
    StateButton,
    StringField,
    TextBlock,
    XYPlot,
)
from isaacsim.gui.components.ui_utils import get_style

import omni.kit.commands
import omni
import omni.usd
import omni.kit.viewport.utility as vp_utility
from pxr import Usd, UsdGeom

class UIBuilder:
    def __init__(self):
        # Frames are sub-windows that can contain multiple UI elements
        self.frames = []
        # UI elements created using a UIElementWrapper from isaacsim.gui.components.element_wrappers
        self.wrapped_ui_elements = []
        print("Hello?\n\n\n")

    ###################################################################################
    #           The Functions Below Are Called Automatically By extension.py
    ###################################################################################

    def on_menu_callback(self):
        """Callback for when the UI is opened from the toolbar.
        This is called directly after build_ui().
        """
        pass

    def on_timeline_event(self, event):
        """Callback for Timeline events (Play, Pause, Stop)
        Args:
            event (omni.timeline.TimelineEventType): Event Type
        """
        pass

    def on_physics_step(self, step):
        """Callback for Physics Step.
        Physics steps only occur when the timeline is playing
        Args:
            step (float): Size of physics step
        """
        pass

    def on_stage_event(self, event):
        """Callback for Stage Events
        Args:
            event (omni.usd.StageEventType): Event Type
        """
        pass

    def cleanup(self):
        """
        Called when the stage is closed or the extension is hot reloaded.
        Perform any necessary cleanup such as removing active callback functions
        Buttons imported from isaacsim.gui.components.element_wrappers implement a cleanup function that should be called
        """
        # None of the UI elements in this template actually have any internal state that needs to be cleaned up.
        # But it is best practice to call cleanup() on all wrapped UI elements to simplify development.
        for ui_elem in self.wrapped_ui_elements:
            ui_elem.cleanup()

    def build_ui(self):
        """
        Build a custom UI tool to run your extension.
        This function will be called any time the UI window is closed and reopened.
        """
        # Create a UI frame that prints the latest UI event.
        self._create_status_report_frame()
        
        # Create a UI frame for scenario selection
        self._create_scenario_selection_frame()
        
    def _create_status_report_frame(self):
        self._status_report_frame = CollapsableFrame("Status Report", collapsed=False)
        with self._status_report_frame:
            with ui.VStack(style=get_style(), spacing=5, height=0):
                self._status_report_field = TextBlock(
                    "Last UI Event",
                    num_lines=3,
                    tooltip="Prints the latest change to this UI",
                    include_copy_button=True,
                )

    def _create_scenario_selection_frame(self):
        """Create a frame with 6 scenario selection buttons"""
        self._scenario_frame = CollapsableFrame("Scenario Selection", collapsed=False)
        with self._scenario_frame:
            with ui.VStack(style=get_style(), spacing=3, height=0):
                # Scenario Reset Button
                with ui.HStack():
                    scenario_btn = Button(
                        "Scenario Reset",
                        "Reset Scenario",
                        tooltip="Click to reset Scenario",
                        on_click_fn=self._on_scenario_clicked,
                    )
                    self.wrapped_ui_elements.append(scenario_btn)
                                
                # Scenario 1 Button
                with ui.HStack():
                    scenario1_btn = Button(
                        "Scenario 1",
                        "Load Scenario 1",
                        tooltip="Click to load and execute Scenario 1",
                        on_click_fn=self._on_scenario1_clicked,
                    )
                    self.wrapped_ui_elements.append(scenario1_btn)
                    
                    ui.Button(
                        "First-person",
                        width=20,
                        clicked_fn=self._on_scenario1_clicked_fp,
                    )
                
                # Scenario 2 Button
                with ui.HStack(spacing=5):
                    scenario2_btn = Button(
                        "Scenario 2",
                        "Load Scenario 2",
                        tooltip="Click to load and execute Scenario 2",
                        on_click_fn=self._on_scenario2_clicked,
                    )
                    self.wrapped_ui_elements.append(scenario2_btn)
                
                    ui.Button(
                        "First-person",
                        width=20,
                        clicked_fn=self._on_scenario2_clicked_fp,
                    )
                    
                # Scenario 3 Button
                with ui.HStack(spacing=5):
                    scenario3_btn = Button(
                        "Scenario 3",
                        "Load Scenario 3",
                        tooltip="Click to load and execute Scenario 3",
                        on_click_fn=self._on_scenario3_clicked,
                    )
                    self.wrapped_ui_elements.append(scenario3_btn)
                
                    ui.Button(
                        "First-person",
                        width=20,
                        clicked_fn=self._on_scenario3_clicked_fp,
                    )
                                    
                # Scenario 4 Button
                with ui.HStack(spacing=5):
                    scenario4_btn = Button(
                        "Scenario 4",
                        "Load Scenario 4",
                        tooltip="Click to load and execute Scenario 4",
                        on_click_fn=self._on_scenario4_clicked,
                    )
                    self.wrapped_ui_elements.append(scenario4_btn)
                
                    ui.Button(
                        "First-person",
                        width=20,
                        clicked_fn=self._on_scenario4_clicked_fp,
                    )
                                        
                # Scenario 5 Button
                with ui.HStack(spacing=5):
                    scenario5_btn = Button(
                        "Scenario 5",
                        "Load Scenario 5",
                        tooltip="Click to load and execute Scenario 5",
                        on_click_fn=self._on_scenario5_clicked,
                    )
                    self.wrapped_ui_elements.append(scenario5_btn)
                
                    ui.Button(
                        "First-person",
                        width=20,
                        clicked_fn=self._on_scenario5_clicked_fp,
                    )
                                        
                # Scenario 6 Button
                # with ui.HStack(spacing=5):
                #     scenario6_btn = Button(
                #         "Scenario 6",
                #         "Load Scenario 6",
                #         tooltip="Click to load and execute Scenario 6",
                #         on_click_fn=self._on_scenario6_clicked,
                #     )
                #     self.wrapped_ui_elements.append(scenario6_btn)
                
                #     ui.Button(
                #         "First-person",
                #         width=20,
                #         clicked_fn=self._on_scenario6_clicked_fp,
                #     )
                    
    ######################################################################################
    # Scenario Callback Functions
    ######################################################################################
    """
    05, 07~14는 배경용 보행자 -> 9명
    00~04, 06은 시나리오 주인공 -> 6명
    """
    def _on_scenario_clicked(self):
        for i in range(15):
            omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
                selected_paths=[f'/World/Characters/Character_{str(i).zfill(2)}'],
                stage=omni.usd.get_context().get_stage(),
                visible=True)

        # Get the stage
        stage = omni.usd.get_context().get_stage()

        # Get the parent prim
        cars_prim = stage.GetPrimAtPath("/World/Cars")
        
        # Get all children prims
        children = cars_prim.GetAllChildren()
        
        # Collect all children paths
        selected_paths = [str(child.GetPath()) for child in children]
        
        # Toggle visibility for all children
        if selected_paths:
            omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
                selected_paths=selected_paths,
                stage=stage,
                visible=True)                

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=['/World/Characters/Character_03'],
            new_translations=[-14.923717847526706, -18.64757162339876, 0.2099999999999964],
            new_rotation_eulers=[0.0, -0.0, 0.0],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            old_translations=[-14.972228332132394, -18.74816695525128, 0.21],
            old_rotation_eulers=[0.0, -0.0, 0.0],
            old_rotation_orders=[0, 1, 2],
            old_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=308.0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=['/World/Characters/Character_04'],
            new_translations=[-11.245398365809605, 15.517356538963021, 0.20499999999999996],
            new_rotation_eulers=[0.0, -0.0, 0.0],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            old_translations=[-11.192342456359885, 15.489250033088556, 0.205],
            old_rotation_eulers=[0.0, -0.0, 0.0],
            old_rotation_orders=[0, 1, 2],
            old_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=239.0)
            
        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=['/World/Characters/Character_05'],
            new_translations=[11.53039430872544, 7.2283092333034284, 0.20499999999996815],
            new_rotation_eulers=[0.0, -0.0, 25.065972884677084],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            old_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=0)
        
        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=['/World/Characters/Character_07'],
            new_translations=[9.818772411016198, -12.107697531036868, 0.21],
            new_rotation_eulers=[0.0, -0.0, -55.70304196615211],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            old_translations=[9.963750729118477, -12.10769753103686, 0.21],
            old_rotation_eulers=[0.0, -0.0, -55.70304196615211],
            old_rotation_orders=[0, 1, 2],
            old_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=269.0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=['/World/Characters/Character_08'],
            new_translations=[14.459380150908931, 10.591589939727303, 0.21000000000007812],
            new_rotation_eulers=[0.0, -0.0, 0.0],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            old_translations=[14.459380150908931, 10.603067762473712, 0.21000000000007812],
            old_rotation_eulers=[0.0, -0.0, 0.0],
            old_rotation_orders=[0, 1, 2],
            old_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=269.0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=['/World/Characters/Character_09'],
            new_translations=[-12.862238899338342, -1.298887155142526, 0.2],
            new_rotation_eulers=[0.0, -0.0, 124.0446335469345],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            old_translations=[-13.017446074822026, -1.2988871551425163, 0.2],
            old_rotation_eulers=[0.0, -0.0, 124.0446335469345],
            old_rotation_orders=[0, 1, 2],
            old_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=269.0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=['/World/Characters/Character_10'],
            new_translations=[-9.731688046261967, -22.68282127380371, 0.21],
            new_rotation_eulers=[0.0, -0.0, 180.0],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            old_translations=[-9.782825437973663, -22.68282127380371, 0.21],
            old_rotation_eulers=[0.0, -0.0, 180.0],
            old_rotation_orders=[0, 1, 2],
            old_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=269.0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=['/World/Characters/Character_11'],
            new_translations=[14.525748108248726, -10.74667168866984, 0.21000000000000013],
            new_rotation_eulers=[0.0, -0.0, -59.67177669857266],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            old_translations=[14.431165292121285, -10.74667168866984, 0.21],
            old_rotation_eulers=[0.0, -0.0, -59.67177669857266],
            old_rotation_orders=[0, 1, 2],
            old_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=269.0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=['/World/Characters/Character_12'],
            new_translations=[10.50795405410383, -22.696647951722472, 0.22],
            new_rotation_eulers=[0.0, -0.0, 180.0],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            old_translations=[10.50795405410383, -22.78308476827612, 0.22],
            old_rotation_eulers=[0.0, -0.0, 180.0],
            old_rotation_orders=[0, 1, 2],
            old_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=269.0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=['/World/Characters/Character_13'],
            new_translations=[13.725462899784016, -15.35886246178162, 0.22],
            new_rotation_eulers=[0.0, -0.0, 0.0],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            old_translations=[13.690201205377788, -15.35886246178162, 0.22],
            old_rotation_eulers=[0.0, -0.0, 0.0],
            old_rotation_orders=[0, 1, 2],
            old_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=269.0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=['/World/Characters/Character_14'],
            new_translations=[-8.92369609720042, -14.08313172574997, 0.13848043467742333],
            new_rotation_eulers=[0.0, -0.0, 82.59842084037382],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            old_translations=[-8.923696097200423, -14.15271506405442, 0.13848043467742333],
            old_rotation_eulers=[0.0, -0.0, 82.59842084037382],
            old_rotation_orders=[0, 1, 2],
            old_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=269.0)
        
        self._set_viewport_to_perspective()
                    
    def _on_scenario1_clicked(self):
        """Callback function for Scenario 1 button"""
        status = "Scenario 1 button was clicked!"
        self._status_report_field.set_text(status)
        print("Executing Scenario 1...")
        # TODO: Add scenario 1 implementation here
        Main_Character_Path = "/World/Characters/Character_06"
        Main_Car_Path = "/World/Cars/Mazda_RX_09"
        
        self._hide_all_cars()
        
        # 기본 pede 활성화/비활성화
        self._set_defualt_background_pedestrians()

        omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
            selected_paths=[Main_Character_Path],
            stage=omni.usd.get_context().get_stage(),
            visible=True)    
        
        omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
            selected_paths=[Main_Car_Path],
            stage=omni.usd.get_context().get_stage(),
            visible=True)    

        # Main Character
        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=[Main_Character_Path],
            new_translations=[1.9973385453323846, -14.203034203779684, 0.22083046485164504],
            new_rotation_eulers=[0.0, -0.0, 90],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=[Main_Car_Path],
            new_translations=[6.40647, -39.93200100025961, 0.014893616549670653],
            new_rotation_eulers=[89.99999999999994, 180.0, 5.684341886080802e-14],
            new_rotation_orders=[2, 1, 0],
            new_scales=[0.02, 0.02, 0.02],
            usd_context_name='',
            time_code=0)
        
        self._set_viewport_to_perspective()
        
        return Main_Car_Path
        
    def _on_scenario1_clicked_fp(self):
        Main_Car_Path = self._on_scenario1_clicked()
        self._set_viewport_camera(f"{Main_Car_Path}/{Main_Car_Path.split('/')[3][0]}_Front_Camera")
        
    def _on_scenario2_clicked(self):
        """Callback function for Scenario 2 button"""
        status = "Scenario 2 button was clicked!"
        self._status_report_field.set_text(status)
        print("Executing Scenario 2...")
        
        self._hide_all_cars()
        
        # 기본 pede 활성화/비활성화
        self._set_defualt_background_pedestrians()
        
        ## 여기서부터 수정
        Main_Character_Path = "/World/Characters/Character_00"
        Main_Car_Path = "/World/Cars/Hazer_Turbo_81___Low_poly_model_02"
             
        """ 실제 시나리오 Actor 1명 활성화 """
        omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
            selected_paths=[Main_Character_Path],
            stage=omni.usd.get_context().get_stage(),
            visible=True)             
        
        """ 실제 시나리오 Car 1대 활성화 """
        omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
            selected_paths=[Main_Car_Path],
            stage=omni.usd.get_context().get_stage(),
            visible=True)             
                    
        # Main Character & Car
        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=[Main_Character_Path],
            new_translations=[-10.144, -0.5734, 0.21],
            new_rotation_eulers=[0.0, 0.0, 0.0],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=[Main_Car_Path],
            new_translations=[0.01833, -27.19222, 0.00943],
            new_rotation_eulers=[90.0, 87.61648, 0.0],
            new_rotation_orders=[2, 1, 0],
            new_scales=[0.015, 0.015, 0.015],
            usd_context_name='',
            time_code=0)
        self._set_viewport_to_perspective()
        
        return Main_Car_Path
                
    def _on_scenario2_clicked_fp(self):
        Main_Car_Path = self._on_scenario2_clicked()
        self._set_viewport_camera(f"{Main_Car_Path}/{Main_Car_Path.split('/')[3][0]}_Front_Camera")

    def _on_scenario3_clicked(self):
        """Callback function for Scenario 3 button"""
        status = "Scenario 3 button was clicked!"
        self._status_report_field.set_text(status)
        print("Executing Scenario 3...")

        self._hide_all_cars()
        # 기본 pede 활성화/비활성화
        self._set_defualt_background_pedestrians()
        
        ## 여기서부터 수정
        Main_Character_Path = "/World/Characters/Character_01"
        Main_Car_Path = "/World/Cars/Jaguar_XJ12_LWB_X305"
        
        """ 실제 시나리오 Actor 1명 활성화 """
        omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
            selected_paths=[Main_Character_Path],
            stage=omni.usd.get_context().get_stage(),
            visible=True)             
        
        """ 실제 시나리오 Car 1대 활성화 """
        omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
            selected_paths=[Main_Car_Path],
            stage=omni.usd.get_context().get_stage(),
            visible=True)             
                    
        # Main Character & Car
        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=[Main_Character_Path],
            new_translations=[14.892247302767224, -9.839363627640413, 0.20999999999985075],
            new_rotation_eulers=[0.0, -0.0, 176.68460094899976],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=0.0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=[Main_Car_Path],
	        new_translations=[7.119865434106926, -16.74427, 0.01019476354160409],
            new_rotation_eulers=[89.99999999999983, 87.92523364481747, 8.810729923425242e-13],
            new_rotation_orders=[2, 1, 0],
            new_scales=[0.012999999523162843, 0.012999999523162843, 0.012999999523162843],
            usd_context_name='',
            time_code=0.0)
        self._set_viewport_to_perspective()
        
        return Main_Car_Path
        
    def _on_scenario3_clicked_fp(self):
        Main_Car_Path = self._on_scenario3_clicked()
        self._set_viewport_camera(f"{Main_Car_Path}/{Main_Car_Path.split('/')[3][0]}_Front_Camera")
        
    def _on_scenario4_clicked(self):
        """Callback function for Scenario 4 button"""
        status = "Scenario 4 button was clicked!"
        self._status_report_field.set_text(status)
        print("Executing Scenario 4...")
        
        # 기본 Car/Pede 활성화/비활성화
        self._hide_all_cars()
        self._set_defualt_background_pedestrians()
        
        ## 여기서부터 수정
        Main_Character_Path = "/World/Characters/Character_02"
        Main_Car_Path = "/World/Cars/Bentley_Mulliner_Batur"
        
        """ 실제 시나리오 Actor 1명 활성화 """
        omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
            selected_paths=[Main_Character_Path],
            stage=omni.usd.get_context().get_stage(),
            visible=True)             
        
        """ 실제 시나리오 Car 1대 활성화 """
        omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
            selected_paths=[Main_Car_Path],
            stage=omni.usd.get_context().get_stage(),
            visible=True)             
                    
        # Main Character & Car
        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=[Main_Character_Path],
            new_translations=[9.714786793446788, -15.194190969387353, 0.21699999999999198],
            new_rotation_eulers=[0.0, -0.0, -56.14425881787412],
            new_rotation_orders=[0, 1, 2],
            new_scales=[1.0, 1.0, 1.0],
            usd_context_name='',
            time_code=114.0)

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=[Main_Car_Path],
            new_translations=[7.813983069786175, -6.088460807160565, 0.015720350666300065],
            new_rotation_eulers=[90.0, -183.287684915079, 0.0],
            new_rotation_orders=[2, 1, 0],
            new_scales=[1.3, 1.3, 1.3],
            usd_context_name='',
            time_code=114.0)
        
        self._set_viewport_to_perspective()
        return Main_Car_Path
        
    def _on_scenario4_clicked_fp(self):
        Main_Car_Path = self._on_scenario4_clicked()
        self._set_viewport_camera(f"{Main_Car_Path}/{Main_Car_Path.split('/')[3][0]}_Front_Camera")    

    def _on_scenario5_clicked(self):
        """Callback function for Scenario 5 button"""
        status = "Scenario 5 button was clicked!"
        self._status_report_field.set_text(status)
        print("Executing Scenario 5...")
        
        # 기본 Car/Pede 활성화/비활성화
        self._hide_all_cars()
        self._set_defualt_background_pedestrians()
        
        ## 여기서부터 수정
        Main_Car_Path = "/World/Cars/WLow_Poly_Car___BMW_E30_1985_White"

        """ 실제 시나리오 Car 1대 활성화 """
        omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
            selected_paths=[Main_Car_Path],
            stage=omni.usd.get_context().get_stage(),
            visible=True)             

        omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
            count=1,
            paths=[Main_Car_Path],
            new_translations=[2.810596358755291, -40.37545851326919, -0.01364650658033062],
            new_rotation_eulers=[89.99999973540453, -2.7690491416383553e-07, -92.60445894670072],
            new_rotation_orders=[0, 1, 2],
            new_scales=[0.007, 0.007, 0.007],
            usd_context_name='',
            time_code=0.0)

        self._set_viewport_to_perspective()
        
        return Main_Car_Path
        
    def _on_scenario5_clicked_fp(self):
        Main_Car_Path = self._on_scenario5_clicked()
        self._set_viewport_camera(f"{Main_Car_Path}/{Main_Car_Path.split('/')[3][0]}_Front_Camera")    

    # def _on_scenario6_clicked(self):
    #     """Callback function for Scenario 6 button"""
    #     status = "Scenario 6 button was clicked!"
    #     self._status_report_field.set_text(status)
    #     print("Executing Scenario 6...")
        
    #     # 기본 Car/Pede 활성화/비활성화
    #     self._hide_all_cars()
    #     self._set_defualt_background_pedestrians()
        
    #     ## 여기서부터 수정
    #     Main_Character_Path = "/World/Characters/Character_02"
    #     Main_Car_Path = "/World/Cars/Bentley_Mulliner_Batur"
        
    #     """ 실제 시나리오 Actor 1명 활성화 """
    #     omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
    #         selected_paths=[Main_Character_Path],
    #         stage=omni.usd.get_context().get_stage(),
    #         visible=True)             
        
    #     """ 실제 시나리오 Car 1대 활성화 """
    #     omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
    #         selected_paths=[Main_Car_Path],
    #         stage=omni.usd.get_context().get_stage(),
    #         visible=True)             
                    
    #     # Main Character & Car
    #     omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
    #         count=1,
    #         paths=[Main_Character_Path],
    #         new_translations=[9.714786793446788, -15.194190969387353, 0.21699999999999198],
    #         new_rotation_eulers=[0.0, -0.0, -56.14425881787412],
    #         new_rotation_orders=[0, 1, 2],
    #         new_scales=[1.0, 1.0, 1.0],
    #         usd_context_name='',
    #         time_code=114.0)

    #     omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
    #         count=1,
    #         paths=[Main_Car_Path],
    #         new_translations=[7.813983069786175, -6.088460807160565, 0.015720350666300065],
    #         new_rotation_eulers=[90.0, -183.287684915079, 0.0],
    #         new_rotation_orders=[2, 1, 0],
    #         new_scales=[1.3, 1.3, 1.3],
    #         usd_context_name='',
    #         time_code=114.0)
    #     self._set_viewport_to_perspective()
        
    #     return Main_Car_Path
        
    # def _on_scenario6_clicked_fp(self):
    #     Main_Car_Path = self._on_scenario6_clicked()
    #     self._set_viewport_camera(f"{Main_Car_Path}/{Main_Car_Path.split('/')[3][0]}_Front_Camera")    

    ######################################################################################
    # Functions Below This Point Are Callback Functions Attached to UI Element Wrappers
    ######################################################################################

    def _on_int_field_value_changed_fn(self, new_value: int):
        status = f"Value was changed in int field to {new_value}"
        self._status_report_field.set_text(status)

    def _on_float_field_value_changed_fn(self, new_value: float):
        status = f"Value was changed in float field to {new_value}"
        self._status_report_field.set_text(status)

    def _on_string_field_value_changed_fn(self, new_value: str):
        status = f"Value was changed in string field to {new_value}"
        self._status_report_field.set_text(status)

    def _on_button_clicked_fn(self):
        status = "The Button was Clicked!"
        self._status_report_field.set_text(status)

    def _on_state_btn_a_click_fn(self):
        status = "State Button was Clicked in State A!"
        self._status_report_field.set_text(status)

    def _on_state_btn_b_click_fn(self):
        status = "State Button was Clicked in State B!"
        self._status_report_field.set_text(status)

    def _on_checkbox_click_fn(self, value: bool):
        status = f"CheckBox was set to {value}!"
        self._status_report_field.set_text(status)

    def _on_dropdown_item_selection(self, item: str):
        status = f"{item} was selected from DropDown"
        self._status_report_field.set_text(status)

    def _on_color_picked(self, color: List[float]):
        formatted_color = [float("%0.2f" % i) for i in color]
        status = f"RGBA Color {formatted_color} was picked in the ColorPicker"
        self._status_report_field.set_text(status)
        
    def _set_viewport_camera(self, camera_path: str):
        """
        Set the active viewport camera to a specified camera path
        
        Args:
            camera_path (str): Full USD path to the camera (e.g., "/World/Cameras/Front_Camera")
        """
        import omni.kit.viewport.utility as vp_utility
        from pxr import Usd, UsdGeom
        
        # Get the active viewport API
        viewport_api = vp_utility.get_active_viewport()
        
        if viewport_api is None:
            print("Error: No active viewport found")
            status = "Error: No active viewport found"
            self._status_report_field.set_text(status)
            return False
        
        # Validate camera path
        stage = omni.usd.get_context().get_stage()
        
        if stage is None:
            print("Error: No USD stage found")
            status = "Error: No USD stage found"
            self._status_report_field.set_text(status)
            return False
        
        prim = stage.GetPrimAtPath(camera_path)
        
        if not prim.IsValid():
            print(f"Error: Camera not found at path: {camera_path}")
            status = f"Error: Camera not found at path: {camera_path}"
            self._status_report_field.set_text(status)
            return False
        
        if not UsdGeom.Camera(prim):
            print(f"Error: Prim at {camera_path} is not a valid camera")
            status = f"Error: Prim at {camera_path} is not a valid camera"
            self._status_report_field.set_text(status)
            return False
        
        # Set the camera using viewport API's camera_path property
        viewport_api.camera_path = camera_path
        
        print(f"Viewport camera changed to: {camera_path}")
        status = f"Viewport camera changed to: {camera_path}"
        self._status_report_field.set_text(status)
        return True

    def _set_viewport_to_perspective(self):
        """
        Set the active viewport back to Perspective view (default camera)
        """
        import omni.kit.viewport.utility as vp_utility
        
        # Get the active viewport API
        viewport_api = vp_utility.get_active_viewport()
        
        if viewport_api is None:
            print("Error: No active viewport found")
            status = "Error: No active viewport found"
            self._status_report_field.set_text(status)
            return False
        
        # Set camera_path to empty string or None to return to Perspective view
        viewport_api.camera_path = "/OmniverseKit_Persp"
        
        print("Viewport changed to Perspective view")
        status = "Viewport changed to Perspective view"
        self._status_report_field.set_text(status)
        return True
    
    def _set_defualt_background_pedestrians(self):
        # 기본 Pedestrian 활성/비활성화
        for i in range(0, 7):
            omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
                selected_paths=[f'/World/Characters/Character_{str(i).zfill(2)}'],
                stage=omni.usd.get_context().get_stage(),
                visible=False)     
        """ 배경용 보행자 활성화 05, 07~14 => 9명"""
        for i in range(7, 15):
            omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
                selected_paths=[f'/World/Characters/Character_{str(i).zfill(2)}'],
                stage=omni.usd.get_context().get_stage(),
                visible=True)
        for i in range(3, 6):
            omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
                selected_paths=[f'/World/Characters/Character_{str(i).zfill(2)}'],
                stage=omni.usd.get_context().get_stage(),
                visible=True)
        
    def _hide_all_cars(self):
        # Get the stage
        stage = omni.usd.get_context().get_stage()

        # Get the parent prim
        cars_prim = stage.GetPrimAtPath("/World/Cars")
        
        # Get all children prims
        children = cars_prim.GetAllChildren()
        
        # Collect all children paths
        selected_paths = [str(child.GetPath()) for child in children]
        
        # Toggle visibility for all children
        if selected_paths:
            omni.kit.commands.execute('ToggleVisibilitySelectedPrims',
                selected_paths=selected_paths,
                stage=stage,
                visible=False)