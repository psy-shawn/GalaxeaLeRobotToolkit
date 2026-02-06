#!/usr/bin/env python3
"""
批量对齐外部相机数据到原始机器人数据
自动查找匹配的相机目录并裁剪视频到对应时间段
"""
import argparse
import csv
import os
import subprocess
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
import glob


def read_metadata_start_ns(metadata_path: str) -> Tuple[int, Optional[int]]:
    """读取 metadata.yaml 中的开始时间和持续时间"""
    with open(metadata_path, 'r') as f:
        meta = yaml.safe_load(f)
    rbi = meta.get('rosbag2_bagfile_information', {})
    
    start_ns = None
    duration_ns = None
    
    if 'starting_time' in rbi and isinstance(rbi['starting_time'], dict):
        start_ns = rbi['starting_time'].get('nanoseconds_since_epoch') or rbi['starting_time'].get('nanoseconds')
    
    if start_ns is None:
        files = rbi.get('files', [])
        if files and isinstance(files, list) and 'starting_time' in files[0]:
            start_ns = files[0]['starting_time'].get('nanoseconds_since_epoch') or files[0]['starting_time'].get('nanoseconds')
            duration_ns = files[0]['duration'].get('nanoseconds') if 'duration' in files[0] else None
    
    if duration_ns is None:
        dur = rbi.get('duration')
        if dur and 'nanoseconds' in dur:
            duration_ns = dur['nanoseconds']
    
    if start_ns is None:
        raise RuntimeError(f"cannot find starting_time in {metadata_path}")
    
    return int(start_ns), int(duration_ns) if duration_ns is not None else None


def parse_cam_dir_timestamp(dirname: str) -> Optional[int]:
    """解析相机目录名称中的时间戳 (YYYYMMDD_HHMMSS)"""
    try:
        dt = datetime.strptime(dirname, "%Y%m%d_%H%M%S")
        return int(time.mktime(dt.timetuple()))
    except Exception:
        return None


def is_camera_dir_complete(cam_dir: Path, subdir: str) -> bool:
    """检查相机子目录是否包含所有必需文件"""
    d = cam_dir / subdir
    return (d / 'timestamps.csv').exists() and \
           ((d / 'rgb_video.mp4').exists() or (d / 'rgb_video.MP4').exists()) and \
           ((d / 'depth_video.mp4').exists() or (d / 'depth_video.MP4').exists())


def find_matching_camera_dir(metadata_path: str, camera_base: Path, 
                             max_time_diff: int, top_subdir: str, 
                             left_subdir: str) -> Optional[Path]:
    """查找时间匹配的相机目录"""
    try:
        start_ns, _ = read_metadata_start_ns(metadata_path)
        raw_ts = int(start_ns // 1_000_000_000)
    except Exception as e:
        print(f"  Warning: cannot read timestamp from {metadata_path}: {e}")
        return None
    
    if not camera_base.exists():
        return None
    
    best_dir = None
    best_diff = None
    
    for item in sorted(camera_base.iterdir()):
        if not item.is_dir():
            continue
        
        cam_ts = parse_cam_dir_timestamp(item.name)
        if cam_ts is None:
            continue
        
        diff = abs(cam_ts - raw_ts)
        if diff > max_time_diff:
            continue
        
        # 至少一个相机目录完整才可用
        if not (is_camera_dir_complete(item, top_subdir) or 
                is_camera_dir_complete(item, left_subdir)):
            continue
        
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_dir = item
    
    return best_dir


def read_csv_timestamps(csv_path: str) -> List[Tuple[int, int]]:
    """读取 CSV 时间戳文件，返回 (frame_index, system_ts_ns) 列表"""
    rows = []
    with open(csv_path, newline='') as f:
        dr = csv.DictReader(f)
        for r in dr:
            fi = int(r['Frame_Index'])
            sys_ns = int(r['System_Timestamp_ns'])
            rows.append((fi, sys_ns))
    rows.sort(key=lambda x: x[0])
    return rows


def compute_frame_range(csv_rows: List[Tuple[int, int]], start_ns: int, 
                       duration_ns: Optional[int], ext_fps: float) -> Optional[Tuple[int, int]]:
    """计算需要裁剪的帧范围
    
    返回 (start_frame, end_frame) 或 None（如果无有效帧）
    改进逻辑：允许相机时间与元数据时间有偏移
    """
    if not csv_rows:
        return None
    
    # 计算所有帧相对于开始时间的偏移（秒）
    frame_times = []
    for fi, sys_ns in csv_rows:
        rel_s = (sys_ns - start_ns) / 1e9
        frame_times.append((fi, rel_s))
    
    # 按相对时间排序
    frame_times.sort(key=lambda x: x[1])
    
    # 确定结束时间限制
    if duration_ns is not None:
        end_time_limit = duration_ns / 1e9
    else:
        end_time_limit = float('inf')
    
    # 策略：找到与 [0, duration] 有交集的帧
    # 如果所有帧都在元数据时间之前或之后，尝试使用最接近的帧
    valid_frames = [(fi, t) for fi, t in frame_times if 0 <= t <= end_time_limit]
    
    if valid_frames:
        start_frame = valid_frames[0][0]
        end_frame = valid_frames[-1][0]
        return (start_frame, end_frame)
    
    # 如果没有完全重叠的帧，尝试找最接近的
    # 情况1：所有帧都在元数据之前（相机提前录制）
    if all(t < 0 for _, t in frame_times):
        # 使用最后几帧（最接近开始时间）
        start_idx = max(0, len(frame_times) - int(duration_ns / 1e9 * ext_fps) if duration_ns else 0)
        start_frame = frame_times[start_idx][0]
        end_frame = frame_times[-1][0]
        print(f"  Warning: all camera frames before metadata start, using last {end_frame - start_frame + 1} frames")
        return (start_frame, end_frame)
    
    # 情况2：所有帧都在元数据之后（相机延迟录制）
    if all(t > end_time_limit for _, t in frame_times):
        # 使用前几帧
        end_idx = min(len(frame_times), int(duration_ns / 1e9 * ext_fps) if duration_ns else len(frame_times))
        start_frame = frame_times[0][0]
        end_frame = frame_times[end_idx - 1][0]
        print(f"  Warning: all camera frames after metadata end, using first {end_frame - start_frame + 1} frames")
        return (start_frame, end_frame)
    
    # 情况3：部分重叠，使用重叠部分
    overlapping = [(fi, t) for fi, t in frame_times if t < end_time_limit]
    if overlapping:
        # 找最接近0的帧作为起始
        closest_to_start = min(overlapping, key=lambda x: abs(x[1]))
        start_idx = frame_times.index(closest_to_start)
        start_frame = frame_times[start_idx][0]
        end_frame = overlapping[-1][0]
        return (start_frame, end_frame)
    
    return None


def crop_video(input_video: Path, start_frame: int, end_frame: int, 
              output_video: Path, ext_fps: float, is_depth: bool = False) -> bool:
    """裁剪视频到指定帧范围"""
    start_time = start_frame / ext_fps
    duration = (end_frame - start_frame + 1) / ext_fps
    
    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-ss', f'{start_time:.6f}',
        '-i', str(input_video),
        '-t', f'{duration:.6f}',
        '-c', 'copy',
        str(output_video)
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Error cropping {'depth' if is_depth else 'RGB'} video: {e.stderr}")
        return False


def process_single_raw(raw_json: Path, data_root: Path, cam_root: Path,
                      top_cam_subdir: str, left_cam_subdir: str,
                      ext_fps: float, max_time_diff: int) -> dict:
    """处理单个 RAW 数据的相机对齐"""
    result = {'raw': str(raw_json), 'status': 'skip', 'reason': ''}
    
    raw_parent = raw_json.parent
    rel_path = raw_parent.relative_to(data_root)
    raw_base = raw_json.stem
    
    # 检查 metadata
    metadata_yaml = raw_parent / raw_base / 'metadata.yaml'
    if not metadata_yaml.exists():
        result['reason'] = 'metadata missing'
        return result
    
    # 查找匹配的相机目录
    camera_base = cam_root / rel_path
    camera_dir = find_matching_camera_dir(str(metadata_yaml), camera_base,
                                         max_time_diff, top_cam_subdir, left_cam_subdir)
    
    if camera_dir is None:
        result['reason'] = f'no matching camera dir in {camera_base}'
        return result
    
    print(f"\n✓ Matched: {raw_base} <-> {camera_dir.name}")
    
    # 读取元数据时间
    try:
        start_ns, duration_ns = read_metadata_start_ns(str(metadata_yaml))
    except Exception as e:
        result['reason'] = f'cannot read metadata: {e}'
        return result
    
    # 创建输出目录
    out_top_dir = raw_parent / 'extra_cam' / 'top'
    out_left_dir = raw_parent / 'extra_cam' / 'left'
    out_top_dir.mkdir(parents=True, exist_ok=True)
    out_left_dir.mkdir(parents=True, exist_ok=True)
    
    processed_count = 0
    
    # 处理俯视相机
    top_cam_dir = camera_dir / top_cam_subdir
    if is_camera_dir_complete(camera_dir, top_cam_subdir):
        print(f"  Processing TOP camera...")
        if process_camera(top_cam_dir, metadata_yaml, start_ns, duration_ns,
                         out_top_dir, ext_fps):
            processed_count += 1
    
    # 处理左视相机
    left_cam_dir = camera_dir / left_cam_subdir
    if is_camera_dir_complete(camera_dir, left_cam_subdir):
        print(f"  Processing LEFT camera...")
        if process_camera(left_cam_dir, metadata_yaml, start_ns, duration_ns,
                         out_left_dir, ext_fps):
            processed_count += 1
    
    if processed_count > 0:
        result['status'] = 'success'
        result['reason'] = f'{processed_count} camera(s) processed'
    else:
        result['reason'] = 'no cameras processed successfully'
    
    return result


def process_camera(cam_dir: Path, metadata_yaml: Path, start_ns: int,
                  duration_ns: Optional[int], output_dir: Path, ext_fps: float) -> bool:
    """处理单个相机目录"""
    csv_path = cam_dir / 'timestamps.csv'
    rgb_video = cam_dir / 'rgb_video.mp4'
    depth_video = cam_dir / 'depth_video.mp4'
    
    # 读取 CSV 时间戳
    try:
        csv_rows = read_csv_timestamps(str(csv_path))
    except Exception as e:
        print(f"    Error reading CSV: {e}")
        return False
    
    # 计算帧范围
    frame_range = compute_frame_range(csv_rows, start_ns, duration_ns, ext_fps)
    if frame_range is None:
        print(f"    Warning: no valid frame range found")
        return False
    
    start_frame, end_frame = frame_range
    print(f"    Frame range: {start_frame} - {end_frame} ({end_frame - start_frame + 1} frames)")
    
    # 裁剪 RGB 视频
    out_rgb = output_dir / 'rgb_cropped.mp4'
    if not crop_video(rgb_video, start_frame, end_frame, out_rgb, ext_fps, is_depth=False):
        return False
    
    # 裁剪深度视频
    out_depth = output_dir / 'depth_cropped.mp4'
    if not crop_video(depth_video, start_frame, end_frame, out_depth, ext_fps, is_depth=True):
        return False
    
    print(f"    ✓ Saved to {output_dir}")
    return True


def batch_process(data_root: str, cam_root: str, top_cam_subdir: str,
                 left_cam_subdir: str, ext_fps: float, max_time_diff: int):
    """批量处理所有 RAW 数据"""
    data_root = Path(data_root)
    cam_root = Path(cam_root)
    
    # 查找所有 *_RAW.json 文件
    raw_jsons = sorted(data_root.glob('**/*_RAW.json'))
    
    print(f"Found {len(raw_jsons)} RAW datasets to process\n")
    print("=" * 80)
    
    results = []
    for raw_json in raw_jsons:
        result = process_single_raw(raw_json, data_root, cam_root,
                                   top_cam_subdir, left_cam_subdir,
                                   ext_fps, max_time_diff)
        results.append(result)
    
    # 统计结果
    success_count = sum(1 for r in results if r['status'] == 'success')
    skip_count = len(results) - success_count
    
    print("\n" + "=" * 80)
    print(f"Summary: {success_count} succeeded, {skip_count} skipped")
    
    # 显示跳过的原因统计
    if skip_count > 0:
        print("\nSkipped reasons:")
        from collections import Counter
        reasons = Counter(r['reason'] for r in results if r['status'] == 'skip')
        for reason, count in reasons.most_common():
            print(f"  - {reason}: {count}")


def parse_args():
    p = argparse.ArgumentParser(description="批量对齐外部相机数据到原始机器人数据")
    p.add_argument('--data-root', required=True, help='原始数据根目录')
    p.add_argument('--cam-root', required=True, help='外部相机数据根目录')
    p.add_argument('--top-cam-subdir', default='cam_CP0E753000BN', help='俯视相机子目录名')
    p.add_argument('--left-cam-subdir', default='cam_CP0E753000AH', help='左视相机子目录名')
    p.add_argument('--ext-fps', type=float, default=15.0, help='外部相机帧率')
    p.add_argument('--max-time-diff', type=int, default=60, help='允许的最大时间差（秒）')
    return p.parse_args()


def main():
    args = parse_args()
    batch_process(args.data_root, args.cam_root, args.top_cam_subdir,
                 args.left_cam_subdir, args.ext_fps, args.max_time_diff)


if __name__ == '__main__':
    main()