import streamlit as st
import json
import os
import subprocess
from pathlib import Path

# ==========================================
# 1. 配置参数
# ==========================================
PROCESS_SCRIPT = "/Users/psy/workspace/GalaxeaLeRobotToolkit/utils/process_camera_poses.py"
VIS_SCRIPT = "/Users/psy/workspace/GalaxeaLeRobotToolkit/utils/visualize_trajectory.py"

st.set_page_config(layout="wide", page_title="Robot Data Inspector")

# ==========================================
# 2. 视频加载与扫描函数
# ==========================================

def get_video_binary(file_path):
    """直接读取视频二进制流，解决路径解析导致的黑屏问题"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                return f.read()
        return None
    except Exception:
        return None

def scan_directory(root_dir):
    """针对你的目录结构进行深度扫描"""
    root = Path(root_dir)
    if not root.exists():
        return None, None, None

    internal_cams = {
        "Head RGB": None, "Head Right": None, 
        "Left Wrist": None, "Right Wrist": None
    }
    ext_rgb = {}
    ext_depth = {}

    # 递归查找所有 mp4
    all_files = list(root.rglob("*.mp4"))

    for path in all_files:
        p_str = str(path)
        name = path.name
        parent_name = path.parent.name

        # 匹配内部相机 (视频位于 observation.images... 目录下)
        if "observation.images.head_rgb" in p_str:
            internal_cams["Head RGB"] = p_str
        elif "observation.images.head_right_rgb" in p_str:
            internal_cams["Head Right"] = p_str
        elif "observation.images.left_wrist_rgb" in p_str:
            internal_cams["Left Wrist"] = p_str
        elif "observation.images.right_wrist_rgb" in p_str:
            internal_cams["Right Wrist"] = p_str

        # 匹配外部相机 (新结构: observation.images.external_xxx)
        elif "observation.images.external_" in p_str:
            if "external_top_rgb" in p_str:
                ext_rgb["external_top"] = p_str
            elif "external_left_rgb" in p_str:
                ext_rgb["external_left"] = p_str
            elif "external_top_depth" in p_str:
                ext_depth["external_top"] = p_str
            elif "external_left_depth" in p_str:
                ext_depth["external_left"] = p_str

    # 寻找数据文件
    parquets = list(root.rglob("*.parquet"))
    target_parquet = str(parquets[0]) if parquets else None

    return internal_cams, {"rgb": ext_rgb, "depth": ext_depth}, target_parquet

# ==========================================
# 3. 主界面
# ==========================================

st.sidebar.header("📂 路径配置")
# 默认路径使用你提供的最新路径
default_path = "/Users/hsong/repos/scripts/recordings/pick_3_bottles_and_place_them_into_trashbin/right_arm_to_left_arm/order_tall_mid_low/20260203_215226"
target_dir = st.sidebar.text_input("Episode Root Path:", value=default_path)

if target_dir and os.path.exists(target_dir):
    internal, external, parquet_file = scan_directory(target_dir)

    st.subheader(f"🎬 当前序列: {Path(target_dir).name}")

    # --- 第一排：内部相机 ---
    st.markdown("### 🤖 内部相机 (Internal)")
    it_cols = st.columns(4)
    it_labels = ["Head RGB", "Head Right", "Left Wrist", "Right Wrist"]
    for i, label in enumerate(it_labels):
        with it_cols[i]:
            path = internal.get(label)
            if path:
                # 使用二进制加载
                vid_bin = get_video_binary(path)
                st.video(vid_bin, autoplay=True, muted=True, loop=True)
                st.caption(f"✅ {label}")
            else:
                st.error(f"缺失: {label}")

    st.divider()

    # --- 第二排：外部相机 ---
    st.markdown("### 📹 外部视角 (External)")
    cam_ids = sorted(external["rgb"].keys())

    if not cam_ids:
        st.warning("未检测到外部相机文件 (observation.images.external_*)")
    else:
        for cid in cam_ids:
            c1, c2 = st.columns(2)
            with c1:
                rgb_p = external["rgb"].get(cid)
                if rgb_p:
                    # 使用二进制加载强制浏览器渲染
                    v_rgb = get_video_binary(rgb_p)
                    st.video(v_rgb, autoplay=True, muted=True, loop=True)
                    st.caption(f"🎥 {cid} - RGB (aligned)")
            with c2:
                dep_p = external["depth"].get(cid)
                if dep_p:
                    v_dep = get_video_binary(dep_p)
                    st.video(v_dep, autoplay=True, muted=True, loop=True)
                    st.caption(f"🕳️ {cid} - Depth (aligned)")

    # --- 第三排：轨迹与标注 ---
    st.divider()
    col_traj, col_anno = st.columns([1.5, 1])

    with col_traj:
        st.markdown("### 📈 3D 轨迹")
        if parquet_file:
            if st.button("🚀 生成/刷新轨迹 GIF"):
                with st.spinner("正在运行可视化脚本..."):
                    # 运行脚本
                    ep_id = Path(target_dir).name
                    out_json = f"processed_{ep_id}.json"
                    out_gif = f"traj_{ep_id}.gif"
                    try:
                        subprocess.run(["python3", PROCESS_SCRIPT, "--input", parquet_file, "--output", out_json, "--frame", "base_link"], check=True)
                        subprocess.run(["python3", VIS_SCRIPT, out_json, "--save-gif", out_gif, "--fps", "20"], check=True)
                        st.session_state.current_gif = out_gif
                    except Exception as e:
                        st.error(f"生成失败: {e}")

            if 'current_gif' in st.session_state and os.path.exists(st.session_state.current_gif):
                # 修复 width 报错
                st.image(st.session_state.current_gif, use_container_width=True)
        else:
            st.info("未找到 parquet 文件")

    with col_anno:
        st.markdown("### 📝 质检")
        q_res = st.radio("结论:", ["合格", "不合格"], horizontal=True)
        q_note = st.text_area("备注:")
        if st.button("💾 保存数据"):
            res_path = Path(target_dir) / "quality_annotation.json"
            with open(res_path, 'w') as f:
                json.dump({"status": q_res, "note": q_note}, f, indent=4)
            st.success("已保存")

else:
    st.info("请输入合法的文件夹路径以开始。")
# streamlit run /Users/psy/workspace/GalaxeaLeRobotToolkit/utils/app_visualize.py