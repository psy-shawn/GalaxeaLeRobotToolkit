"""
视频处理模块：负责视频抽帧和编码
"""
import cv2
import base64
import os
from pathlib import Path
from typing import List, Tuple
import numpy as np


class VideoFrameExtractor:
    """视频抽帧器"""
    
    def __init__(self, fps: int = 1):
        """
        初始化视频抽帧器
        
        Args:
            fps: 抽帧帧率，默认1fps（每秒1帧）
        """
        self.fps = fps
    
    def extract_frames(self, video_path: str) -> List[Tuple[float, np.ndarray]]:
        """
        从视频中抽取关键帧
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            List[(timestamp, frame)]: 时间戳和帧数据的列表
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")
        
        # 获取原始视频帧率
        original_fps = cap.get(cv2.CAP_PROP_FPS)
        frame_interval = int(original_fps / self.fps)  # 每隔多少帧抽取一次
        
        frames = []
        frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 按间隔抽取帧
            if frame_count % frame_interval == 0:
                timestamp = frame_count / original_fps  # 计算时间戳（秒）
                frames.append((timestamp, frame))
            
            frame_count += 1
        
        cap.release()
        print(f"从视频 {Path(video_path).name} 中抽取了 {len(frames)} 帧 (原始fps: {original_fps:.2f}, 抽取fps: {self.fps})")
        
        return frames
    
    def frames_to_base64_list(self, frames: List[Tuple[float, np.ndarray]]) -> List[Tuple[float, str]]:
        """
        将帧列表转换为base64编码列表
        
        Args:
            frames: 时间戳和帧数据的列表
            
        Returns:
            List[(timestamp, base64_str)]: 时间戳和base64编码的列表
        """
        encoded_frames = []
        
        for timestamp, frame in frames:
            # 将帧编码为JPEG格式
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            # 转换为base64
            base64_str = base64.b64encode(buffer).decode('utf-8')
            encoded_frames.append((timestamp, base64_str))
        
        return encoded_frames
    
    def process_video(self, video_path: str) -> List[Tuple[float, str]]:
        """
        处理视频：抽帧并编码为base64
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            List[(timestamp, base64_str)]: 时间戳和base64编码的列表
        """
        frames = self.extract_frames(video_path)
        encoded_frames = self.frames_to_base64_list(frames)
        return encoded_frames


def create_frame_grid(frames: List[Tuple[float, str]], grid_size: int = 9) -> Tuple[List[float], str]:
    """
    创建帧网格图：将多个帧合并为一张网格图
    用于一次性发送给VLM，减少API调用次数
    
    Args:
        frames: 时间戳和base64编码的帧列表
        grid_size: 网格大小（取多少帧）
        
    Returns:
        (timestamps, grid_base64): 选中的时间戳列表和网格图的base64编码
    """
    # 均匀采样帧
    step = max(1, len(frames) // grid_size)
    selected_frames = frames[::step][:grid_size]
    
    if not selected_frames:
        return [], ""
    
    # 解码base64为图像
    images = []
    timestamps = []
    for timestamp, base64_str in selected_frames:
        img_data = base64.b64decode(base64_str)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        images.append(img)
        timestamps.append(timestamp)
    
    # 计算网格大小
    rows = int(np.ceil(np.sqrt(len(images))))
    cols = int(np.ceil(len(images) / rows))
    
    # 获取单个图像尺寸并调整大小
    h, w = images[0].shape[:2]
    target_size = (320, 240)  # 缩小单帧大小以节省带宽
    
    # 创建网格画布
    grid_h = target_size[1] * rows
    grid_w = target_size[0] * cols
    grid = np.zeros((grid_h, grid_w, 3), dtype=np.uint8)
    
    # 将图像放入网格
    for idx, img in enumerate(images):
        row = idx // cols
        col = idx % cols
        resized = cv2.resize(img, target_size)
        
        y1 = row * target_size[1]
        y2 = y1 + target_size[1]
        x1 = col * target_size[0]
        x2 = x1 + target_size[0]
        
        grid[y1:y2, x1:x2] = resized
        
        # 添加时间戳标注
        text = f"{timestamp:.1f}s"
        cv2.putText(grid, text, (x1 + 5, y1 + 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    # 编码为base64
    _, buffer = cv2.imencode('.jpg', grid, [cv2.IMWRITE_JPEG_QUALITY, 85])
    grid_base64 = base64.b64encode(buffer).decode('utf-8')
    
    return timestamps, grid_base64
