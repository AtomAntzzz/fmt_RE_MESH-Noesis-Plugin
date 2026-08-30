# RE Engine Mesh/Animtion Noesis Tool
# Version: v0.22
# Last Release: August 30, 2026
# Author: AtomAntzzz

import maya.cmds as cmds
import maya.mel as mel
import re
import os
import subprocess
import time
import json
import random


def build_noesis_command(noesis_path, input_file, fbx_path, log_path,
                          optimize=True, framerate=60, batch=False,
                          no_prompt=False):
    """Build a Windows command line for a Noesis command-mode export."""
    arguments = [
        noesis_path,
        "?cmode",
        input_file,
        fbx_path,
    ]

    if not optimize:
        arguments.append("-fbxnooptimize")

    arguments.extend([
        "-fbxmeshmerge",
        "-logfile",
        log_path,
        "-fbxframerate",
        str(framerate),
    ])

    if batch:
        arguments.append("-b")
    if no_prompt:
        arguments.append("-noprompt")

    return subprocess.list2cmdline(arguments)


def launch_noesis_command(command, working_directory):
    """Launch Noesis with a legacy Windows code page available to Python plugins."""
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    # Noesis 4.474 embeds Python 3.2, whose plugin loader can fail with error
    # -306 when Windows' system code page is UTF-8. A real CP936 console keeps
    # plugin loading stable. Do not redirect stdout/stderr: pipes detach Noesis
    # from the console code page it needs during Python initialization.
    console_command = "chcp 936>nul & " + command
    return subprocess.Popen(
        console_command,
        shell=True,
        cwd=working_directory,
        startupinfo=startupinfo,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


class AnimationExporterUI:
    def __init__(self):
        self.window_name = "REEM_Maya_Window"
        self.animation_data = []
        self.noesis_path = ""
        self.names_to_objects = {}
        self.current_extension = ""
        
        self.games_list = [
            "RE2 RT", "RE3 RT", "RE2", "RE3", "RE4", "DMC5", "RE7", 
            "RE7 RT", "RE8", "MHRise", "MHRSunbreak", "SF6", 
            "REVerse", "AJ_AAT", "DD2"
        ]
        
        self.game_extensions = {
            "RE2 RT": ".mesh.2109108288",
            "RE3 RT": ".mesh.2109108288", 
            "RE2": ".mesh.1808312334",
            "RE3": ".mesh.1902042334",
            "RE4": ".mesh.221108797",
            "DMC5": ".mesh.1808282334",
            "RE7": ".mesh.32",
            "RE7 RT": ".mesh.220128762",
            "RE8": ".mesh.2101050001",
            "MHRise": ".mesh.2008058288",
            "MHRSunbreak": ".mesh.2109148288",
            "SF6": ".mesh.230110883",
            "REVerse": ".mesh.2102020001",
            "AJ_AAT": ".mesh.230612127",
            "DD2": ".mesh.231011879"
        }
        
        self.load_settings()
        self.create_ui()
    
    def create_ui(self):
        """创建UI界面"""
        # 如果窗口已存在，删除它
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
        
        # 创建窗口
        self.window = cmds.window(
            self.window_name,
            title="RE Engine Mesh/Animation Noesis Tool",
            widthHeight=(300, 500),  # 增加窗口高度以容纳新按钮
            resizeToFitChildren=True,
            sizeable=False
        )
        
        # 主布局 - 增加内边距和间距
        main_layout = cmds.columnLayout(
            adjustableColumn=True,
            columnAttach=('both', 15),
            rowSpacing=10,
            parent=self.window
        )
        
        # ===== 标题区域 =====
        cmds.text(label="RE Engine Mesh/Animtion Noesis Tool", font="boldLabelFont", height=25)
        cmds.separator(height=10, style="in")
        

        # Config 区域 
        cmds.text(label="Noesis Path", font="boldLabelFont", align="left")
        #cmds.text(label="Config", font="boldLabelFont", align="left")
        """
        # 当前游戏菜单
        self.game_combo = cmds.optionMenu(
            label="Game",
            enable=True,
            changeCommand=self.on_game_option_changed,
            height=30
        )
        
        # 填充菜单项
        for game in self.games_list:
            cmds.menuItem(label=game, parent=self.game_combo)
        
        # 初始化game_combo
        current_game = self.get_current_game()
        if current_game in self.games_list:
            cmds.optionMenu(self.game_combo, edit=True, value=current_game)
        
        # 文字显示扩展名    
        self.text_current_extension = cmds.text(label=f".mesh{self.current_extension}", font="boldLabelFont", align="left")
        """

        #self.chk_bone_numbers = cmds.checkBox(label="Use Bone Numbers", value=True) # 是否在骨骼名称前面添加序号，3dsmax的习惯，maya不用加
        # cmds.setParent('..')

        # Noesis Path
        #cmds.text(label="Noesis Path:", font="boldLabelFont", align="left")
        noesis_row = cmds.rowLayout(numberOfColumns=2, columnWidth2=(300, 80),
                                    columnAttach2=('both', 'both'),
                                    columnAlign2=('center', 'center'))
        self.noesis_path_field = cmds.textField(text=self.noesis_path, width=300)
        cmds.button(label="Browse", command=self.browse_noesis, width=80,height=25)
        cmds.setParent('..')

        cmds.separator(height=10)

        # Import 区域
        cmds.text(label="Import", font="boldLabelFont", align="left")
        self.import_button = cmds.button(
            label="Import Mesh/Animation",
            command=self.import_file,
            height=30,
            backgroundColor=(0.45, 0.55, 0.7)
        )

        # Import Options
        import_options_col = cmds.rowColumnLayout(numberOfColumns=2, 
                     columnAttach=[(1, 'left', 5), (2, 'left', 5)],
                     columnWidth=[(1, 200), (2, 200)])
        self.chk_new_scene = cmds.checkBox(label="New Scene On Import", value=False)
        self.chk_folder = cmds.checkBox(label="Import Folder", value=False)
        self.chk_fbx_optimize = cmds.checkBox(label="FBX Optimize", value=True)
        self.chk_delete_fbx = cmds.checkBox(label="Delete FBX", value=True)
        #self.chk_populate_bones = cmds.checkBox(label="Populate Bones Lists", value=False)
        cmds.setParent('..')
           
        '''
        # 添加fixframerate按钮
        self.fix_framerate_button = cmds.button(
            label="Fix Frame Rate for DD2/RE4",
            command=self.fix_framerate,
            height=35,
            backgroundColor=(0.7, 0.45, 0.6),
            annotation="Convert animation from 30fps to 60fps with frame offset for DD2/RE4 compatibility"
        )
        '''
                
        cmds.separator(height=15)
        
        # =====动画列表标签和下拉框=====
        cmds.text(label="Animation List", align="left", font="boldLabelFont")
        self.animation_combo = cmds.optionMenu(
            label="",
            enable=False,
            changeCommand=self.on_animation_selected,
            height=30
        )
        cmds.menuItem(label="No animations loaded", parent=self.animation_combo)
        '''
        # 添加 Set Timeline Range 按钮
        self.set_timeline_button = cmds.button(
            label="Set Timeline to Selected Animation",
            command=self.set_timeline_range,
            height=30,
            enable=False,
            backgroundColor=(0.6, 0.5, 0.8),
            annotation="Adjust Maya timeline to match the selected animation's frame range"
        )
        '''
        
        # Manually Paste Noesis List按钮
        self.paste_button = cmds.button(
            label="Manually Paste Noesis List",
            command=self.show_input_dialog,
            height=30,
            backgroundColor=(0.45, 0.55, 0.7)
        )  
        
        cmds.separator(height=15)
        
        # ===== Export 区域 =====
        cmds.text(label="Export", align="left", font="boldLabelFont")
        
        # 单选按钮组
        self.radio_collection = cmds.radioCollection()
        
        self.export_selected_radio = cmds.radioButton(
            label="Export Selected Animation",
            collection=self.radio_collection,
            select=True,
            onCommand=self.on_export_option_changed
        )
        
        self.export_all_radio = cmds.radioButton(
            label="Export All Animations",
            collection=self.radio_collection,
            onCommand=self.on_export_option_changed
        )
        
        # 导出按钮
        self.export_button = cmds.button(
            label="Export",
            command=self.export_animation,
            height=40,
            enable=False,
            backgroundColor=(0.4, 0.7, 0.4)
        )
        
        cmds.separator(height=15)
        
        # 状态标签
        self.status_text = cmds.text(
            label="Ready - Please fill Noesis Path first",
            align="center",
            backgroundColor=(0.25, 0.25, 0.25),
            height=25
        )
        
        # 显示窗口
        cmds.showWindow(self.window)

    # Import Functions Begin----------------------------------------------------------------------------
    def browse_noesis(self, *args):
        """查找noesis.exe路径"""
        file_filter = "Executable Files (*.exe);;All Files (*.*)"
        result = cmds.fileDialog2(
            fileFilter=file_filter,
            dialogStyle=2,
            caption="Select Noesis.exe",
            fileMode=1,
            okCaption="Select"
        )
        
        if result:
            self.noesis_path = result[0]
            cmds.textField(self.noesis_path_field, edit=True, text=self.noesis_path)
            self.save_settings()
            self.update_status(f"Noesis path set: {os.path.basename(self.noesis_path)}")
    
    def NoesisComponentsFound(self):
        """验证Noesis路径"""
        self.noesis_path = cmds.textField(self.noesis_path_field, query=True, text=True)
        if not self.noesis_path or not os.path.exists(self.noesis_path):
            cmds.warning("Please set a valid Noesis path first!")
            self.update_status("Error: Invalid Noesis path")
            return False
        return True        
            
    def import_file(self, *args):
        """从Noesis导入模型/动画"""
        if not self.NoesisComponentsFound():
            return
        
        # 选择导入文件
        file_filter = (
            "RE Engine Mesh/MOTLIST (*.mesh.* *.motlist.*);;"
            "All Files (*.*)"
        )

        input_file = cmds.fileDialog2(
            fileFilter=file_filter,
            dialogStyle=2,
            caption="Select Mesh or MOTLIST File",
            fileMode=1,
            okCaption="Import"
        )
        
        if not input_file:
            self.update_status("Import cancelled")
            return
            
        input_file = input_file[0]
        
        # 默认只处理一个文件
        files_to_process = [input_file]
        # 选择导入文件夹会获取选中文件所在文件夹下的其他.mesh.文件，.motlist.文件不会被加入
        if cmds.checkBox(self.chk_folder, query=True, value=True):
            # 获取路径
            file_dir = os.path.dirname(input_file)
            # 获取所有.mesh.文件
            files_to_process = [f for f in os.listdir(file_dir) 
                                if '.mesh.' in f.lower() and os.path.isfile(os.path.join(file_dir, f))]
            # .mesh.文件路径+文件名
            files_to_process = [os.path.join(file_dir, f) for f in files_to_process]
            
        # 重置场景选项
        if cmds.checkBox(self.chk_new_scene, query=True, value=True):
            cmds.file(new=True, force=True)
            print("Scene reset before importing") 
   
        noesis_output = ""
        success = False    
        last_ext = self.current_extension
        
        # 开始导入
        for file in files_to_process:
            self.update_status(f"Importing: {os.path.basename(file)}...")
        
            # 导入mesh/动画
            success, noesis_output = self.import_from_noesis(file)
        
            # 导入失败，直接下一个
            if not success:
                continue
            
            # 导入成功
            
            # 根据导入文件的扩展名更新当前游戏配置
            this_ext = os.path.splitext(file)[1]
            if this_ext != last_ext:
                last_ext = this_ext
                # 根据扩展名查找对应的游戏
                full_ext = f".mesh{this_ext}"
                game_index = self.get_extension_index(full_ext)
                if game_index >= 0:
                    self.change_current_game(game_index)
                    # 更新列表选择
                    cmds.optionMenu(self.game_combo, edit=True, value=self.get_current_game())
                    
            # 后处理导入的mesh/动画
            self.post_process_imported_objects(file, "", None,False)
            
            # 解析动画文本数据
            if ".motlist." in file:
                # 根据noesisoutput解析动画数据
                if noesis_output:
                    self.parse_animation_text(noesis_output)
                else: # 是MOTLIST文件但Log不可用
                    self.update_status("Import complete, Log is null")
            else: # 模型文件，不需要解析动画文本
                self.update_status("Mesh import complete")
        

    
    '''
    def import_scene(self, *args):
    """从Noesis导入场景"""
        if not self.NoesisComponentsFound():
            return
    '''
    
    def import_from_noesis(self, input_file):
        """从Noesis导入模型/动画以及log"""
        noesis_output = ""
        
        if not input_file:
            cmds.error(f"Import failed, Invaild file:{input_file}")
            return False, noesis_output
        
        # 双重splitext用于处理RE Engine的特殊文件格式
        # 例如：character.mesh.2102020001 -> file_base="character", this_ext=".2102020001" 
        file_base = os.path.splitext(os.path.splitext(os.path.basename(input_file))[0])[0]
        file_dir = os.path.dirname(input_file)
        
        # 设置导出目录
        fbx_path = os.path.join(file_dir, file_base + ".fbx")
        log_path = os.path.join(file_dir, file_base + "_noesis.txt")
            
        # 设定动画导出帧率 TODO:根据不同的游戏设定不同的帧率
        framerate = 60
        cmds.currentUnit(time='ntscf')  # 60fps

        # 保留fmt_RE_MESH的交互式选择窗口，方便选择关联MESH或[ALL]动画。
        cmd = build_noesis_command(
            noesis_path=self.noesis_path,
            input_file=input_file,
            fbx_path=fbx_path,
            log_path=log_path,
            optimize=cmds.checkBox(self.chk_fbx_optimize, query=True, value=True),
            framerate=framerate,
        )
    
        print(f"Noesis Command:\n{cmd}\n")
    
        # 在隐藏的CP936控制台中启动Noesis，兼容Windows UTF-8 Beta设置。
        process = launch_noesis_command(cmd, os.path.dirname(self.noesis_path))
    
        # 等待选择完成
        process.wait()
    
        # 读取Log文件
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    noesis_output = f.read()
                print("Noesis Output:\n" + noesis_output)
                os.remove(log_path)
                
                # 检查Noesis是否有导出错误
                if "Traceback" in noesis_output or "Error" in noesis_output:
                    cmds.warning("Noesis reported errors - check script editor")
                    return False, noesis_output
            except Exception as e:
                print(f"Failed to read log file: {e}")
    
        # 等待文件解锁并导入
        self.wait_for_file_unlock(fbx_path)
    
        # fbx不存在，说明Noesis没有成功创建
        if not os.path.exists(fbx_path):
            cmds.warning(f"FBX file was not created by Noesis:{fbx_path}")
            return False, noesis_output
    
        # 导入fbx文件
        success = self.import_fbx(fbx_path)
        
        # 删除Noesis导出的FBX中间文件
        if cmds.checkBox(self.chk_delete_fbx, query=True, value=True):
            try:
                os.remove(fbx_path)
            except:
                pass
        
        if not success: # 若单个fbx导入失败，返回false
            cmds.warning(f"FBX import failed for: {fbx_path}")
            return False, noesis_output
        
        return True, noesis_output
        
    def import_fbx(self, fbx_path):
        """导入FBX文件"""
        try: 
            # 设置FBX导入选项
            mel.eval('FBXImportMode -v "merge"')
            mel.eval('FBXImportMergeAnimationLayers -v false')
            
            # 导入FBX
            cmds.file(fbx_path, i=True, type="FBX", ignoreVersion=True, mergeNamespacesOnClash=False, namespace=":")
            print(f"Successfully imported: {fbx_path}")
            return True
            
        except Exception as e:
            cmds.warning(f"Failed to import FBX: {e}")
            return False
        
    def post_process_imported_objects(self, orig_path, file_base, set_coords=None, already_imported=False):
        """后处理导入的对象"""
        obj_imported = cmds.ls(type='transform')
        print(f"obj_imported:{len(obj_imported)}")
        meshes = [obj for obj in obj_imported if self.is_mesh(obj)]

        # 处理.motlist.动画文件 - 删除dummymesh
        if ".motlist." in orig_path and meshes:
            for mesh in meshes:
                if "dummy" in mesh.lower():
                    cmds.delete(mesh)
                    meshes.remove(mesh)
                    print("Deleted dummy mesh")
            return
        
        # 处理.mesh.文件
        for mesh in meshes:
            # 随机 RGB 颜色
            r, g, b = [random.random() for _ in range(3)]
            # 随机线框颜色
            cmds.setAttr(mesh + ".overrideEnabled", 1)
            cmds.setAttr(mesh + ".overrideRGBColors", 1)
            cmds.setAttr(mesh + ".overrideColorRGB", r, g, b, type="double3")
            
            print("Set wireframe color on {}".format(mesh))
    # Import Functions Ends----------------------------------------------------------------------------

    # Animation Functions Begin------------------------------------------------------------------------
    def parse_animation_text(self, text):
        """解析动画文本数据"""
        try:
            self.animation_data = []
            problematic_animations = []  # 记录有问题的动画
            lines = text.strip().split('\n')
            
            # 匹配Noesis插件fmt_RE_MESH.py中输出的格式
            pattern = r'@\s*(\d+)\s*[\'"]([^\'\"]*)\s*\((\d+)\s*frames\).*ID:\s*(\d+)'
            
            # 匹配警告/错误信息的模式
            warning_patterns = [
                r'WARNING:\s*Keyframed anim\s*\([\'"]([^\'\"]*)[^)]*\)\s*is missing keyframed bones list',
                r'ERROR:\s*.*[\'"]([^\'\"]*)[\'"]',
                r'FAILED:\s*.*[\'"]([^\'\"]*)[\'"]',
                # 可以根据需要添加更多错误模式
            ]
            
            # 首先识别所有有问题的动画名称
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 检查是否是警告/错误信息
                for warning_pattern in warning_patterns:
                    warning_match = re.search(warning_pattern, line, re.IGNORECASE)
                    if warning_match:
                        problematic_anim_name = warning_match.group(1).strip()
                        problematic_animations.append(problematic_anim_name)
                        print(f"Detected problematic animation: '{problematic_anim_name}' - {line}")
                        break
            
            # 解析动画数据，同时剔除有问题的动画
            for line in lines:
                line = line.strip()
                if not line or not line.startswith('@'):
                    continue
                
                match = re.search(pattern, line)
                if match:
                    start_frame = int(match.group(1))
                    name = match.group(2).strip()
                    frame_count = int(match.group(3))
                    anim_id = int(match.group(4))
                    
                    # 检查这个动画是否在问题列表中
                    is_problematic = any(problematic_name in name or name in problematic_name 
                                   for problematic_name in problematic_animations)
                    
                    if is_problematic:
                        print(f"Skipping problematic animation: '{name}' (ID: {anim_id})")
                        continue
                    
                    self.animation_data.append({
                        'name': name,
                        'start_frame': start_frame,
                        'frame_count': frame_count,
                        'end_frame': start_frame + frame_count - 1,
                        'id': anim_id
                    })
                else:
                    print(f"Warning: Could not parse line: {line}")
            
            # 修正blend pose条目的帧数并重新计算起始帧
            if self.animation_data:
                self.detect_incorrect_frames()
                # 重新计算所有动画的起始帧（因为剔除了一些动画）
                self.recalculate_frame_ranges()
            
            if self.animation_data:
                # 清空并更新下拉列表
                menu_items = cmds.optionMenu(self.animation_combo, query=True, itemListLong=True)
                if menu_items:
                    cmds.deleteUI(menu_items)
                
                # 添加新的菜单项
                for anim in self.animation_data:
                    display_text = f"{anim['name']} (Frames: {anim['start_frame']}-{anim['end_frame']}, ID: {anim['id']})"
                    cmds.menuItem(label=display_text, parent=self.animation_combo)
                
                # 启用控件
                cmds.optionMenu(self.animation_combo, edit=True, enable=True)
                cmds.button(self.export_button, edit=True, enable=True)
                # cmds.button(self.set_timeline_button, edit=True, enable=True)
                
                # 更新状态信息
                status_msg = f"Successfully parsed {len(self.animation_data)} animations"
                if problematic_animations:
                    status_msg += f" (Skipped {len(problematic_animations)} problematic animations)"
                    
                self.update_status(status_msg)
                print(f"Parsed {len(self.animation_data)} animations successfully")
            else:
                cmds.warning("No valid animation data found in text!")
                self.update_status("No valid animation data found!")
        
        except Exception as e:
            error_msg = f"Failed to parse animation text: {str(e)}"
            cmds.error(error_msg)
            self.update_status("Parse failed - Check script editor for details")
    
    def detect_incorrect_frames(self):
        """检测并修正错误的帧数"""
        blend_pose_count = 0
        invalid_frame_count = 0
    
        for anim in self.animation_data:
            # 检查是否是blend pose条目（包含_blend*_*pose_模式）
            is_blend_pose = "_blend" in anim['name'].lower() and "_pose_" in anim['name'].lower()
            
            if is_blend_pose: # 修正blend pose条目的帧数，blend pose只输出了一帧，但却被错误标记为60帧
                # 修正blend pose的帧数为2帧
                original_frame_count = anim['frame_count']
                anim['frame_count'] = 1
                anim['original_frame_count'] = original_frame_count  # 保存原始帧数用于调试
                blend_pose_count += 1
                print(f"Corrected blend pose '{anim['name']}': {original_frame_count} frames -> 1 frame")
                
            if anim['frame_count'] < 1: # 修正帧数小于1的帧数为2帧
                original_frame_count = anim['frame_count']
                anim['frame_count'] = 1
                anim['original_frame_count'] = original_frame_count  # 保存原始帧数用于调试
                invalid_frame_count += 1
                print(f"Warning: Animation '{anim['name']}' had invalid frame count, {original_frame_count} frames -> 1 frame")
        
        if blend_pose_count > 0:
            print(f"Fixed {blend_pose_count} blend pose animations")  
            
        if invalid_frame_count > 0:
            print(f"Fixed {invalid_frame_count} animations with invalid frame counts")  
    
    def recalculate_frame_ranges(self):
        """重新计算所有动画的帧范围"""
        if not self.animation_data:
            return
        
        current_start_frame = 0
        
        for i, anim in enumerate(self.animation_data):
            if i == 0:
                # 第一个动画保持原始起始帧或从0开始
                new_start_frame = 0
            else:
                # 后续动画的起始帧基于前一个动画的结束帧+1
                new_start_frame = current_start_frame
            
            original_start = anim['start_frame']
            anim['start_frame'] = new_start_frame
            anim['end_frame'] = new_start_frame + anim['frame_count'] - 1
            
            # 更新下一个动画的起始帧
            current_start_frame = anim['end_frame'] + 1
            
            # 如果有变化，输出调试信息
            if new_start_frame != original_start:
                print(f"Recalculated '{anim['name']}': "
                    f"start {original_start}->{new_start_frame}, "
                    f"end {anim['end_frame']} (frames: {anim['frame_count']})")
        
        print(f"Recalculated frame ranges for {len(self.animation_data)} animations")        

    def fix_framerate(self, *args):
        """修复Noesis导出的动画速率被错误识别为30fps的情况，将动画修改帧速率为60fps"""
        try:
            # 检查是否有选中的对象
            selected_objects = cmds.ls(selection=True, long=True)
            if not selected_objects:
                cmds.warning("Please select an object first!")
                self.update_status("Error: No object selected for DD2 frame rate fix")
                return
            
            self.update_status("Applying DD2 frame rate fix...")
            
            # 步骤1: 设置帧速率为30fps
            cmds.currentUnit(time='ntsc')  # 30fps
            print("Step 1: Set frame rate to 30fps")
            
            # 步骤2: 选择当前选中物体的所有子级
            mel.eval('select -hierarchy;')
            print(f"Step 2: Selected All Hierarchy")
            
            # 步骤3: 将时间缩短一半
            try:
                # 对选中的所有对象执行时间缩放
                mel.eval('scaleKey -timeScale 0.5 -timePivot 0;')
                print("Step 3: Applied time scale 0.5 with pivot at frame 0")
                
            except Exception as e:
                print(f"Warning during scaleKey operation: {str(e)}")
                # 即使scaleKey失败也继续执行后续步骤
            
            # 步骤4: 设置帧速率为60fps
            cmds.currentUnit(time='ntscf')  # 60fps
            print("Step 4: Set frame rate to 60fps")
            
            # 完成
            self.update_status("DD2 frame rate fix completed successfully")
            
            # 显示完成对话框
            cmds.confirmDialog(
                title="DD2 Frame Rate Fix Complete",
                message="Successfully applied DD2 frame rate fix:\n"
                       "Fix animation speed issues caused by incorrect frame rate export settings in Noesis",
                button=["OK"]
            )
            
            print("DD2 frame rate fix completed successfully!")
            
        except Exception as e:
            error_msg = f"DD2 frame rate fix failed: {str(e)}"
            cmds.error(error_msg)
            self.update_status("DD2 frame rate fix failed - Check script editor")
            
            cmds.confirmDialog(
                title="DD2 Frame Rate Fix Error",
                message=f"Failed to apply DD2 frame rate fix:\n{str(e)}",
                button=["OK"],
                icon="critical"
            )
    
    def export_animation(self, *args):
        """导出动画"""
        if not self.animation_data:
            cmds.warning("No animation data to export!")
            return
        
        # 分别导出每个动画
        self.export_animations_separately()
    
    def export_animations_separately(self):
        """分别导出每个动画"""
        # 选择导出文件夹
        export_path = cmds.fileDialog2(
            caption="Select Export Directory",
            fileMode=3,  # 文件夹选择模式
            okCaption="Select"
        )
        
        if not export_path:
            self.update_status("Export cancelled by user")
            return
        
        export_path = export_path[0]
        
        try:
            export_selected = cmds.radioButton(self.export_selected_radio, query=True, select=True)
            
            if export_selected:
                # 导出选中的动画
                selected_index = cmds.optionMenu(self.animation_combo, query=True, select=True) - 1
                if 0 <= selected_index < len(self.animation_data):
                    anim = self.animation_data[selected_index]
                    self.update_status(f"Exporting: {anim['name']}...")
                    self.export_single_animation_as_take(anim, export_path)
                    self.update_status(f"Exported: {anim['name']}")
                    cmds.confirmDialog(
                        title="Export Complete",
                        message=f"Successfully exported: {anim['name']}\nTo: {export_path}",
                        button=["OK"]
                    )
                else:
                    cmds.warning("Invalid animation selection!")
            else:
                # 导出所有动画
                exported_count = 0
                failed_exports = []
                
                for i, anim in enumerate(self.animation_data):
                    try:
                        self.update_status(f"Exporting... {i+1}/{len(self.animation_data)}: {anim['name']}")
                        self.export_single_animation_as_take(anim, export_path)
                        exported_count += 1
                    except Exception as e:
                        failed_exports.append(f"{anim['name']}: {str(e)}")
                        print(f"Failed to export {anim['name']}: {str(e)}")
                
                if failed_exports:
                    self.update_status(f"Export complete: {exported_count}/{len(self.animation_data)} successful")
                    error_message = f"Exported {exported_count}/{len(self.animation_data)} animations.\n\nFailed exports:\n" + "\n".join(failed_exports[:5])
                    if len(failed_exports) > 5:
                        error_message += f"\n... and {len(failed_exports)-5} more"
                    cmds.confirmDialog(
                        title="Export Complete with Errors",
                        message=error_message,
                        button=["OK"],
                        icon="warning"
                    )
                else:
                    self.update_status(f"Export complete: {exported_count} animations")
                    cmds.confirmDialog(
                        title="Export Complete",
                        message=f"Successfully exported all {exported_count} animations to:\n{export_path}",
                        button=["OK"]
                    )
        
        except Exception as e:
            error_msg = f"Export failed: {str(e)}"
            cmds.error(error_msg)
            self.update_status("Export failed - Check script editor for details")
            cmds.confirmDialog(
                title="Export Error",
                message=f"Export failed:\n{str(e)}",
                button=["OK"],
                icon="critical"
            )
    
    def export_single_animation_as_take(self, anim_data, export_path):
        """导出单个动画片段作为独立的Take"""
        try:
            # 设置FBX导出参数
            self.setup_fbx_export_settings_for_clips()
            
            # 清除现有的动画分割设置
            mel.eval('FBXExportSplitAnimationIntoTakes -clear')
            
            # 创建单个Take
            take_name = f"{anim_data['name']}_ID{anim_data['id']}"
            start_frame = anim_data['start_frame']
            end_frame = anim_data['end_frame']
            
            # 设置烘焙时间范围
            mel.eval(f'FBXExportBakeComplexStart -v {start_frame}')
            mel.eval(f'FBXExportBakeComplexEnd -v {end_frame}')
            
            # 添加Take scripts/others/gameFbxExporter.mel
            mel.eval(f'FBXExportSplitAnimationIntoTakes -v "{take_name}" {start_frame} {end_frame}')
            
            # 检查选择
            selected_objects = cmds.ls(selection=True, long=True)
            if not selected_objects:
                result = cmds.confirmDialog(
                    title="No Selection",
                    message="No objects selected. Export all visible objects?",
                    button=["Yes", "No"],
                    defaultButton="Yes",
                    cancelButton="No",
                    dismissString="No"
                )
                
                if result == "Yes":
                    all_transforms = cmds.ls(type='transform', long=True)
                    visible_objects = [obj for obj in all_transforms 
                                     if cmds.getAttr(f"{obj}.visibility") 
                                     and not cmds.getAttr(f"{obj}.intermediateObject", default=False)]
                    if visible_objects:
                        cmds.select(visible_objects)
                    else:
                        raise Exception("No visible objects found to export!")
                else:
                    raise Exception("Export cancelled - no objects to export!")
            
            # 生成文件名
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', anim_data['name'])
            filename = f"{safe_name}_ID{anim_data['id']}.fbx"
            filepath = os.path.join(export_path, filename).replace('\\', '/')
            
            # 执行导出
            mel.eval(f'FBXExport -f "{filepath}" -s')
            
            # 清理
            mel.eval('FBXExportSplitAnimationIntoTakes -clear')
            
            print(f"Exported animation: {anim_data['name']} (Frames: {start_frame}-{end_frame}, ID: {anim_data['id']}) to {filepath}")
            
        except Exception as e:
            # 确保清理
            mel.eval('FBXExportSplitAnimationIntoTakes -clear')
            raise e
    
    def setup_fbx_export_settings_for_clips(self):
        """设置FBX导出选项用于动画片段"""
        try:
            # 重置FBX导出设置
            mel.eval('FBXResetExport')
            
            # 设置动画导出选项
            mel.eval('FBXExportBakeComplexAnimation -v true')
            mel.eval('FBXExportBakeComplexStep -v 1')
            
            # 导出设置
            mel.eval('FBXExportAnimationOnly -v false')  # 导出几何体和动画
            mel.eval('FBXExportBakeComplexAnimation -v true')
            
            # 启用删除原始Take（这样只保留我们分割的Takes）
            mel.eval('FBXExportDeleteOriginalTakeOnSplitAnimation -v true')
            
            # 其他常用设置
            mel.eval('FBXExportSmoothingGroups -v true')
            mel.eval('FBXExportHardEdges -v false')
            mel.eval('FBXExportTangents -v false')
            mel.eval('FBXExportSmoothMesh -v true')
            mel.eval('FBXExportInstances -v false')
            mel.eval('FBXExportReferencedAssetsContent -v true')
            
            # 单位设置
            mel.eval('FBXExportConvertUnitString "cm"')
            
        except Exception as e:
            print(f"Warning: Some FBX export settings may not be available: {str(e)}")
    # Animation Functions End------------------------------------------------------------------------

    # UI Callback Functions Begin------------------------------------------------------
    def show_input_dialog(self, *args):
        """显示手动输入对话框"""
        result = cmds.promptDialog(
            title='Paste Noesis Animation List',
            message='Please paste your Noesis animation list here:\n(Example: @ 0 \'animation_name (165 frames) ID: 0\')',
            button=['OK', 'Cancel'],
            defaultButton='OK',
            cancelButton='Cancel',
            dismissString='Cancel',
            scrollableField=True,
            text=""
        )
        
        if result == 'OK':
            text = cmds.promptDialog(query=True, text=True)
            if text.strip():
                self.parse_animation_text(text)
            else:
                self.update_status("No text provided")
                cmds.warning("No animation data provided!")
    
    def on_animation_selected(self, *args):
        """动画选择改变时的回调"""
        selected_index = cmds.optionMenu(self.animation_combo, query=True, select=True) - 1
        if 0 <= selected_index < len(self.animation_data):
            anim = self.animation_data[selected_index]
            self.update_status(f"Selected: {anim['name']} ({anim['frame_count']} frames, ID: {anim['id']})")
            
        self.set_timeline_range()
    
    def set_timeline_range(self, *args):
        """设置timeline范围为选中动画的范围"""
        if not self.animation_data:
            cmds.warning("No animation data available!")
            return
        
        selected_index = cmds.optionMenu(self.animation_combo, query=True, select=True) - 1
        if 0 <= selected_index < len(self.animation_data):
            anim = self.animation_data[selected_index]
            
            try:
                # 设置动画范围
                cmds.playbackOptions(
                    minTime=anim['start_frame'],
                    maxTime=anim['end_frame'],
                    animationStartTime=anim['start_frame'],
                    animationEndTime=anim['end_frame']
                )
                
                # 将当前时间设置为动画开始帧
                cmds.currentTime(anim['start_frame'])
                
                # 更新状态
                self.update_status(f"Timeline set to {anim['name']}: frames {anim['start_frame']}-{anim['end_frame']}")
                
                print(f"Timeline range set to: {anim['start_frame']}-{anim['end_frame']} for animation '{anim['name']}'")
                
            except Exception as e:
                error_msg = f"Failed to set timeline range: {str(e)}"
                cmds.error(error_msg)
                self.update_status("Failed to set timeline range")
        else:
            cmds.warning("Invalid animation selection!")
    
    def on_export_option_changed(self, *args):
        """导出选项改变时的处理"""
        selected_radio = cmds.radioCollection(self.radio_collection, query=True, select=True)
        
        # 使用字符串比较来判断选中的单选按钮
        if cmds.radioButton(self.export_selected_radio, query=True, select=True):
            # Export Selected Animation 被选中
            if self.animation_data:  # 只有在有动画数据时才启用下拉列表
                cmds.optionMenu(self.animation_combo, edit=True, enable=True)
                #cmds.button(self.set_timeline_button, edit=True, enable=True)
                selected_index = cmds.optionMenu(self.animation_combo, query=True, select=True) - 1
                if 0 <= selected_index < len(self.animation_data):
                    anim = self.animation_data[selected_index]
                    self.update_status(f"Export mode: Selected animation - {anim['name']}")
                else:
                    self.update_status("Export mode: Selected animation")
            else:
                cmds.optionMenu(self.animation_combo, edit=True, enable=False)
                #cmds.button(self.set_timeline_button, edit=True, enable=False)
                self.update_status("Export mode: Selected animation (No animations loaded)")
        else:
            # Export All Animations 被选中
            cmds.optionMenu(self.animation_combo, edit=True, enable=False)
            #cmds.button(self.set_timeline_button, edit=True, enable=False)
            if self.animation_data:
                self.update_status(f"Export mode: All animations ({len(self.animation_data)} total)")
            else:
                self.update_status("Export mode: All animations (No animations loaded)")
                
    def on_game_option_changed(self, selected_game):
        """comboBox 选项变更时的回调"""
        if selected_game in self.games_list:
            index = self.games_list.index(selected_game)
            self.change_current_game(index)        
    
    def update_status(self, message):
        """更新状态显示"""
        cmds.text(self.status_text, edit=True, label=message)
        cmds.refresh()  # 强制刷新界面
    
    def close_window(self):
        """关闭窗口"""
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
    # UI Callback Functions End-------------------------------------------------------            
     
    # Support Functions Begin----------------------------------------------------------------
    def load_settings(self):
        """Load saved settings"""
        settings_file = os.path.join(os.path.expanduser("~"), ".maya_anim_exporter_settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                    self.noesis_path = settings.get("noesis_path", "")
                    self.current_extension = settings.get("current_extension", "")
            except:
                pass
    
    def save_settings(self):
        """Save settings"""
        settings_file = os.path.join(os.path.expanduser("~"), ".maya_anim_exporter_settings.json")
        settings = {
            "noesis_path": self.noesis_path,
            "current_extension": self.current_extension
        }
        try:
            with open(settings_file, 'w') as f:
                json.dump(settings, f)
        except:
            pass        
         
    def wait_for_file_unlock(self, filepath, timeout=10):
        """等待文件解锁"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if os.path.exists(filepath):
                try:
                    # 尝试打开文件
                    with open(filepath, 'rb') as f:
                        # 文件可写
                        return True
                except:
                    # 文件被占用
                    time.sleep(0.1)
            else:
                time.sleep(0.1)
        return False
    
    def get_extension_index(self, extension):
        """根据扩展名获取游戏索引"""
        for i, game in enumerate(self.games_list):
            if self.game_extensions.get(game, "") == extension:
                return i
        return -1
    
    def get_current_game(self):
        """根据扩展名获取游戏名称"""
        if self.current_extension and self.games_list:
            full_ext = f".mesh{self.current_extension}"
            game_index = self.get_extension_index(full_ext)
            return self.games_list[game_index]
    
    def change_current_game(self, list_index):
        """根据序号切换当前游戏设置"""
        try:
            if 0 <= list_index < len(self.games_list):
                current_item = self.games_list[list_index]
                
                # 更新当前扩展名
                current_ext = self.game_extensions.get(current_item, "")
                #if self.lbl_current_ext:
                #    cmds.text(self.lbl_current_ext, edit=True, label=current_ext)
                
                # 更新PAK位置
                #self.current_pak_location = self.pak_locations.get(current_item, "")
                #if self.edt_scn_path:
                #    cmds.textField(self.edt_scn_path, edit=True, text=self.current_pak_location)
                
                # 更新列表选择
                #if self.list_game_selection:
                #    cmds.textScrollList(self.list_game_selection, edit=True, 
                #                       selectIndexedItem=list_index + 1)
                
                # 提取纯扩展名（去掉.mesh前缀）
                self.current_extension = current_ext.replace(".mesh", "") if current_ext.startswith(".mesh") else current_ext
                
                cmds.text(self.text_current_extension, edit = True, label = f".mesh{self.current_extension}",)
                
                self.save_settings()
                
                print(f"Switched to {current_item}: {current_ext}")  
        except Exception as e:
            print(f"Error changing game: {e}")
            
    def get_skin_clusters(self, mesh):
        """获取网格的皮肤修改器"""
        history = cmds.listHistory(mesh)
        return [node for node in history if cmds.nodeType(node) == 'skinCluster']

    def is_mesh(self, obj):
        """检查对象是否为网格"""
        if cmds.nodeType(obj) == 'mesh':
            return True
        shapes = cmds.listRelatives(obj, shapes=True, type='mesh')
        return shapes is not None and len(shapes) > 0

    def is_bone(self, obj):
        """检查对象是否为骨骼"""
        return cmds.nodeType(obj) == 'joint'
    # Support Functions End---------------------------------------------------------------- 

def show_animation_exporter():
    """显示动画导出工具"""
    exporter = AnimationExporterUI()
    return exporter


# 运行脚本
if __name__ == "__main__":
    show_animation_exporter()
