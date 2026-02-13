#!/usr/bin/env python3
"""
快速测试脚本：测试自动标注系统的各个组件
"""
import sys
import os
from pathlib import Path

# 添加当前目录到path
sys.path.insert(0, str(Path(__file__).parent))

from video_processor import VideoFrameExtractor, create_frame_grid
from vlm_annotator import VLMAnnotator
from data_updater import DatasetUpdater


def test_video_processor():
    """测试视频处理模块"""
    print("=" * 60)
    print("测试1: 视频处理模块")
    print("=" * 60)
    
    # 使用straighten_papercup数据集的第一个视频
    video_path = "/Users/psy/workspace/data/galaxea/lerobot/straighten_papercup/straighten_papercup/videos/chunk-000/observation.images.head_rgb/episode_000000.mp4"
    
    if not os.path.exists(video_path):
        print(f"❌ 测试视频不存在: {video_path}")
        return False
    
    try:
        extractor = VideoFrameExtractor(fps=1)
        frames = extractor.extract_frames(video_path)
        
        print(f"✓ 成功提取 {len(frames)} 帧")
        print(f"✓ 视频时长: {frames[-1][0]:.2f}秒")
        
        # 测试base64编码
        encoded = extractor.frames_to_base64_list(frames)
        print(f"✓ 成功编码 {len(encoded)} 帧")
        
        # 测试网格图创建
        timestamps, grid_base64 = create_frame_grid(encoded, grid_size=9)
        print(f"✓ 成功创建网格图，包含 {len(timestamps)} 个时间点")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_vlm_annotator():
    """测试VLM推理模块"""
    print("\n" + "=" * 60)
    print("测试2: VLM推理模块")
    print("=" * 60)
    
    try:
        annotator = VLMAnnotator()
        print("✓ VLM标注器初始化成功")
        
        # 测试提示词
        print(f"✓ 系统提示词长度: {len(annotator.SYSTEM_PROMPT)} 字符")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_data_updater():
    """测试数据更新模块"""
    print("\n" + "=" * 60)
    print("测试3: 数据更新模块")
    print("=" * 60)
    
    dataset_dir = "/Users/psy/workspace/data/galaxea/lerobot/straighten_papercup"
    
    if not os.path.exists(dataset_dir):
        print(f"❌ 数据集目录不存在: {dataset_dir}")
        return False
    
    try:
        updater = DatasetUpdater(dataset_dir)
        print(f"✓ 数据更新器初始化成功")
        
        # 测试加载episodes
        episodes = updater.load_episodes()
        print(f"✓ 成功加载 {len(episodes)} 个episodes")
        
        # 显示前3个episodes
        for i, ep in enumerate(episodes[:3]):
            print(f"  Episode {ep.get('episode_index')}: {len(ep.get('tasks', []))} tasks, length={ep.get('length')}")
        
        # 测试加载meta
        meta = updater.load_meta()
        print(f"✓ 成功加载meta数据")
        print(f"  原始数据集: {meta.get('rawDataSetName')}")
        print(f"  原始数据数量: {len(meta.get('rawDataList', []))}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_full_pipeline():
    """测试完整流程（不调用API）"""
    print("\n" + "=" * 60)
    print("测试4: 完整流程（模拟）")
    print("=" * 60)
    
    video_path = "/Users/psy/workspace/data/galaxea/lerobot/straighten_papercup/straighten_papercup/videos/chunk-000/observation.images.head_rgb/episode_000000.mp4"
    dataset_dir = "/Users/psy/workspace/data/galaxea/lerobot/straighten_papercup"
    
    if not os.path.exists(video_path):
        print(f"❌ 测试视频不存在: {video_path}")
        return False
    
    try:
        # 步骤1: 视频处理
        print("步骤1: 处理视频...")
        extractor = VideoFrameExtractor(fps=1)
        encoded_frames = extractor.process_video(video_path)
        print(f"✓ 提取了 {len(encoded_frames)} 帧")
        
        # 步骤2: 创建网格图
        print("\n步骤2: 创建网格图...")
        timestamps, grid_base64 = create_frame_grid(encoded_frames, grid_size=9)
        print(f"✓ 网格图包含 {len(timestamps)} 个关键帧")
        print(f"✓ Base64长度: {len(grid_base64)} 字符")
        
        # 步骤3: 模拟VLM结果
        print("\n步骤3: 模拟VLM标注结果...")
        mock_result = {
            "actions": [
                {
                    "start_time": 0.0,
                    "end_time": 8.0,
                    "description": "双臂配合将左侧的抱枕立起来",
                    "description_en": "Both arms coordinate to stand up the left cushion"
                },
                {
                    "start_time": 8.0,
                    "end_time": 15.0,
                    "description": "双臂配合将中间的抱枕立起来",
                    "description_en": "Both arms coordinate to stand up the center cushion"
                }
            ],
            "task_summary": "整理沙发抱枕",
            "task_summary_en": "Arrange sofa cushions"
        }
        print(f"✓ 模拟了 {len(mock_result['actions'])} 个动作")
        
        # 步骤4: 数据格式转换（不实际写入）
        print("\n步骤4: 测试数据格式转换...")
        updater = DatasetUpdater(dataset_dir)
        
        # 构建tasks列表
        tasks = []
        for action in mock_result['actions']:
            desc_cn = action.get('description', '')
            desc_en = action.get('description_en', '')
            if desc_cn and desc_en:
                tasks.append(f"{desc_cn}@{desc_en}")
        
        print(f"✓ 生成了 {len(tasks)} 个tasks")
        for i, task in enumerate(tasks, 1):
            print(f"  {i}. {task.split('@')[0][:40]}...")
        
        # 构建annotations
        annotations = []
        for action in mock_result['actions']:
            start_time = action.get('start_time', 0)
            end_time = action.get('end_time', 0)
            description = action.get('description', '')
            
            annotation = {
                "startSecond": int(start_time),
                "startNanoSecond": int((start_time - int(start_time)) * 1e9),
                "endSecond": int(end_time),
                "endNanoSecond": int((end_time - int(end_time)) * 1e9),
                "text": description,
                "annotatedDuration": int(end_time - start_time)
            }
            annotations.append(annotation)
        
        print(f"✓ 生成了 {len(annotations)} 个annotations")
        
        print("\n✓ 完整流程测试成功（未实际写入数据）")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("自动标注系统测试")
    print("=" * 60 + "\n")
    
    results = []
    
    # 运行各项测试
    results.append(("视频处理", test_video_processor()))
    results.append(("VLM推理", test_vlm_annotator()))
    results.append(("数据更新", test_data_updater()))
    results.append(("完整流程", test_full_pipeline()))
    
    # 输出总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    for name, success in results:
        status = "✓ 通过" if success else "✗ 失败"
        print(f"{name}: {status}")
    
    total = len(results)
    passed = sum(1 for _, s in results if s)
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！系统已就绪。")
        print("\n下一步：运行以下命令测试单个episode的实际标注：")
        print("python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/straighten_papercup --single 0")
    else:
        print("\n⚠️  部分测试失败，请检查配置和依赖。")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
