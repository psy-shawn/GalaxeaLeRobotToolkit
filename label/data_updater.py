"""
数据更新模块：负责将VLM标注结果写入到episodes.jsonl和training_data_set_meta.json
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any
import time


class DatasetUpdater:
    """数据集更新器"""
    
    def __init__(self, dataset_dir: str):
        """
        初始化数据集更新器
        
        Args:
            dataset_dir: 数据集根目录，如 /path/to/straighten_papercup
        """
        self.dataset_dir = Path(dataset_dir)
        self.dataset_name = self.dataset_dir.name
        
        # 关键文件路径
        self.episodes_file = self.dataset_dir / self.dataset_name / "meta" / "episodes.jsonl"
        self.meta_file = self.dataset_dir / "training_data_set_meta.json"
        
        # 备份标记，确保只备份一次
        self._backup_done = False
        
        # 确保文件存在
        if not self.episodes_file.exists():
            print(f"警告: episodes.jsonl 不存在: {self.episodes_file}")
        if not self.meta_file.exists():
            print(f"警告: training_data_set_meta.json 不存在: {self.meta_file}")
    
    def load_episodes(self) -> List[Dict]:
        """加载episodes.jsonl文件"""
        episodes = []
        if self.episodes_file.exists():
            with open(self.episodes_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        episodes.append(json.loads(line))
        return episodes
    
    def load_meta(self) -> Dict:
        """加载training_data_set_meta.json文件"""
        if self.meta_file.exists():
            with open(self.meta_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def backup_original_files(self):
        """
        备份原始文件（仅在首次调用时执行）
        应该在开始批处理之前调用一次
        """
        if self._backup_done:
            return
        
        import shutil
        backup_time = time.strftime("%Y%m%d_%H%M%S")
        
        # 备份episodes.jsonl
        if self.episodes_file.exists():
            backup_file = self.episodes_file.with_suffix(f'.jsonl.bak_{backup_time}')
            shutil.copy2(self.episodes_file, backup_file)
            print(f"✓ 已备份原始episodes文件到: {backup_file}")
        
        # 备份training_data_set_meta.json
        if self.meta_file.exists():
            backup_file = self.meta_file.with_suffix(f'.json.bak_{backup_time}')
            shutil.copy2(self.meta_file, backup_file)
            print(f"✓ 已备份原始meta文件到: {backup_file}")
        
        self._backup_done = True
        print()
    
    def save_episodes(self, episodes: List[Dict], backup: bool = False):
        """
        保存episodes.jsonl文件
        
        Args:
            episodes: episode列表
            backup: 是否备份原文件（不推荐使用，应使用backup_original_files）
        """
        if backup and self.episodes_file.exists():
            backup_file = self.episodes_file.with_suffix('.jsonl.bak')
            import shutil
            shutil.copy2(self.episodes_file, backup_file)
            print(f"已备份原文件到: {backup_file}")
        
        # 确保目录存在
        self.episodes_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.episodes_file, 'w', encoding='utf-8') as f:
            for episode in episodes:
                f.write(json.dumps(episode, ensure_ascii=False) + '\n')
        
        print(f"已保存 {len(episodes)} 个episodes到: {self.episodes_file}")
    
    def save_meta(self, meta: Dict, backup: bool = False):
        """
        保存training_data_set_meta.json文件
        
        Args:
            meta: 元数据字典
            backup: 是否备份原文件（不推荐使用，应使用backup_original_files）
        """
        if backup and self.meta_file.exists():
            backup_file = self.meta_file.with_suffix('.json.bak')
            import shutil
            shutil.copy2(self.meta_file, backup_file)
            print(f"已备份原文件到: {backup_file}")
        
        # 确保目录存在
        self.meta_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.meta_file, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=4)
        
        print(f"已保存meta数据到: {self.meta_file}")
    
    def update_episode_tasks(
        self,
        episode_index: int,
        vlm_result: Dict[str, Any],
        video_duration: float
    ) -> bool:
        """
        更新单个episode的tasks字段
        
        Args:
            episode_index: episode索引
            vlm_result: VLM标注结果
            video_duration: 视频时长（秒）
            
        Returns:
            是否成功更新
        """
        episodes = self.load_episodes()
        
        # 查找对应的episode
        target_episode = None
        for episode in episodes:
            if episode.get('episode_index') == episode_index:
                target_episode = episode
                break
        
        if target_episode is None:
            print(f"错误: 未找到 episode_index={episode_index}")
            return False
        
        # 构建tasks列表
        tasks = []
        
        # 添加每个动作的中英文描述（不包括任务总结）
        for action in vlm_result.get('actions', []):
            desc_cn = action.get('description', '')
            desc_en = action.get('description_en', '')
            if desc_cn and desc_en:
                tasks.append(f"{desc_cn}@{desc_en}")
            elif desc_cn:
                tasks.append(desc_cn)
        
        # 更新tasks
        target_episode['tasks'] = tasks
        
        # 保存（不备份，应在任务开始前统一备份）
        self.save_episodes(episodes, backup=False)
        print(f"已更新 episode {episode_index} 的tasks字段，共 {len(tasks)} 个任务")
        
        return True
    
    def update_meta_annotations(
        self,
        episode_index: int,
        vlm_result: Dict[str, Any],
        raw_file_name: str = None
    ) -> bool:
        """
        更新training_data_set_meta.json中对应原始数据的annotations
        
        Args:
            episode_index: episode索引
            vlm_result: VLM标注结果
            raw_file_name: 原始文件名（用于匹配rawDataList中的项）
            
        Returns:
            是否成功更新
        """
        meta = self.load_meta()
        
        if 'rawDataList' not in meta:
            print("错误: meta文件中没有rawDataList字段")
            return False
        
        # 方法1: 直接使用episode_index作为rawDataList的索引（推荐）
        # episode 0 对应 rawDataList[0]，episode 1 对应 rawDataList[1]，以此类推
        target_raw_data = None
        
        if episode_index < len(meta['rawDataList']):
            target_raw_data = meta['rawDataList'][episode_index]
            print(f"使用索引匹配: episode {episode_index} -> rawDataList[{episode_index}] ({target_raw_data.get('name', 'unknown')})")
        else:
            # 方法2: 如果索引超出范围，尝试使用raw_file_name匹配
            print(f"警告: episode_index={episode_index} 超出 rawDataList 范围 (长度={len(meta['rawDataList'])})")
            
            if raw_file_name is None:
                # 尝试从episodes中获取raw_file_name
                episodes = self.load_episodes()
                for episode in episodes:
                    if episode.get('episode_index') == episode_index:
                        raw_file_name = episode.get('raw_file_name')
                        break
            
            if raw_file_name:
                # 使用文件名匹配
                for raw_data in meta['rawDataList']:
                    if raw_data.get('name') == raw_file_name:
                        target_raw_data = raw_data
                        print(f"使用文件名匹配: {raw_file_name}")
                        break
        
        if target_raw_data is None:
            print(f"错误: 无法找到 episode {episode_index} 对应的rawData")
            return False
        
        # 获取原始的基准时间和质量标签
        base_second = 0
        base_nanosecond = 0
        action_quality_label = "qualified"  # 默认值
        
        # 如果已有annotations，使用第一个作为基准时间
        if target_raw_data.get('annotations') and len(target_raw_data['annotations']) > 0:
            first_annotation = target_raw_data['annotations'][0]
            base_second = first_annotation.get('startSecond', 0)
            base_nanosecond = first_annotation.get('startNanoSecond', 0)
            action_quality_label = first_annotation.get('actionQualityLabel', 'qualified')
            print(f"使用原始基准时间: {base_second}s + {base_nanosecond}ns")
        else:
            print("警告: 没有找到原始annotations，使用默认基准时间0")
        
        # 构建annotations列表
        annotations = []
        
        for action in vlm_result.get('actions', []):
            start_time = action.get('start_time', 0)  # VLM输出的相对时间（秒）
            end_time = action.get('end_time', 0)
            description = action.get('description', '')
            
            # 将VLM的相对时间转换为绝对时间
            # 基准时间 + 相对时间 = 绝对时间
            
            # 先计算总纳秒数（基准纳秒 + 相对时间的纳秒）
            start_total_ns = base_nanosecond + int(start_time * 1e9)
            end_total_ns = base_nanosecond + int(end_time * 1e9)
            
            # 计算最终的秒和纳秒（处理纳秒溢出）
            start_second = base_second + start_total_ns // 1000000000
            start_nanosecond = start_total_ns % 1000000000
            end_second = base_second + end_total_ns // 1000000000
            end_nanosecond = end_total_ns % 1000000000
            
            annotation = {
                "text": description,
                "actionQualityLabel": action_quality_label,
                "startSecond": int(start_second),
                "startNanoSecond": int(start_nanosecond),
                "endSecond": int(end_second),
                "endNanoSecond": int(end_nanosecond)
            }
            
            annotations.append(annotation)
        
        # 更新annotations
        target_raw_data['annotations'] = annotations
        
        # 保存（不备份，应在任务开始前统一备份）
        self.save_meta(meta, backup=False)
        raw_data_name = target_raw_data.get('name', f'rawDataList[{episode_index}]')
        print(f"已更新 {raw_data_name} 的annotations字段，共 {len(annotations)} 个标注")
        
        return True
    
    def update_episode_full(
        self,
        episode_index: int,
        vlm_result: Dict[str, Any],
        video_duration: float,
        raw_file_name: str = None
    ) -> bool:
        """
        完整更新episode的所有相关数据
        
        Args:
            episode_index: episode索引
            vlm_result: VLM标注结果
            video_duration: 视频时长
            raw_file_name: 原始文件名
            
        Returns:
            是否成功
        """
        # 更新episodes.jsonl
        success1 = self.update_episode_tasks(episode_index, vlm_result, video_duration)
        
        # 更新training_data_set_meta.json
        success2 = self.update_meta_annotations(episode_index, vlm_result, raw_file_name)
        
        return success1 and success2
    
    def batch_update(
        self,
        episode_annotations: List[Dict[str, Any]],
        progress_callback=None
    ):
        """
        批量更新多个episodes
        
        Args:
            episode_annotations: 标注结果列表，每项包含 episode_index, vlm_result, video_duration, raw_file_name
            progress_callback: 进度回调函数
        """
        total = len(episode_annotations)
        success_count = 0
        
        for i, annotation in enumerate(episode_annotations):
            episode_index = annotation.get('episode_index')
            vlm_result = annotation.get('vlm_result')
            video_duration = annotation.get('video_duration', 0)
            raw_file_name = annotation.get('raw_file_name')
            
            print(f"\n[{i+1}/{total}] 更新 episode {episode_index}...")
            
            success = self.update_episode_full(
                episode_index,
                vlm_result,
                video_duration,
                raw_file_name
            )
            
            if success:
                success_count += 1
            
            if progress_callback:
                progress_callback(i + 1, total, success)
        
        print(f"\n批量更新完成: {success_count}/{total} 成功")
