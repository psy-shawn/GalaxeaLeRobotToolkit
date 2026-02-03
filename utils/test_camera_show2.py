import cv2
import numpy as np
from pyorbbecsdk import *
import time
import threading
from queue import Queue
import os
from datetime import datetime
VIDEO_FPS = 15.0
def setup_camera_pipeline(device, camera_index):
    """为单台相机配置并启动Pipeline"""
    device_info = device.get_device_info()
    serial = device_info.get_serial_number()
    
    print(f"正在配置相机 {camera_index}: 序列号 {serial}")
    
    # 创建Pipeline
    pipeline = Pipeline(device)
    config = Config()
    
    success = True
    error_msgs = []
    
    try:
        # 配置Depth流
        depth_profile_list = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
        if depth_profile_list is not None:
            depth_profile = depth_profile_list.get_video_stream_profile(640, 400, OBFormat.Y16, int(VIDEO_FPS))
            if depth_profile:
                config.enable_stream(depth_profile)
                print(f"  相机{camera_index}: 深度流 640x400 Y16 @{int(VIDEO_FPS)}fps")
            else:
                default_depth_profile = depth_profile_list.get_default_video_stream_profile()
                config.enable_stream(default_depth_profile)
                print(f"  相机{camera_index}: 使用默认深度流配置")
        else:
            error_msgs.append(f"相机{camera_index}: 不支持深度流")
            success = False
    except Exception as e:
        error_msgs.append(f"相机{camera_index}: 深度流配置异常 - {str(e)[:50]}")
        success = False
    
    try:
        # 配置Color流
        color_profile_list = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
        if color_profile_list is not None:
            color_profile = color_profile_list.get_video_stream_profile(640, 480, OBFormat.RGB, int(VIDEO_FPS))
            if color_profile:
                config.enable_stream(color_profile)
                print(f"  相机{camera_index}: 彩色流 640x480 RGB @{int(VIDEO_FPS)}fps")
            else:
                default_color_profile = color_profile_list.get_default_video_stream_profile()
                config.enable_stream(default_color_profile)
                print(f"  相机{camera_index}: 使用默认彩色流配置")
        else:
            error_msgs.append(f"相机{camera_index}: 不支持彩色流")
            success = False
    except Exception as e:
        error_msgs.append(f"相机{camera_index}: 彩色流配置异常 - {str(e)[:50]}")
        success = False
    
    # 启动pipeline
    if success:
        try:
            pipeline.start(config)
            print(f"✅ 相机 {camera_index} 启动成功")
            return {
                'pipeline': pipeline,
                'serial': serial,
                'index': camera_index,
                'errors': []
            }
        except Exception as e:
            error_msgs.append(f"相机{camera_index}: 启动失败 - {str(e)[:50]}")
    
    # 如果有错误，返回错误信息
    return {
        'pipeline': None,
        'serial': serial,
        'index': camera_index,
        'errors': error_msgs
    }

def camera_capture_worker(pipeline_info, frame_queue, stop_event):
    """相机捕获工作线程"""
    pipeline = pipeline_info['pipeline']
    camera_index = pipeline_info['index']
    serial = pipeline_info['serial']
    
    frame_count = 0
    last_log_time = time.time()
    consecutive_timeouts = 0  # 添加连续超时计数
    
    while not stop_event.is_set():
        try:
            # 等待同步帧 - 减少超时时间以便更快发现问题
            frames = pipeline.wait_for_frames(500)  # 改为500ms超时
            if frames is None:
                consecutive_timeouts += 1
                # 每5次输出一次调试信息
                if consecutive_timeouts % 5 == 0:
                    print(f"⚠️ 相机{camera_index} (SN:{serial[-6:]}) 等待帧超时 {consecutive_timeouts}次")
                continue
            
            # 重置超时计数
            consecutive_timeouts = 0
            
            color_frame = frames.get_color_frame()
            depth_frame = frames.get_depth_frame()
            
            if color_frame is None:
                frame_count_debug = getattr(camera_capture_worker, 'debug_color', 0) + 1
                camera_capture_worker.debug_color = frame_count_debug
                if frame_count_debug % 50 == 0:
                    print(f"⚠️ 相机{camera_index}color_frame为None (debug#{frame_count_debug})")
                continue
            
            if depth_frame is None:
                frame_count_debug = getattr(camera_capture_worker, 'debug_depth', 0) + 1
                camera_capture_worker.debug_depth = frame_count_debug
                if frame_count_debug % 50 == 0:
                    print(f"⚠️ 相机{camera_index}depth_frame为None (debug#{frame_count_debug})")
                continue
            
            # 处理彩色帧
            color_data = np.frombuffer(color_frame.get_data(), dtype=np.uint8)
            color_width = color_frame.get_width()
            color_height = color_frame.get_height()
            
            if color_frame.get_format() == OBFormat.RGB:
                color_data = color_data.reshape((color_height, color_width, 3))
                color_image = cv2.cvtColor(color_data, cv2.COLOR_RGB2BGR)
            else:
                color_data = color_data.reshape((color_height, color_width, -1))
                color_image = color_data
            
            # 处理深度帧
            depth_data = np.frombuffer(depth_frame.get_data(), dtype=np.uint16)
            depth_width = depth_frame.get_width()
            depth_height = depth_frame.get_height()
            
            if len(depth_data) > 0:
                depth_data = depth_data.reshape((depth_height, depth_width))
                depth_normalized = cv2.normalize(depth_data, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                depth_image = cv2.applyColorMap(depth_normalized, cv2.COLORMAP_JET)
            else:
                depth_image = np.zeros((depth_height, depth_width, 3), dtype=np.uint8)
            
            # 调整深度图尺寸以匹配彩色图
            if depth_image.shape[:2] != color_image.shape[:2]:
                depth_image = cv2.resize(depth_image, (color_image.shape[1], color_image.shape[0]))
            
            # 水平拼接
            combined = np.hstack((color_image, depth_image))
            
            # 添加相机信息
            cv2.putText(combined, f"Cam{camera_index}: {serial[-6:]}", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(combined, f"Frame: {frame_count}", 
                       (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # 添加时间戳
            timestamp = color_frame.get_timestamp()
            cv2.putText(combined, f"TS: {timestamp/1e6:.2f}ms", 
                       (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # 添加到队列
            frame_queue.put({
                'camera_index': camera_index,
                'frame': combined,
                'frame_count': frame_count,
                'timestamp': timestamp
            })
            
            frame_count += 1
            
            # 每2秒输出一次状态
            current_time = time.time()
            if current_time - last_log_time > 2.0:
                fps = frame_count / (current_time - last_log_time) if frame_count > 0 else 0
                print(f"相机{camera_index}: {frame_count}帧, 实时FPS: {fps:.1f}")
                frame_count = 0
                last_log_time = current_time
                
        except Exception as e:
            print(f"相机{camera_index}捕获异常: {e}")
            time.sleep(0.1)
    
    print(f"相机{camera_index}捕获线程结束")

def main():
    # 初始化上下文
    ctx = Context()
    device_list = ctx.query_devices()
    
    if device_list.get_count() == 0:
        print("❌ 未发现相机，请检查USB连接")
        return
    
    print(f"✅ 检测到 {device_list.get_count()} 台相机")
    
    # 同时配置和启动所有相机
    print("\n🚀 正在同时启动所有相机...")
    pipelines = []
    
    for i in range(device_list.get_count()):
        device = device_list.get_device_by_index(i)
        pipeline_info = setup_camera_pipeline(device, i)
        
        if pipeline_info['pipeline'] is not None:
            pipelines.append(pipeline_info)
        else:
            print(f"❌ 相机{i}配置失败: {pipeline_info['errors']}")
    
    if not pipelines:
        print("❌ 没有可用的相机配置，退出")
        return
    
    print(f"\n🎯 成功启动 {len(pipelines)} 台相机")
    
    # 创建帧队列和停止事件
    frame_queue = Queue(maxsize=20)
    stop_event = threading.Event()
    
    # 启动捕获线程
    capture_threads = []
    for pipeline_info in pipelines:
        thread = threading.Thread(
            target=camera_capture_worker,
            args=(pipeline_info, frame_queue, stop_event),
            daemon=True
        )
        thread.start()
        capture_threads.append(thread)
        print(f"📹 启动相机{pipeline_info['index']}捕获线程")
    
    print("\n🎬 双相机同步运行中...")
    print("════════════════════════════════════════════")
    print("控制指令:")
    print("  • 按 'q' 或 ESC 键 - 退出程序")
    print("  • 按 's' 键 - 保存当前帧到文件")
    print("  • 按 'p' 键 - 暂停/继续显示")
    print("════════════════════════════════════════════")
    
    # 创建显示窗口
    window_names = []
    for pipeline_info in pipelines:
        window_name = f"Camera {pipeline_info['index']} - {pipeline_info['serial'][-6:]}"
        window_names.append(window_name)
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 640, 240)  # 设置窗口大小

        # =========== 👇 在这里添加位置设置代码 👇 ===========
        # 根据相机索引(index)计算纵向位置
        # 50是起始Y坐标，520是垂直间距（窗口高度480 + 标题栏间隔40）
        x_pos = 5 
        y_pos = 5 + (pipeline_info['index'] * 520) 
        
        cv2.moveWindow(window_name, x_pos, y_pos)
        # =================================================
    # 主显示循环
    display_enabled = True
    last_fps_time = time.time()
    fps_frame_count = 0
    
    try:
        while True:
            # 处理所有待显示的帧
            frames_to_display = {}
            while not frame_queue.empty():
                frame_data = frame_queue.get_nowait()
                frames_to_display[frame_data['camera_index']] = frame_data
            
            # 显示帧
            if display_enabled and frames_to_display:
                for camera_index, frame_data in frames_to_display.items():
                    window_name = window_names[camera_index]
                    cv2.imshow(window_name, frame_data['frame'])
                
                fps_frame_count += 1
            
            # 计算并显示FPS
            current_time = time.time()
            if current_time - last_fps_time >= 1.0:
                fps = fps_frame_count / (current_time - last_fps_time)
                print(f"\r📊 显示FPS: {fps:.1f} | 按'q'退出 | 队列大小: {frame_queue.qsize()}", end="")
                fps_frame_count = 0
                last_fps_time = current_time
            
            # 键盘控制
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q') or key == 27:  # 'q' 或 ESC
                print("\n\n🛑 用户请求退出")
                break
            elif key == ord('s'):  # 保存当前帧
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                save_dir = "saved_frames"
                os.makedirs(save_dir, exist_ok=True)
                
                for camera_index, frame_data in frames_to_display.items():
                    filename = f"{save_dir}/cam{camera_index}_{timestamp}.png"
                    cv2.imwrite(filename, frame_data['frame'])
                    print(f"💾 保存相机{camera_index}帧: {filename}")
                
                # 添加短暂延迟防止重复保存
                time.sleep(0.3)
            elif key == ord('p'):  # 暂停/继续显示
                display_enabled = not display_enabled
                status = "继续" if display_enabled else "暂停"
                print(f"\n⏸️  显示{status}")
                
                # 暂停时显示纯色画面
                if not display_enabled:
                    for window_name in window_names:
                        blank_frame = np.zeros((480, 1280, 3), dtype=np.uint8)
                        cv2.putText(blank_frame, "显示已暂停", 
                                   (500, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                        cv2.putText(blank_frame, "按 'p' 键继续", 
                                   (470, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                        cv2.imshow(window_name, blank_frame)
            
            # 控制循环频率
            time.sleep(0.001)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  检测到中断信号")
    except Exception as e:
        print(f"\n\n❌ 运行时错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 停止所有线程
        print("\n🛑 正在停止所有相机...")
        stop_event.set()
        
        # 等待线程结束
        for thread in capture_threads:
            thread.join(timeout=2.0)
        
        # 停止所有pipeline
        print("正在释放相机资源...")
        for pipeline_info in pipelines:
            if pipeline_info['pipeline']:
                try:
                    pipeline_info['pipeline'].stop()
                    print(f"✅ 相机{pipeline_info['index']}已停止")
                except Exception as e:
                    print(f"❌ 停止相机{pipeline_info['index']}时出错: {e}")
        
        # 关闭所有窗口
        cv2.destroyAllWindows()
        
        # 清空队列
        while not frame_queue.empty():
            try:
                frame_queue.get_nowait()
            except:
                pass
        
        print("\n🎉 程序结束，所有资源已释放")

if __name__ == "__main__":
    main()