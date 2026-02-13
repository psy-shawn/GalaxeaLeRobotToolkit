"""
自动化数据标注主程序
负责协调视频处理、VLM推理和数据更新的完整流程
"""
import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
import time
from tqdm import tqdm

from video_processor import VideoFrameExtractor
from vlm_annotator import VLMAnnotator
from data_updater import DatasetUpdater


class AutoAnnotator:
    """自动标注器"""
    
    def __init__(
        self,
        dataset_dir: str,
        api_url: str = None,
        api_token: str = None,
        fps: int = 1,
        use_grid: bool = True,
        max_episodes: int = None
    ):
        """
        初始化自动标注器
        
        Args:
            dataset_dir: 数据集根目录
            api_url: VLM API地址
            api_token: API token
            fps: 视频抽帧帧率
            use_grid: 是否使用网格图模式
            max_episodes: 最大处理episode数（None表示全部）
        """
        self.dataset_dir = Path(dataset_dir)
        self.dataset_name = self.dataset_dir.name
        
        # 初始化各个模块
        self.video_extractor = VideoFrameExtractor(fps=fps)
        
        kwargs = {}
        if api_url:
            kwargs['api_url'] = api_url
        if api_token:
            kwargs['api_token'] = api_token
        self.vlm_annotator = VLMAnnotator(**kwargs)
        
        self.data_updater = DatasetUpdater(dataset_dir)
        
        self.use_grid = use_grid
        self.max_episodes = max_episodes
        
        # 视频文件目录
        self.video_base_dir = self.dataset_dir / self.dataset_name / "videos" / "chunk-000" / "observation.images.head_rgb"
        
        if not self.video_base_dir.exists():
            raise FileNotFoundError(f"视频目录不存在: {self.video_base_dir}")
    
    def find_video_files(self) -> List[Path]:
        """查找所有视频文件"""
        video_files = sorted(self.video_base_dir.glob("episode_*.mp4"))
        
        if self.max_episodes is not None:
            video_files = video_files[:self.max_episodes]
        
        print(f"找到 {len(video_files)} 个视频文件")
        return video_files
    
    def get_episode_index(self, video_path: Path) -> int:
        """从视频文件名提取episode索引"""
        # episode_000000.mp4 -> 0
        filename = video_path.stem  # episode_000000
        index_str = filename.split('_')[-1]  # 000000
        return int(index_str)
    
    def get_episode_info(self, episode_index: int) -> Dict:
        """获取episode的额外信息（如任务描述）"""
        episodes = self.data_updater.load_episodes()
        
        for episode in episodes:
            if episode.get('episode_index') == episode_index:
                return episode
        
        return {}
    
    def annotate_single_video(
        self,
        video_path: Path,
        save_result: bool = True
    ) -> Dict[str, Any]:
        """
        标注单个视频
        
        Args:
            video_path: 视频文件路径
            save_result: 是否立即保存结果
            
        Returns:
            标注结果字典
        """
        episode_index = self.get_episode_index(video_path)
        episode_info = self.get_episode_info(episode_index)
        
        print(f"\n{'='*60}")
        print(f"处理 Episode {episode_index}: {video_path.name}")
        print(f"当前任务: {episode_info.get('tasks', ['未知'])[0] if episode_info.get('tasks') else '未知'}")
        print(f"{'='*60}\n")
        
        # 步骤1: 视频抽帧
        print("步骤1: 视频抽帧...")
        encoded_frames = self.video_extractor.process_video(str(video_path))
        
        if not encoded_frames:
            print("错误: 未能提取到任何帧")
            return None
        
        video_duration = encoded_frames[-1][0]  # 最后一帧的时间戳
        print(f"视频时长: {video_duration:.2f}秒")
        
        # 步骤2: VLM推理
        print("\n步骤2: VLM推理...")
        vlm_result = self.vlm_annotator.annotate_video_frames(
            encoded_frames,
            episode_info=episode_info,
            use_grid=self.use_grid
        )
        
        if 'error' in vlm_result:
            print(f"VLM推理出错: {vlm_result['error']}")
            return None
        
        # 打印结果
        print(f"\n标注结果:")
        print(f"任务总结: {vlm_result.get('task_summary', 'N/A')}")
        print(f"识别到 {len(vlm_result.get('actions', []))} 个动作:")
        for i, action in enumerate(vlm_result.get('actions', []), 1):
            print(f"  {i}. [{action.get('start_time', 0):.1f}s - {action.get('end_time', 0):.1f}s] {action.get('description', '')}")
        
        # 步骤3: 更新数据
        if save_result:
            print("\n步骤3: 更新数据集...")
            # 如果是单个视频处理，先备份原始文件
            self.data_updater.backup_original_files()
            
            raw_file_name = episode_info.get('raw_file_name')
            success = self.data_updater.update_episode_full(
                episode_index,
                vlm_result,
                video_duration,
                raw_file_name
            )
            
            if success:
                print("✓ 数据更新成功")
            else:
                print("✗ 数据更新失败")
        
        return {
            'episode_index': episode_index,
            'vlm_result': vlm_result,
            'video_duration': video_duration,
            'raw_file_name': episode_info.get('raw_file_name')
        }
    
    def annotate_all_videos(self, start_index: int = 0):
        """
        标注所有视频
        
        Args:
            start_index: 从第几个视频开始（用于断点续传）
        """
        video_files = self.find_video_files()
        
        if start_index > 0:
            video_files = video_files[start_index:]
            print(f"从第 {start_index} 个视频开始处理")
        
        # 在开始处理前备份原始文件
        print("正在备份原始数据文件...")
        self.data_updater.backup_original_files()
        
        results = []
        failed_episodes = []
        
        for i, video_path in enumerate(tqdm(video_files, desc="处理视频")):
            try:
                result = self.annotate_single_video(video_path, save_result=True)
                
                if result:
                    results.append(result)
                else:
                    failed_episodes.append(self.get_episode_index(video_path))
                
                # 添加延迟以避免API限流
                if i < len(video_files) - 1:
                    time.sleep(1)
                    
            except Exception as e:
                episode_index = self.get_episode_index(video_path)
                print(f"\n错误: Episode {episode_index} 处理失败: {str(e)}")
                failed_episodes.append(episode_index)
                continue
        
        # 输出总结
        print(f"\n{'='*60}")
        print(f"处理完成!")
        print(f"成功: {len(results)}/{len(video_files)}")
        if failed_episodes:
            print(f"失败的episodes: {failed_episodes}")
        print(f"{'='*60}")
        
        return results, failed_episodes
    
    def export_results(self, results: List[Dict], output_file: str):
        """导出标注结果到JSON文件"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"结果已导出到: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="自动化机器人数据标注工具")
    parser.add_argument(
        "dataset_dir",
        type=str,
        help="数据集目录路径，如 /path/to/straighten_papercup"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="VLM API地址（可选，默认使用配置）"
    )
    parser.add_argument(
        "--api-token",
        type=str,
        default=None,
        help="API Token（可选，默认使用配置）"
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=1,
        help="视频抽帧帧率（默认1fps）"
    )
    parser.add_argument(
        "--no-grid",
        action="store_true",
        help="不使用网格图模式（成本较高）"
    )
    parser.add_argument(
        "--max-episodes",
        type=int,
        default=None,
        help="最大处理episode数量（用于测试）"
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="从第几个视频开始处理（断点续传）"
    )
    parser.add_argument(
        "--single",
        type=int,
        default=None,
        help="只处理指定的episode索引"
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="导出结果到指定JSON文件"
    )
    
    args = parser.parse_args()
    
    # 创建自动标注器
    annotator = AutoAnnotator(
        dataset_dir=args.dataset_dir,
        api_url=args.api_url,
        api_token=args.api_token,
        fps=args.fps,
        use_grid=not args.no_grid,
        max_episodes=args.max_episodes
    )
    
    # 执行标注
    if args.single is not None:
        # 单个episode模式
        video_files = annotator.find_video_files()
        target_video = None
        for video_file in video_files:
            if annotator.get_episode_index(video_file) == args.single:
                target_video = video_file
                break
        
        if target_video:
            result = annotator.annotate_single_video(target_video, save_result=True)
            if args.export and result:
                annotator.export_results([result], args.export)
        else:
            print(f"错误: 未找到 episode {args.single}")
    else:
        # 批量处理模式
        results, failed = annotator.annotate_all_videos(start_index=args.start_index)
        
        if args.export:
            annotator.export_results(results, args.export)


if __name__ == "__main__":
    main()
