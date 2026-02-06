#!/usr/bin/env bash
set -e

# 配置参数
DATA_ROOT="/Users/psy/workspace/data/r1lite/20260203"
CAM_ROOT="/Users/psy/workspace/data/recordings/20260203"
TOP_CAM_SUBDIR="cam_CP0E753000BN"
LEFT_CAM_SUBDIR="cam_CP0E753000AH"
EXT_FPS=15
MAX_TIME_DIFF_SEC=60

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 调用 Python 脚本批量处理
python3 "${SCRIPT_DIR}/align_and_crop_cam.py" \
    --data-root "$DATA_ROOT" \
    --cam-root "$CAM_ROOT" \
    --top-cam-subdir "$TOP_CAM_SUBDIR" \
    --left-cam-subdir "$LEFT_CAM_SUBDIR" \
    --ext-fps "$EXT_FPS" \
    --max-time-diff "$MAX_TIME_DIFF_SEC"