#!/usr/bin/env python3
"""
Align external camera timestamps (CSV nanoseconds) to an episode metadata start time
and crop the external RGB MP4 and copy corresponding depth frames.

Example (depth as images):
  python align_and_crop_cam.py \
    --metadata /home/r1lite/OpenGalaxea/GalaxeaDataset/20260120/pick/pick_tissue_box/RB251106042_20260120222037424_RAW/metadata.yaml \
    --csv /home/r1lite/recordings/cam_CP0E753000AH_20260127_234055/timestamps.csv \
    --rgb /home/r1lite/recordings/cam_CP0E753000AH_20260127_234055/rgb_video.mp4 \
    --depth /home/r1lite/recordings/cam_CP0E753000AH_20260127_234055/depth_raw \
    --out_video ./rgb_cropped.mp4 \
    --out_depth ./depth_cropped \
    --ext_fps 15 \
    --dry_run

Example (depth as video):
  python align_and_crop_cam.py \
    --metadata /home/r1lite/OpenGalaxea/GalaxeaDataset/20260120/pick/pick_tissue_box/RB251106042_20260120222037424_RAW/metadata.yaml \
    --csv /home/r1lite/recordings/cam_CP0E753000AH_20260127_234055/timestamps.csv \
    --rgb /home/r1lite/recordings/cam_CP0E753000AH_20260127_234055/rgb_video.mp4 \
    --depth /home/r1lite/recordings/cam_CP0E753000AH_20260127_234055/depth_video.mp4 \
    --out_video ./rgb_cropped.mp4 \
    --out_depth ./depth_cropped.mp4 \
    --ext_fps 15 \
    --depth_is_video \
    --dry_run

Notes:
- CSV must contain columns: Frame_Index,System_Timestamp_ns (nanoseconds since epoch)
- metadata.yaml must contain starting_time.nanoseconds_since_epoch (or files[0].starting_time...)
- For depth images: filenames are assumed numeric (e.g. 000001.png). Script tries to detect padding and 0/1 base.
- For depth video: use --depth_is_video flag, output will also be a video file.
"""
import argparse
import csv
import os
import subprocess
import sys
import yaml
from pathlib import Path
from typing import List, Tuple

def read_metadata_start_ns(metadata_path: str) -> Tuple[int, int]:
    with open(metadata_path, 'r') as f:
        meta = yaml.safe_load(f)
    rbi = meta.get('rosbag2_bagfile_information', {})
    # Try common locations
    start_ns = None
    duration_ns = None
    if 'starting_time' in rbi and isinstance(rbi['starting_time'], dict):
        start_ns = rbi['starting_time'].get('nanoseconds_since_epoch') or rbi['starting_time'].get('nanoseconds')
    if start_ns is None:
        files = rbi.get('files', [])
        if files and isinstance(files, list) and 'starting_time' in files[0]:
            start_ns = files[0]['starting_time'].get('nanoseconds_since_epoch') or files[0]['starting_time'].get('nanoseconds')
            duration_ns = files[0]['duration'].get('nanoseconds') if 'duration' in files[0] else None
    # fallback duration in top-level
    if duration_ns is None:
        dur = rbi.get('duration')
        if dur and 'nanoseconds' in dur:
            duration_ns = dur['nanoseconds']
    if start_ns is None:
        raise RuntimeError(f"cannot find starting_time in {metadata_path}")
    return int(start_ns), int(duration_ns) if duration_ns is not None else None

def read_csv_timestamps(csv_path: str) -> List[Tuple[int,int]]:
    # returns list of (frame_index, system_ts_ns)
    rows = []
    with open(csv_path, newline='') as f:
        dr = csv.DictReader(f)
        for r in dr:
            fi = int(r['Frame_Index'])
            sys_ns = int(r['System_Timestamp_ns'])
            rows.append((fi, sys_ns))
    rows.sort(key=lambda x: x[0])
    return rows

def compute_rel_seconds(rows: List[Tuple[int,int]], start_ns: int):
    # returns list of dicts with frame_index, sys_ns, rel_s
    out = []
    for fi, sys_ns in rows:
        rel = (sys_ns - start_ns) / 1e9
        out.append({'frame_index': fi, 'sys_ns': sys_ns, 'rel_s': rel})
    return out

def detect_depth_naming(depth_dir: Path):
    files = sorted([p.name for p in depth_dir.iterdir() if p.is_file()])
    if not files:
        raise RuntimeError(f"no files found in {depth_dir}")
    # find first numeric filename part
    for name in files:
        stem = Path(name).stem
        if stem.isdigit():
            pad = len(stem)
            first_val = int(stem)
            return pad, first_val
    # fallback: try parse filename like 000001.png by stripping ext
    raise RuntimeError("no numeric depth filenames detected")

def is_video_file(path: Path) -> bool:
    """Check if the path is a video file (by extension)."""
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}
    return path.suffix.lower() in video_extensions


def find_start_end_indices(rel_list, start_offset=0.0, end_offset=None, duration_s=None):
    # rel_list: list of dicts with rel_s; may not overlap with [0,duration]
    # We'll pick the nearest frames to start_offset and to end_time_limit (fallback)
    if not rel_list:
        raise RuntimeError("empty rel_list")
    # sort by rel_s to be safe
    rel_sorted = sorted(rel_list, key=lambda e: e['rel_s'])
    times = [e['rel_s'] for e in rel_sorted]
    frames = [e['frame_index'] for e in rel_sorted]
    import bisect

    # determine time limit for end
    if end_offset is not None:
        end_time_limit = end_offset
    elif duration_s is not None:
        end_time_limit = duration_s
    else:
        end_time_limit = float('inf')

    # find start: first frame with rel_s >= start_offset, else nearest (last frame before or closest)
    pos = bisect.bisect_left(times, start_offset)
    if pos < len(times):
        start_idx = frames[pos]
    else:
        # all frames are before start_offset -> pick last frame
        start_idx = frames[-1]

    # find end: last frame with rel_s <= end_time_limit, else nearest (first after or closest)
    pos_end = bisect.bisect_right(times, end_time_limit) - 1
    if pos_end >= 0:
        end_idx = frames[pos_end]
    else:
        # all frames are after end_time_limit -> pick first frame
        end_idx = frames[0]

    # if the selected end is before start, try to pick nearest frames by absolute difference
    if end_idx < start_idx:
        # compute nearest indices to start_offset and end_time_limit by absolute diff
        start_diff_idx = min(range(len(times)), key=lambda i: abs(times[i] - start_offset))
        end_diff_idx = min(range(len(times)), key=lambda i: abs(times[i] - end_time_limit))
        start_idx = frames[start_diff_idx]
        end_idx = frames[end_diff_idx]

    if end_idx < start_idx:
        raise RuntimeError("end frame is before start frame after alignment (even after fallback)")
    return start_idx, end_idx

def ffmpeg_crop(input_mp4: str, start_time: float, duration: float, out_mp4: str, dry_run=False):
    # Use -ss START -i INPUT -t DURATION -c copy OUT for faster copy (may be keyframe related)
    cmd = [
        'ffmpeg', '-y',
        '-ss', f'{start_time:.6f}',
        '-i', input_mp4,
        '-t', f'{duration:.6f}',
        '-c', 'copy',
        out_mp4
    ]
    print("ffmpeg command:", ' '.join(cmd))
    if dry_run:
        return
    subprocess.check_call(cmd)

def ffmpeg_depth_crop(input_video: str, start_time: float, duration: float, out_video: str, dry_run=False):
    # Crop depth video (16-bit grayscale) using re-encoding for precise frame handling
    # -pix_fmt gray16le ensures 16-bit grayscale output for depth data
    cmd = [
        'ffmpeg', '-y',
        '-ss', f'{start_time:.6f}',
        '-i', input_video,
        '-t', f'{duration:.6f}',
        '-c', 'copy',
        out_video
    ]
    print("depth ffmpeg command:", ' '.join(cmd))
    if dry_run:
        return
    subprocess.check_call(cmd)

def copy_depth_frames(depth_dir: Path, out_dir: Path, start_frame: int, end_frame: int, pad: int, first_val: int, dry_run=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    # Determine whether file index base is 0 or 1 by comparing first_val
    base_offset = 0 if first_val == 0 else 1
    for frame in range(start_frame, end_frame + 1):
        file_index = frame + base_offset
        fname = f"{file_index:0{pad}d}.png"
        src = depth_dir / fname
        if not src.exists():
            # warn and continue
            print(f"warning: depth file missing: {src}")
            continue
        dst = out_dir / fname
        print(f"copy {src} -> {dst}")
        if not dry_run:
            import shutil
            shutil.copy2(src, dst)

def parse_args():
    p = argparse.ArgumentParser(description="Align external camera CSV timestamps to metadata start and crop RGB+depth.")
    p.add_argument('--metadata', required=True, help='path to metadata.yaml (episode to use as start)')
    p.add_argument('--csv', required=True, help='external camera timestamps CSV (Frame_Index,System_Timestamp_ns,...)')
    p.add_argument('--rgb', required=True, help='external RGB mp4 path')
    p.add_argument('--depth', required=True, help='depth input: either a directory with depth images (numeric names like 000001.png) or a depth video file (.mp4)')
    p.add_argument('--out_video', required=True, help='output cropped RGB mp4 path')
    p.add_argument('--out_depth', required=True, help='output: either directory for cropped depth frames OR output video path (if --depth_is_video)')
    p.add_argument('--ext_fps', type=float, default=30.0, help='external camera FPS (default 30)')
    p.add_argument('--start_offset', type=float, default=0.0, help='seconds after episode start to begin crop (default 0)')
    p.add_argument('--end_offset', type=float, default=None, help='seconds after episode start to end crop (default: metadata duration)')
    p.add_argument('--depth_is_video', action='store_true', help='treat --depth as a video file instead of image directory')
    p.add_argument('--dry_run', action='store_true', help='do not run ffmpeg or copy files, just print actions')
    return p.parse_args()

def main():
    args = parse_args()
    metadata = Path(args.metadata)
    csvp = Path(args.csv)
    rgbp = Path(args.rgb)
    depth_input = Path(args.depth)
    out_video = Path(args.out_video)
    out_depth = Path(args.out_depth)

    start_ns, duration_ns = read_metadata_start_ns(str(metadata))
    duration_s = (duration_ns / 1e9) if duration_ns else None
    print(f"episode start_ns={start_ns} ({start_ns/1e9:.6f}s since epoch), duration_s={duration_s}")

    rows = read_csv_timestamps(str(csvp))
    rel = compute_rel_seconds(rows, start_ns)

    # debug show sample
    print(f"CSV rows read: {len(rel)}. sample: {rel[0] if rel else 'empty'}")

    # determine start/end frame indices
    start_frame, end_frame = find_start_end_indices(rel, start_offset=args.start_offset, end_offset=args.end_offset, duration_s=duration_s)
    print(f"determined frames: start_frame={start_frame}, end_frame={end_frame}")

    # compute ffmpeg times (relative to external video start)
    start_time = start_frame / float(args.ext_fps)
    duration = (end_frame - start_frame + 1) / float(args.ext_fps)
    print(f"FFmpeg will crop from {start_time:.6f}s for duration {duration:.6f}s (ext_fps={args.ext_fps})")

    if args.dry_run:
        print("DRY RUN: no ffmpeg or file operations will be executed.")

    # Process RGB video
    ffmpeg_crop(str(rgbp), start_time, duration, str(out_video), dry_run=args.dry_run)

    # Process depth: either as video or as image directory
    if args.depth_is_video:
        # Depth is a video file, crop it similarly
        if not is_video_file(depth_input):
            raise RuntimeError(f"depth_is_video is set but --depth is not a video file: {depth_input}")
        depth_output = out_depth  # out_depth is the output video path
        print(f"Cropping depth video: {depth_input} -> {depth_output}")
        ffmpeg_crop(str(depth_input), start_time, duration, str(depth_output), dry_run=args.dry_run)
        print("done. outputs:")
        print("  video ->", out_video)
        print("  depth video ->", depth_output)
    else:
        # Depth is a directory of images
        if not depth_input.is_dir():
            raise RuntimeError(f"--depth is not a directory: {depth_input}")
        # depth frames copy: detect pad & base
        pad, first_val = detect_depth_naming(depth_input)
        print(f"detected depth naming pad={pad}, first_val={first_val}")
        copy_depth_frames(depth_input, out_depth, start_frame, end_frame, pad, first_val, dry_run=args.dry_run)
        print("done. outputs:")
        print("  video ->", out_video)
        print("  depth dir ->", out_depth)

if __name__ == '__main__':
    main()

"""
# Example usage with depth as images:

cd /Users/hsong/repos/scripts

VIDEO_DIR=/Users/hsong/repos/scripts/recordings/20260202/pick_3_bottles_and_place_them_into_trashbin/left_arm/order_low_tall_mid/20260202_231415
python3 align_and_crop_cam.py \
  --metadata $VIDEO_DIR/metadata.yaml \
  --csv $VIDEO_DIR/cam_CP0E753000AH/timestamps.csv \
  --rgb $VIDEO_DIR/cam_CP0E753000AH/rgb_video.mp4 \
  --depth_is_video \
  --depth $VIDEO_DIR/cam_CP0E753000AH/depth_video.mp4 \
  --out_video $VIDEO_DIR/cam_CP0E753000AH/aligned_rgb.mp4 \
  --out_depth $VIDEO_DIR/cam_CP0E753000AH/aligned_depth.mp4 \
  --ext_fps 15

python3 align_and_crop_cam.py \
  --metadata $VIDEO_DIR/metadata.yaml \
  --csv $VIDEO_DIR/cam_CP0E753000BN/timestamps.csv \
  --rgb $VIDEO_DIR/cam_CP0E753000BN/rgb_video.mp4 \
  --depth_is_video \
  --depth $VIDEO_DIR/cam_CP0E753000BN/depth_video.mp4 \
  --out_video $VIDEO_DIR/cam_CP0E753000BN/aligned_rgb.mp4 \
  --out_depth $VIDEO_DIR/cam_CP0E753000BN/aligned_depth.mp4 \
  --ext_fps 15

"""