#!/usr/bin/env bash
set -e

# 配置参数
DATA_ROOT="/Users/psy/workspace/data/galaxea/r1lite/20260206/pick_place"
CAM_ROOT="/Users/psy/workspace/data/recordings/pick_place"
TOP_CAM_SUBDIR="cam_CP0E753000BN"
LEFT_CAM_SUBDIR="cam_CP0E753000AH"
EXT_FPS=15
MAX_TIME_DIFF_SEC=60

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==================================="
echo "外部相机视频对齐与修复工具"
echo "==================================="
echo ""

# 第一步: 调用 Python 脚本批量处理和对齐视频
echo "步骤 1/2: 对齐视频时间戳..."
python3 "${SCRIPT_DIR}/align_and_crop_cam.py" \
    --data-root "$DATA_ROOT" \
    --cam-root "$CAM_ROOT" \
    --top-cam-subdir "$TOP_CAM_SUBDIR" \
    --left-cam-subdir "$LEFT_CAM_SUBDIR" \
    --ext-fps "$EXT_FPS" \
    --max-time-diff "$MAX_TIME_DIFF_SEC"

echo ""
echo "步骤 2/2: 修复视频以支持浏览器播放..."

# 第二步: 修复生成的视频，使其支持浏览器流式播放
# 检查ffmpeg是否安装
if ! command -v ffmpeg &> /dev/null; then
    echo "警告: 未找到ffmpeg工具，跳过视频修复"
    echo "如需浏览器播放支持，请安装ffmpeg:"
    echo "  macOS: brew install ffmpeg"
    exit 0
fi

process_video() {
    local input_file="$1"
    local temp_file="${input_file%.mp4}_temp.mp4"
    
    echo "  修复: $(basename "$input_file")"
    
    # 使用ffmpeg重新编码视频以支持浏览器流式播放
    if ffmpeg -i "$input_file" \
        -c:v libx264 \
        -preset fast \
        -crf 23 \
        -movflags +faststart \
        -pix_fmt yuv420p \
        -c:a copy \
        -y \
        "$temp_file" 2>/dev/null; then
        
        # 用修复后的文件替换原文件
        mv "$temp_file" "$input_file"
        echo "    ✓ 成功"
        return 0
    else
        echo "    ✗ 失败"
        rm -f "$temp_file"
        return 1
    fi
}

TOTAL_PROCESSED=0
TOTAL_SUCCESS=0

# 查找所有生成的外部相机视频并修复
echo "  搜索视频文件..."
find "$DATA_ROOT" -type f \( -name "rgb_cropped.mp4" -o -name "depth_cropped.mp4" \) | while read -r video_file; do
    TOTAL_PROCESSED=$((TOTAL_PROCESSED + 1))
    
    if process_video "$video_file"; then
        TOTAL_SUCCESS=$((TOTAL_SUCCESS + 1))
    fi
done

echo ""
echo "==================================="
echo "处理完成!"
echo "==================================="
echo "视频修复: $TOTAL_SUCCESS/$TOTAL_PROCESSED 个文件"
echo ""
echo "✓ 外部相机视频已对齐并修复，可在浏览器中播放"
echo ""