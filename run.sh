#!/bin/bash
dataset_name=pick_cola_bottle_by_left_hand
input_dir=/Users/psy/workspace/data/r1lite/20260129/pick/pick_cola_bottle/left
output_dir=/Users/psy/workspace/data/lerobot/
robot_type=R1Lite # options: R1Pro, R1Lite

export SAVE_VIDEO=1 
export USE_H264=0
export USE_COMPRESSION=0
export IS_COMPUTE_EPISODE_STATS_IMAGE=1
export MAX_PROCESSES=4
export USE_ROS1=0
export USE_TRANSLATION=0

python -m dataset_converter \
    --input_dir $input_dir \
    --output_dir $output_dir \
    --robot_type $robot_type \
    --dataset_name $dataset_name