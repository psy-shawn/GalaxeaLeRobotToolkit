#!/bin/bash
# source /Users/psy/workspace/GalaxeaLeRobotToolkit/install/setup.zsh
# 使用实际存在数据的目录
dataset_name=pick_3_bottles_and_place_them_into_trashbin
input_dir=/Users/psy/workspace/data/r1lite/test/20260204/pick_3_bottles_and_place_them_into_trashbin
output_dir=/Users/psy/workspace/data/lerobot/
robot_type=R1Lite # options: R1Pro, R1Lite

# # Fix OpenMP conflict on macOS
export KMP_DUPLICATE_LIB_OK=TRUE
# export OMP_NUM_THREADS=1

export SAVE_VIDEO=1 
export USE_H264=0
export USE_COMPRESSION=0
export IS_COMPUTE_EPISODE_STATS_IMAGE=1
export MAX_PROCESSES=4
export USE_ROS1=0
export USE_TRANSLATION=0

python -m dataset_converter_old \
    --input_dir $input_dir \
    --output_dir $output_dir \
    --robot_type $robot_type \
    --dataset_name $dataset_name