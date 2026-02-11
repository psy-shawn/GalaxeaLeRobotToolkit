import pandas as pd
import numpy as np
from scipy.spatial.transform import Rotation as R
import json
import argparse
import os
from pathlib import Path
from tqdm import tqdm

# 尝试导入可视化脚本 (确保 visualize_trajectory.py 在同一目录下)
try:
    import visualize_trajectory
    HAS_VISUALIZER = True
except ImportError:
    HAS_VISUALIZER = False
    print("提示: 未找到 visualize_trajectory.py，可视化功能将被跳过。")

# ==========================================
# 1. 硬编码标定参数 (Calibration Parameters)
# ==========================================

# 静态变换：Base -> Torso
TF_BASE_TO_TORSO = {
    "pos": [0.178, -0.001, 0.588],
    "quat": [0.000, -0.001, 0.000, 1.000]  # xyzw
}

# 静态变换：Torso -> Head Left Camera
TF_TORSO_TO_HEAD_LEFT = {
    "pos": [0.055, 0.031, 0.632],
    "quat": [-0.612, 0.613, -0.353, 0.353] # xyzw
}

# 静态变换：Torso -> Head Right Camera
TF_TORSO_TO_HEAD_RIGHT = {
    "pos": [0.055, -0.034, 0.632],
    "quat": [-0.612, 0.613, -0.353, 0.353] # xyzw
}

# 静态变换：Left Gripper -> Left Wrist Camera (D405)
TF_LEFT_GRIPPER_TO_CAM = {
    "pos": [-0.019, 0.009, 0.075],
    "quat": [-0.641, 0.641, -0.299, 0.299] # xyzw
}

# 静态变换：Right Gripper -> Right Wrist Camera (D405)
TF_RIGHT_GRIPPER_TO_CAM = {
    "pos": [-0.019, 0.009, 0.075],
    "quat": [-0.641, 0.641, -0.299, 0.299] # xyzw
}

# ==========================================
# 2. 辅助函数 (Helper Functions)
# ==========================================

def get_matrix(pos, quat):
    """将位置和四元数(xyzw)转换为4x4齐次变换矩阵"""
    mat = np.eye(4)
    mat[:3, 3] = pos
    r = R.from_quat(quat)
    mat[:3, :3] = r.as_matrix()
    return mat

def get_pos_quat(matrix):
    """从4x4矩阵提取位置和四元数(xyzw)"""
    pos = matrix[:3, 3].tolist()
    r = R.from_matrix(matrix[:3, :3])
    quat = r.as_quat().tolist() # xyzw
    return pos, quat

# 预计算静态矩阵 (Pre-compute Static Matrices)
MAT_BASE_TO_TORSO = get_matrix(TF_BASE_TO_TORSO['pos'], TF_BASE_TO_TORSO['quat'])
MAT_TORSO_TO_HEAD_LEFT = get_matrix(TF_TORSO_TO_HEAD_LEFT['pos'], TF_TORSO_TO_HEAD_LEFT['quat'])
MAT_TORSO_TO_HEAD_RIGHT = get_matrix(TF_TORSO_TO_HEAD_RIGHT['pos'], TF_TORSO_TO_HEAD_RIGHT['quat'])
MAT_L_GRIP_TO_CAM = get_matrix(TF_LEFT_GRIPPER_TO_CAM['pos'], TF_LEFT_GRIPPER_TO_CAM['quat'])
MAT_R_GRIP_TO_CAM = get_matrix(TF_RIGHT_GRIPPER_TO_CAM['pos'], TF_RIGHT_GRIPPER_TO_CAM['quat'])

# ==========================================
# 3. 主处理逻辑 (Main Logic)
# ==========================================

def process_file(input_path, output_path, target_frame):
    """处理单个 parquet/json 文件，计算相机外参"""
    # 读取输入文件
    if input_path.endswith('.json'):
        df = pd.read_json(input_path)
    else:
        df = pd.read_parquet(input_path)

    results = []
    
    # 确定全局变换矩阵 (Transform Selector)
    # 如果目标是 base_link，我们需要将所有相对于 torso 的数据再左乘 T_base_to_torso
    # 如果目标是 torso_link3，数据保持原样 (单位矩阵)
    if target_frame == 'base_link':
        TRANSFORM_MAT = MAT_BASE_TO_TORSO
    else: # torso_link3
        TRANSFORM_MAT = np.eye(4)

    for index, row in df.iterrows():
        frame_data = {}
        
        # --- 1. 读取原始数据 (均在 Torso Frame 下) ---
        l_ee_pose_raw = row['observation.state.left_ee_pose']  # [x,y,z, qx,qy,qz,qw]
        r_ee_pose_raw = row['observation.state.right_ee_pose']
        
        # 转为矩阵 (Relative to Torso)
        mat_torso_to_l_grip = get_matrix(l_ee_pose_raw[:3], l_ee_pose_raw[3:])
        mat_torso_to_r_grip = get_matrix(r_ee_pose_raw[:3], r_ee_pose_raw[3:])
        
        # --- 2. 计算中间过程 (Relative to Torso) ---
        
        # 计算腕部相机 (Torso -> Grip -> Cam)
        mat_torso_to_l_wrist_cam = np.dot(mat_torso_to_l_grip, MAT_L_GRIP_TO_CAM)
        mat_torso_to_r_wrist_cam = np.dot(mat_torso_to_r_grip, MAT_R_GRIP_TO_CAM)
        
        # 头部相机 (Torso -> Head Cam) - 已经是静态已知的
        mat_torso_to_head_l = MAT_TORSO_TO_HEAD_LEFT
        mat_torso_to_head_r = MAT_TORSO_TO_HEAD_RIGHT

        # --- 3. 应用目标坐标系变换 (To Target Frame) ---
        # 公式: T_target_to_obj = T_target_to_torso * T_torso_to_obj
        
        # A. 计算最终 EE Pose
        mat_final_l_ee = np.dot(TRANSFORM_MAT, mat_torso_to_l_grip)
        mat_final_r_ee = np.dot(TRANSFORM_MAT, mat_torso_to_r_grip)

        # B. 计算最终相机 Pose
        mat_final_l_wrist_cam = np.dot(TRANSFORM_MAT, mat_torso_to_l_wrist_cam)
        mat_final_r_wrist_cam = np.dot(TRANSFORM_MAT, mat_torso_to_r_wrist_cam)
        mat_final_head_l_cam  = np.dot(TRANSFORM_MAT, mat_torso_to_head_l)
        mat_final_head_r_cam  = np.dot(TRANSFORM_MAT, mat_torso_to_head_r)

        # --- 4. 封装数据 ---
        
        def pack_pose(prefix, mat):
            p, q = get_pos_quat(mat)
            # 保存为平铺格式 [x,y,z, qx,qy,qz,qw] 方便绘图脚本直接使用
            frame_data[f'{prefix}_pose'] = p + q 
            # 也可以保留拆分格式
            frame_data[f'{prefix}_pos'] = p
            frame_data[f'{prefix}_quat'] = q
            frame_data[f'{prefix}_matrix'] = mat.tolist()

        # 保存 EE (覆盖原名或新建，这里为了可视化兼容建议保留原名结构或清晰的新名)
        # 注意：为了让 visualize_trajectory 能直接画出变换后的EE，我们通常需要更新 key
        # 这里我保存为标准 key，这样可视化脚本读取时就是变换后的数据
        pack_pose('left_ee', mat_final_l_ee)     # Output key: left_ee_pose
        pack_pose('right_ee', mat_final_r_ee)    # Output key: right_ee_pose
        
        # 保存相机
        pack_pose('cam_left_wrist', mat_final_l_wrist_cam)
        pack_pose('cam_right_wrist', mat_final_r_wrist_cam)
        pack_pose('cam_head_left', mat_final_head_l_cam)
        pack_pose('cam_head_right', mat_final_head_r_cam)

        # 保留时间戳
        if 'timestamp' in row:
            frame_data['timestamp'] = row['timestamp']
        
        results.append(frame_data)

    # --- 5. 输出 JSON ---
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=4)

    return len(results)

def process_dataset(dataset_path, target_frame, output_dir=None, visualize_episodes=None):
    """
    批量处理 LeRobot 数据集中的所有 episodes
    
    Args:
        dataset_path: LeRobot 数据集根目录路径
        target_frame: 目标坐标系 ('base_link' 或 'torso_link3')
        output_dir: 输出目录，默认为 dataset_path/camera_poses
        visualize_episodes: 要可视化的 episode 索引列表，None 表示不可视化
    """
    dataset_path = Path(dataset_path)
    
    # 检查数据集路径
    if not dataset_path.exists():
        raise ValueError(f"数据集路径不存在: {dataset_path}")
    
    data_dir = dataset_path / "data/chunk-000"
    if not data_dir.exists():
        raise ValueError(f"数据目录不存在: {data_dir}")
    
    # 查找所有 episode parquet 文件
    episode_files = sorted(data_dir.glob("episode_*.parquet"))
    
    if not episode_files:
        raise ValueError(f"未找到任何 episode parquet 文件: {data_dir}")
    
    print(f"找到 {len(episode_files)} 个 episodes")
    
    # 设置输出目录
    if output_dir is None:
        output_dir = dataset_path / "camera_poses"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {output_dir}")
    print(f"目标坐标系: {target_frame}\n")
    
    # 批量处理所有 episodes
    processed_files = []
    for episode_file in tqdm(episode_files, desc="处理 episodes"):
        episode_name = episode_file.stem  # e.g., "episode_000000"
        output_file = output_dir / f"{episode_name}_camera_poses_{target_frame}.json"
        
        try:
            num_frames = process_file(str(episode_file), str(output_file), target_frame)
            processed_files.append(str(output_file))
            tqdm.write(f"✓ {episode_name}: {num_frames} 帧 -> {output_file.name}")
        except Exception as e:
            tqdm.write(f"✗ {episode_name}: 处理失败 - {e}")
    
    print(f"\n处理完成！共处理 {len(processed_files)} 个文件")
    print(f"输出目录: {output_dir}")
    
    # 可视化指定的 episodes
    if visualize_episodes is not None and HAS_VISUALIZER:
        print(f"\n开始可视化 episodes: {visualize_episodes}")
        for ep_idx in visualize_episodes:
            episode_name = f"episode_{ep_idx:06d}"
            json_file = output_dir / f"{episode_name}_camera_poses_{target_frame}.json"
            
            if json_file.exists():
                print(f"\n可视化 {episode_name}...")
                visualize_trajectory.plot_animated_trajectories([str(json_file)], reference_frame=target_frame)
            else:
                print(f"警告: 未找到文件 {json_file}")
    
    return processed_files

# ==========================================
# 4. 程序入口 (Main Entry)
# ==========================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量计算 LeRobot 数据集中所有 episodes 的相机外参")
    
    parser.add_argument("--dataset", type=str, required=True, 
                        help="LeRobot 数据集根目录路径")
    parser.add_argument("--output", type=str, default=None,
                        help="输出目录路径，默认为 {dataset}/camera_poses")
    parser.add_argument("--frame", type=str, default="base_link", 
                        choices=["base_link", "torso_link3"],
                        help="目标参考坐标系：'base_link' (世界坐标) 或 'torso_link3' (躯干相对坐标)")
    
    # 可视化参数
    parser.add_argument("--visualize", nargs='*', type=int, metavar='EPISODE_IDX',
                        help="可视化指定的 episode 索引，例如: --visualize 0 1 2")

    args = parser.parse_args()

    # 执行批量处理
    processed_files = process_dataset(
        dataset_path=args.dataset,
        target_frame=args.frame,
        output_dir=args.output,
        visualize_episodes=args.visualize
    )

    print(f"\n✓ 所有处理完成！")
    print(f"  - 处理文件数: {len(processed_files)}")
    print(f"  - 坐标系: {args.frame}")



"""
使用示例:

# 处理整个数据集，输出到默认目录
python3 process_camera_poses_batch.py --dataset /path/to/lerobot/dataset --frame base_link

# 指定输出目录
python3 process_camera_poses_batch.py --dataset /path/to/lerobot/dataset --output /path/to/output --frame torso_link3

# 处理并可视化 episode 0 和 1
python3 process_camera_poses_batch.py --dataset /path/to/lerobot/dataset --frame base_link --visualize 0 1

# 实际使用案例
python3 /Users/psy/workspace/GalaxeaLeRobotToolkit/utils/process_camera_poses_batch.py \
    --dataset /Users/psy/workspace/data/lerobot/pick_3_bottles_and_place_them_into_trashbin/pick_3_bottles_and_place_them_into_trashbin \
    --frame base_link \
    --visualize 0
"""