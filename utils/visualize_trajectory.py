#!/usr/bin/env python3
import json
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.animation as animation
import argparse
import os
import numpy as np
import pandas as pd

# 轨迹样式配置
STYLES = {
    'cam_left_wrist': {'color': 'blue', 'linestyle': '-', 'label': 'L-Wrist Cam'},
    'cam_right_wrist': {'color': 'green', 'linestyle': '-', 'label': 'R-Wrist Cam'},
    'cam_head_left': {'color': 'red', 'linestyle': '--', 'label': 'Head-L Cam'},
    'cam_head_right': {'color': 'orange', 'linestyle': '--', 'label': 'Head-R Cam'},
    'left_ee': {'color': 'navy', 'linestyle': ':', 'marker': 'o', 'label': 'L-End Effector'},
    'right_ee': {'color': 'darkgreen', 'linestyle': ':', 'marker': 's', 'label': 'R-End Effector'},
    'default': {'color': 'gray', 'linestyle': '-', 'marker': None}
}

def load_data(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.parquet':
        return pd.read_parquet(file_path).to_dict(orient='records')
    with open(file_path, 'r') as f:
        return json.load(f)

def extract_trajectories(data):
    trajs = {}
    if not data: return trajs
    sample = data[0]
    keys_to_extract = [k for k in sample.keys() if k.endswith('_pos')]
    if 'left_ee_pose' in sample: keys_to_extract.append('left_ee_pose')
    if 'right_ee_pose' in sample: keys_to_extract.append('right_ee_pose')

    for key in keys_to_extract:
        points = []
        for frame in data:
            val = frame.get(key)
            if val and len(val) >= 3:
                points.append(val[:3])
        if points:
            clean_name = key.replace('_pos', '').replace('_pose', '')
            trajs[clean_name] = np.array(points)
    return trajs

def setup_3d_axes(ax, trajs, title):
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_zlabel('Z (m)')
    ax.set_title(title)
    
    all_points = np.vstack(list(trajs.values()))
    max_range = (all_points.max(axis=0) - all_points.min(axis=0)).max() / 2.0
    mid_point = (all_points.max(axis=0) + all_points.min(axis=0)) / 2.0
    
    ax.set_xlim(mid_point[0] - max_range, mid_point[0] + max_range)
    ax.set_ylim(mid_point[1] - max_range, mid_point[1] + max_range)
    ax.set_zlim(mid_point[2] - max_range, mid_point[2] + max_range)

def plot_animated_trajectories(file_paths, reference_frame="Unknown"):
    if isinstance(file_paths, str):
        file_paths = [file_paths]

    all_source_trajs = {}
    max_len = 0
    
    for path in file_paths:
        data = load_data(path)
        trajs = extract_trajectories(data)
        source_name = os.path.basename(path)
        all_source_trajs[source_name] = trajs
        for t in trajs.values():
            max_len = max(max_len, len(t))

    if max_len == 0:
        print("错误: 未找到有效轨迹数据。")
        return

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    # 获取所有点的集合用于初始化坐标轴
    combined_trajs = {f"{s}_{k}": v for s, d in all_source_trajs.items() for k, v in d.items()}
    setup_3d_axes(ax, combined_trajs, f"Robot Trajectory Real-time (Ref: {reference_frame})")

    # 初始化绘图对象
    plot_elements = []
    for source, trajs in all_source_trajs.items():
        for name, coords in trajs.items():
            style = STYLES.get(name, STYLES['default'])
            line, = ax.plot([], [], [], 
                            color=style['color'], 
                            linestyle=style['linestyle'],
                            label=f"{style.get('label', name)}")
            point, = ax.plot([], [], [], 
                             color=style['color'], 
                             marker=style.get('marker', 'o'), 
                             markersize=6)
            plot_elements.append({
                'line': line, 
                'point': point, 
                'coords': coords, 
                'name': style.get('label', name),
                'color': style['color']
            })

    ax.legend(loc='upper left', fontsize='small')
    
    # 【核心新增】在右上方创建一个信息文本框
    # 使用 ax.text2D 并设置 transform=ax.transAxes 锁定在窗口右上角
    stats_text = ax.text2D(0.95, 0.95, "", transform=ax.transAxes, 
                           fontsize=10, fontfamily='monospace',
                           verticalalignment='top', horizontalalignment='right',
                           bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.8, edgecolor='gray'))

    state = {'paused': False, 'frame': 0}

    def update(n):
        if not state['paused']:
            state['frame'] = n % max_len
        
        curr = state['frame']
        
        # 实时坐标信息列表
        info_lines = [f"FRAME: {curr:04d}", "-" * 20]
        
        for el in plot_elements:
            c = el['coords']
            idx = min(curr, len(c) - 1)
            
            # 更新 3D 绘图
            el['line'].set_data(c[:idx+1, 0], c[:idx+1, 1])
            el['line'].set_3d_properties(c[:idx+1, 2])
            el['point'].set_data([c[idx, 0]], [c[idx, 1]])
            el['point'].set_3d_properties([c[idx, 2]])
            
            # 格式化实时 XYZ 字符串
            x, y, z = c[idx]
            info_lines.append(f"{el['name'][:12]:<12}: {x:>6.3f}, {y:>6.3f}, {z:>6.3f}")
        
        # 更新右上角文字
        stats_text.set_text("\n".join(info_lines))
        
        return [el['line'] for el in plot_elements] + [el['point'] for el in plot_elements] + [stats_text]

    def on_keypress(event):
        if event.key == ' ':
            state['paused'] = not state['paused']
        elif event.key.lower() == 'r':
            state['frame'] = 0
        elif event.key.lower() == 's':
            save_path = "trajectory_output.gif"
            print(f"正在保存 GIF...")
            ani.save(save_path, writer='pillow', fps=20)
            print(f"保存成功: {save_path}")

    fig.canvas.mpl_connect('key_press_event', on_keypress)
    ani = animation.FuncAnimation(fig, update, frames=max_len, interval=50, blit=False)
    
    plt.tight_layout()
    plt.show()
def main():
    parser = argparse.ArgumentParser(description="Visualize 3D trajectories")
    parser.add_argument('files', nargs='+', help="Input files (JSON or parquet)")
    parser.add_argument('--frame', type=str, default="base_link", help="Reference frame")
    
    # --- ADD THESE THREE ARGUMENTS ---
    parser.add_argument('--save-gif', type=str, default=None, help="Save path for GIF")
    parser.add_argument('--fps', type=int, default=15, help="FPS for GIF")
    parser.add_argument('--animate', action='store_true', default=True, help="Animate plot")
    # ---------------------------------

    args = parser.parse_args()
    
    all_poses = {}
    for file_path in args.files:
        if not os.path.exists(file_path):
            continue
        source_name = os.path.basename(file_path).replace('.json', '').replace('.parquet', '')
        poses = extract_trajectories(load_data(file_path))
        if poses:
            all_poses[source_name] = poses

    if not all_poses:
        print("No valid data.")
        return

    # LOGIC TO HANDLE GIF SAVING WITHOUT GUI
    if args.save_gif:
        print(f"Saving GIF to {args.save_gif}...")
        # Call the existing save_gif function if you have it, 
        # or a modified version of plot_animated_trajectories
        save_trajectory_as_gif(all_poses, args.frame, args.save_gif, args.fps)
    else:
        plot_animated_trajectories(args.files, args.frame)

# ADD THIS HELPER FUNCTION if it's missing to handle the save
def save_trajectory_as_gif(all_poses, reference_frame, output_path, fps):
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    combined_trajs = {f"{s}_{k}": v for s, d in all_poses.items() for k, v in d.items()}
    setup_3d_axes(ax, combined_trajs, f"Saving Trajectory: {reference_frame}")

    plot_elements = []
    max_len = 0
    for source, trajs in all_poses.items():
        for name, coords in trajs.items():
            style = STYLES.get(name, STYLES['default'])
            line, = ax.plot([], [], [], color=style['color'], linestyle=style['linestyle'])
            point, = ax.plot([], [], [], color=style['color'], marker='o')
            plot_elements.append({'line': line, 'point': point, 'coords': coords})
            max_len = max(max_len, len(coords))

    def update(n):
        artists = []
        for el in plot_elements:
            c = el['coords']
            idx = min(n, len(c) - 1)
            el['line'].set_data(c[:idx+1, 0], c[:idx+1, 1])
            el['line'].set_3d_properties(c[:idx+1, 2])
            el['point'].set_data([c[idx, 0]], [c[idx, 1]])
            el['point'].set_3d_properties([c[idx, 2]])
            artists.extend([el['line'], el['point']])
        return artists

    ani = animation.FuncAnimation(fig, update, frames=max_len, interval=1000/fps, blit=False)
    ani.save(output_path, writer='pillow', fps=fps)
    plt.close(fig) # Important: close the figure to free memory


if __name__ == "__main__":
    main()

"""
# 查看相对于 base_link 的轨迹
python3 visualize_trajectory.py output_base.json --frame base_link

# 同时对比两个文件的轨迹
python3 visualize_trajectory.py output_base.json output_torso.json
"""