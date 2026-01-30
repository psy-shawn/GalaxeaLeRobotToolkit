#!/bin/bash

# 检查是否提供了目录参数
if [ $# -eq 0 ]; then
    echo "Usage: $0 <directory>"
    echo "Example: $0 ../data/20260129"
    exit 1
fi

TARGET_DIR="$1"

# 检查目录是否存在
if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Directory '$TARGET_DIR' does not exist"
    exit 1
fi

echo "Searching for add_label.sh in: $TARGET_DIR"
echo "----------------------------------------"

# 查找所有的 add_label.sh 文件并运行
find "$TARGET_DIR" -type f -name "add_label.sh" | while read -r script; do
    script_dir=$(dirname "$script")
    echo "Found: $script"
    echo "Executing in directory: $script_dir"
    
    # 进入脚本所在目录并执行
    (cd "$script_dir" && bash add_label.sh)
    
    if [ $? -eq 0 ]; then
        echo "✓ Successfully executed: $script"
    else
        echo "✗ Failed to execute: $script"
    fi
    echo "----------------------------------------"
done

echo "All add_label.sh scripts have been processed."
