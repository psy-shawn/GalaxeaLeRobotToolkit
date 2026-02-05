import cv2
import numpy as np
from pyorbbecsdk import *
import time
import os
import csv
from datetime import datetime
import argparse
import json
import shutil  # 用于删除文件夹

# 全局配置
SAVE_ROOT = "./recordings"
# 视频编码配置
VIDEO_CODEC = 'mp4v'  # 可选: 'mp4v', 'avc1', 'XVID'
VIDEO_EXT = '.mp4'
# 可配置帧率
VIDEO_FPS = 15.0

# 同步配置文件路径
CONFIG_FILE_PATH = "/Users/psy/workspace/GalaxeaLeRobotToolkit/utils/multi_device_sync_config.json"


def sync_mode_from_str(sync_mode_str):
    """转换同步模式字符串为枚举值"""
    sync_mode_str = sync_mode_str.upper()
    if sync_mode_str == "FREE_RUN":
        return OBMultiDeviceSyncMode.FREE_RUN
    elif sync_mode_str == "STANDALONE":
        return OBMultiDeviceSyncMode.STANDALONE
    elif sync_mode_str == "PRIMARY":
        return OBMultiDeviceSyncMode.PRIMARY
    elif sync_mode_str == "SECONDARY":
        return OBMultiDeviceSyncMode.SECONDARY
    elif sync_mode_str == "SECONDARY_SYNCED":
        return OBMultiDeviceSyncMode.SECONDARY_SYNCED
    elif sync_mode_str == "SOFTWARE_TRIGGERING":
        return OBMultiDeviceSyncMode.SOFTWARE_TRIGGERING
    elif sync_mode_str == "HARDWARE_TRIGGERING":
        return OBMultiDeviceSyncMode.HARDWARE_TRIGGERING
    else:
        return OBMultiDeviceSyncMode.FREE_RUN


def setup_pipeline(device, serial, sync_config_dict=None):
    """为指定设备创建并配置Pipeline"""
    pipeline = Pipeline(device)
    config = Config()

    # 配置同步模式
    if sync_config_dict:
        try:
            sync_config = device.get_multi_device_sync_config()
            sync_config.mode = sync_mode_from_str(sync_config_dict.get("mode", "FREE_RUN"))
            sync_config.color_delay_us = sync_config_dict.get("color_delay_us", 0)
            sync_config.depth_delay_us = sync_config_dict.get("depth_delay_us", 0)
            sync_config.trigger_out_enable = sync_config_dict.get("trigger_out_enable", False)
            sync_config.trigger_out_delay_us = sync_config_dict.get("trigger_out_delay_us", 0)
            sync_config.frames_per_trigger = sync_config_dict.get("frames_per_trigger", 1)

            device.set_multi_device_sync_config()
            print(f"  [同步] 模式: {sync_config_dict.get('mode', 'FREE_RUN')}")
        except Exception as e:
            print(f"  [同步] 配置失败: {e}")

    try:
        # 启用深度流
        depth_profile_list = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
        if depth_profile_list is not None:
            depth_profile = depth_profile_list.get_video_stream_profile(640, 400, OBFormat.Y16, int(VIDEO_FPS))
            if depth_profile:
                config.enable_stream(depth_profile)
                print(f"  [深度] 640x400 Y16 @{int(VIDEO_FPS)}fps")
            else:
                default_depth_profile = depth_profile_list.get_default_video_stream_profile()
                config.enable_stream(default_depth_profile)
                print(f"  [深度] 默认配置")
    except Exception as e:
        print(f"  深度流配置异常: {e}")
    
    try:
        # 启用彩色流
        color_profile_list = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
        if color_profile_list is not None:
            color_profile = color_profile_list.get_video_stream_profile(640, 480, OBFormat.RGB, int(VIDEO_FPS))
            if color_profile:
                config.enable_stream(color_profile)
                print(f"  [彩色] 640x480 RGB @{int(VIDEO_FPS)}fps")
            else:
                default_color_profile = color_profile_list.get_default_video_stream_profile()
                config.enable_stream(default_color_profile)
                print(f"  [彩色] 默认配置")
    except Exception as e:
        print(f"  彩色流配置异常: {e}")
    
    pipeline.start(config)
    return pipeline

def main():
    parser = argparse.ArgumentParser(description="Record from Orbbec cameras")
    parser.add_argument('--no-display', action='store_true', help='run in headless mode without GUI display')
    args = parser.parse_args()
    no_display = args.no_display

    # 初始化
    ctx = Context()
    device_list = ctx.query_devices()
    
    if device_list.get_count() == 0:
        print("❌ 未检测到奥比中光设备")
        return
    
    print(f"✅ 检测到 {device_list.get_count()} 台相机")
    print(f"📹 视频编码: {VIDEO_CODEC} ({VIDEO_EXT})")

    # 加载同步配置
    sync_configs = {}
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'r') as f:
                config_data = json.load(f)
                for device in config_data.get("devices", []):
                    serial = device.get("serial_number", "")
                    if serial:
                        sync_configs[serial] = device.get("config", {})
            print("📄 已加载同步配置文件")
        except Exception as e:
            print(f"⚠️  加载同步配置文件失败: {e}")
    else:
        print("ℹ️  未找到同步配置文件，使用FREE_RUN模式")

    # 创建根目录
    if not os.path.exists(SAVE_ROOT):
        os.makedirs(SAVE_ROOT)
    
    recorders = []
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 本次会话的总目录
    session_dir = os.path.join(SAVE_ROOT, timestamp_str)
    
    # 标记是否保存数据 (默认为True，Ctrl+X时改为False)
    save_data_flag = True

    for i in range(device_list.get_count()):
        try:
            # 1. 先尝试获取设备对象
            # 如果这行报错，说明是系统内置相机或权限被占用，直接跳过
            device = device_list.get_device_by_index(i)
            
            # 2. 获取设备信息进行二次确认
            info = device.get_device_info()
            name = info.get_name()
            serial = info.get_serial_number()
            
            # 3. 过滤非奥比中光设备（可选，但建议保留）
            if "FaceTime" in name or "Apple" in name:
                print(f"⏭️  跳过内置设备: {name}")
                continue
                
        except Exception as e:
            # 这里会捕获到 uvc_open failed: -3
            print(f"⚠️  跳过无法访问的设备 (索引 {i}): {e}")
            continue

        print(f"\n🎯 正在初始化相机 {i} (SN: {serial})...")

    # # 为每台相机初始化录制器
    # for i in range(device_list.get_count()):
    #     device = device_list.get_device_by_index(i)
    #     serial = device.get_device_info().get_serial_number()
        
    #     print(f"\n🎯 正在初始化相机 {i} (SN: {serial})...")
        
        # 相机独立目录
        cam_dir = os.path.join(session_dir, f"cam_{serial}")
        os.makedirs(cam_dir, exist_ok=True)
        # 注意：这里不再需要 depth_raw 文件夹，因为改为视频录制了
        
        # 配置并启动pipeline
        device_sync_config = sync_configs.get(serial, {})
        pipeline = setup_pipeline(device, serial, device_sync_config)
        
        # --- RGB 视频写入器 ---
        rgb_video_path = os.path.join(cam_dir, f"rgb_video{VIDEO_EXT}")
        fourcc = cv2.VideoWriter_fourcc(*VIDEO_CODEC)
        rgb_writer = cv2.VideoWriter(rgb_video_path, fourcc, float(VIDEO_FPS), (640, 480))
        
        if not rgb_writer.isOpened():
            print(f"⚠️  警告: 无法创建MP4视频文件，尝试使用XVID编码...")
            rgb_video_path = os.path.join(cam_dir, "rgb_video.avi")
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            rgb_writer = cv2.VideoWriter(rgb_video_path, fourcc, float(VIDEO_FPS), (640, 480))

        # --- Depth 视频写入器 (新增) ---
        # 深度图分辨率为 640x400 (见 setup_pipeline)
        depth_video_path = os.path.join(cam_dir, f"depth_video{VIDEO_EXT}")
        # 使用相同的编码器
        depth_writer = cv2.VideoWriter(depth_video_path, fourcc, float(VIDEO_FPS), (640, 400))
        
        # 时间戳CSV文件
        csv_path = os.path.join(cam_dir, "timestamps.csv")
        csv_file = open(csv_path, 'w', newline='')
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["Frame_Index", "System_Timestamp_ns", "Device_Timestamp_us",
                           "RGB_Width", "RGB_Height", "Depth_Width", "Depth_Height", "Rel_Time_ms"])
        
        # 深度帧信息CSV (稍微调整，因为没有单个文件名了)
        depth_info_path = os.path.join(cam_dir, "depth_stats.csv")
        depth_info_file = open(depth_info_path, 'w', newline='')
        depth_info_writer = csv.writer(depth_info_file)
        depth_info_writer.writerow(["Frame_Index", "Min_Distance", "Max_Distance", 
                                  "Mean_Distance", "Valid_Pixels"])
        
        recorders.append({
            'pipeline': pipeline,
            'serial': serial,
            'index': i,
            'rgb_writer': rgb_writer,
            'depth_writer': depth_writer,
            'csv_file': csv_file,
            'csv_writer': csv_writer,
            'depth_info_file': depth_info_file,
            'depth_info_writer': depth_info_writer,
            'cam_dir': cam_dir,
            'frame_idx': 0,
            'video_path': rgb_video_path,
            'depth_video_path': depth_video_path
        })
        
        print(f"  录制目录: {cam_dir}")
    
    print(f"\n⏺️  开始同步录制 {len(recorders)} 台相机")
    if no_display:
        print("   headless mode. Use Ctrl-C to stop.")
    else:
        print("   按 'q' 或 'Ctrl+Y' -> 保存并退出")
        print("   按 'Ctrl+X'        -> ❌ 丢弃数据并退出")
        print("   按 'p'             -> 暂停/继续")

    # 窗口设置
    if not no_display:
        for rec in recorders:
            window_name = f"Camera {rec['index']} - {rec['serial'][-6:]}"
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, 640, 240)
            cv2.moveWindow(window_name, 5, 5 + (rec['index'] * 520))

    try:
        start_time = time.time()
        start_time_ns = time.time_ns()
        last_status_time = start_time
        recording_paused = False
        
        while True:
            # --- 按键控制逻辑 ---
            if no_display:
                key = None
            else:
                key = cv2.waitKey(1) & 0xFF
            
            # 处理特殊按键
            if key == ord('q') or key == 25: # 25 is Ctrl+Y
                print("\n💾 用户请求停止并保存...")
                save_data_flag = True
                break
            elif key == 24: # 24 is Ctrl+X
                print("\n🗑️ 用户请求停止并 [丢弃数据]...")
                save_data_flag = False
                break
            elif key == ord('p'):
                recording_paused = not recording_paused
                print(f"\n⏸️  录制{'已暂停' if recording_paused else '已继续'}")
                cv2.waitKey(300)

            # 暂停逻辑
            if recording_paused:
                if not no_display:
                    for rec in recorders:
                        preview = np.zeros((480, 640*2, 3), dtype=np.uint8)
                        cv2.putText(preview, "PAUSED", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                        cv2.imshow(f"Camera {rec['index']} - {rec['serial'][-6:]}", preview)
                else:
                    time.sleep(0.1)
                continue
            
            # 帧处理
            frames_processed = 0
            for rec in recorders:
                pipeline = rec['pipeline']
                frames = pipeline.wait_for_frames(50)
                if frames is None: continue
                
                color_frame = frames.get_color_frame()
                depth_frame = frames.get_depth_frame()
                
                if color_frame is None or depth_frame is None: continue
                
                frame_idx = rec['frame_idx']
                
                # --- RGB 处理 ---
                color_data = np.frombuffer(color_frame.get_data(), dtype=np.uint8)
                color_data = color_data.reshape((color_frame.get_height(), color_frame.get_width(), 3))
                bgr_image = cv2.cvtColor(color_data, cv2.COLOR_RGB2BGR)
                rec['rgb_writer'].write(bgr_image)
                
                # --- Depth 处理 (转为视频) ---
                depth_data = np.frombuffer(depth_frame.get_data(), dtype=np.uint16)
                depth_data = depth_data.reshape((depth_frame.get_height(), depth_frame.get_width()))
                
                # 1. 生成可视化彩色深度图用于保存为MP4 (因为MP4不支持16位灰度)
                # 归一化: 0-255. 为了更好的可视化效果，可以截断过远的距离
                # 这里简单地做 MINMAX 归一化
                depth_norm = cv2.normalize(depth_data, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                depth_colormap = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
                
                # 写入深度视频文件
                rec['depth_writer'].write(depth_colormap)
                
                # --- 记录数据 ---
                sys_ts_ns = time.time_ns()
                dev_ts_us = color_frame.get_timestamp()
                rel_time_ms = (sys_ts_ns - start_time_ns) / 1e6

                rec['csv_writer'].writerow([
                    frame_idx, sys_ts_ns, dev_ts_us,
                    color_frame.get_width(), color_frame.get_height(),
                    depth_frame.get_width(), depth_frame.get_height(),
                    rel_time_ms
                ])
                
                # 统计信息
                valid_depth = depth_data[depth_data > 0]
                if len(valid_depth) > 0:
                    min_dist, max_dist = np.min(valid_depth), np.max(valid_depth)
                    mean_dist = np.mean(valid_depth)
                    valid_pixels = len(valid_depth)
                else:
                    min_dist = max_dist = mean_dist = valid_pixels = 0
                
                rec['depth_info_writer'].writerow([frame_idx, min_dist, max_dist, mean_dist, valid_pixels])
                
                # --- 预览显示 ---
                # 为了预览一致，调整深度图大小匹配RGB
                if depth_colormap.shape[:2] != bgr_image.shape[:2]:
                    depth_display_resized = cv2.resize(depth_colormap, (bgr_image.shape[1], bgr_image.shape[0]))
                else:
                    depth_display_resized = depth_colormap
                    
                preview = np.hstack((bgr_image, depth_display_resized))
                
                info_text = f"Cam {rec['index']} | Fr: {frame_idx} | {rel_time_ms:.1f}ms"
                cv2.putText(preview, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                if not no_display:
                    cv2.imshow(f"Camera {rec['index']} - {rec['serial'][-6:]}", preview)
                
                rec['frame_idx'] += 1
                frames_processed += 1
            
            # 定时状态输出
            current_time = time.time()
            if current_time - last_status_time > 5 and frames_processed > 0:
                elapsed = current_time - start_time
                print(f"\r📊 录制中: {elapsed:.1f}s | Ctrl+Y 保存退出 | Ctrl+X 丢弃退出", end="")
                last_status_time = current_time
    
    except KeyboardInterrupt:
        print("\n\n⚠️  检测到中断信号，默认保存数据")
    except Exception as e:
        print(f"\n\n❌ 录制出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # --- 清理资源 ---
        print("\n正在释放资源...")
        if not no_display:
            cv2.destroyAllWindows()
            
        for rec in recorders:
            try:
                rec['pipeline'].stop()
                rec['rgb_writer'].release()
                rec['depth_writer'].release() # 释放深度视频写入器
                rec['csv_file'].close()
                rec['depth_info_file'].close()
            except Exception as e:
                print(f"清理相机 {rec['index']} 时出错: {e}")

        # --- 保存 vs 丢弃 逻辑 ---
        if save_data_flag:
            print("\n✅ 数据已保存。")
            for rec in recorders:
                print(f"  [Cam {rec['index']}] 帧数: {rec['frame_idx']}")
                print(f"    RGB视频:   {rec['video_path']}")
                print(f"    深度视频:  {rec['depth_video_path']}")
            print(f"  数据根目录: {session_dir}")
        else:
            print("\n🗑️  正在执行删除操作...")
            try:
                if os.path.exists(session_dir):
                    shutil.rmtree(session_dir)
                    print(f"✅ 已成功删除本次会话目录: {session_dir}")
                else:
                    print("⚠️  目录不存在，无法删除。")
            except Exception as e:
                print(f"❌ 删除目录失败: {e}")

if __name__ == "__main__":
    main()