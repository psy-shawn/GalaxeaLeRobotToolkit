import pandas as pd
import numpy as np
from scipy.spatial.transform import Rotation as R
import json
import argparse
import os

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
    print(f"正在读取: {input_path}")
    
    # 读取输入文件
    if input_path.endswith('.json'):
        df = pd.read_json(input_path)
    else:
        df = pd.read_parquet(input_path)

    results = []
    
    print(f"开始处理 {len(df)} 帧数据，目标坐标系: {target_frame}...")

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

    print(f"处理完成！文件已保存至: {output_path}")

# ==========================================
# 4. 程序入口 (Main Entry)
# ==========================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="计算相机外参并转换参考系 (Base/Torso)")
    
    parser.add_argument("--input", type=str, required=True, 
                        help="输入的 parquet 或 json 文件路径")
    parser.add_argument("--output", type=str, required=True, 
                        help="输出的 json 文件路径")
    parser.add_argument("--frame", type=str, default="base_link", 
                        choices=["base_link", "torso_link3"],
                        help="目标参考坐标系：'base_link' (世界坐标) 或 'torso_link3' (躯干相对坐标)")
    
    # 可视化参数
    parser.add_argument("--visualize", nargs='*',
                        help="是否运行可视化。可留空仅显示当前结果，或追加其他json文件进行对比。")

    args = parser.parse_args()

    # 强制检查输出后缀
    if not args.output.endswith('.json'):
        print("警告: 输出文件建议使用 .json 后缀。")

    # 执行主处理
    process_file(args.input, args.output, args.frame)

    # 执行可视化
    if args.visualize is not None:
        if not HAS_VISUALIZER:
            print("错误: 无法执行可视化，缺少 visualize_trajectory 模块。")
        else:
            files_to_plot = [args.output]
            # 如果用户传了额外的文件 (e.g. --visualize ground_truth.json)
            if len(args.visualize) > 0:
                files_to_plot.extend(args.visualize)
            
            print(f"\n启动可视化... 参考系: {args.frame}")
            print(f"加载文件列表: {files_to_plot}")
            
            # 调用可视化脚本
            # 注意：因为我们在 process_file 里已经把数据转换到了 args.frame 
            # 所以传给 visualizer 的 reference_frame 参数主要是为了图表标题，实际数据已经是正确的了
            visualize_trajectory.plot_animated_trajectories(files_to_plot, reference_frame=args.frame)



"""
python3 process_camera_poses.py --input episode_000000.parquet --output output_torso.json --frame torso_link3 --visualize

python3 process_camera_poses.py --input episode_000000.parquet --output with_cameraposes_base.json --frame base_link --visualize
"""