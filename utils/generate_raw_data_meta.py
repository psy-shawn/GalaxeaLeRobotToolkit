#!/usr/bin/env python3
"""
自动生成 raw_data_meta.json 文件
遍历目录结构,为每个包含mcap文件的子目录创建对应的元数据文件
用法：
    python generate_raw_data_meta.py [root_directory]
如果未指定 root_directory，则使用脚本所在目录。 
"""
import os
import json
import yaml
import re
from pathlib import Path

def find_mcap_folders(root_dir):
    """
    查找所有包含 mcap 文件的文件夹
    返回: {folder_path: [mcap_folders_list]}
    """
    result = {}
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 跳过 fail 文件夹
        if 'fail' in dirpath.split(os.sep):
            continue
        
        # 查找当前目录下的所有以 _RAW 结尾的文件夹
        raw_folders = [d for d in dirnames if d.endswith('_RAW')]
        
        if raw_folders:
            result[dirpath] = raw_folders
    
    return result

def create_raw_data_meta(folder_path, raw_folders):
    """
    为指定文件夹创建 raw_data_meta.json
    """
    # 从路径中提取数据集名称
    # 例如: path = "/Users/psy/workspace/data/r1lite/20260203/pick_3_bottles_and_place_it_into_trashbin/left_arm/order_low_mid_tall"
    # dataset_name = "pick_3_bottles_and_place_it_into_trashbin"
    # annotations.text = "pick 3 bottles and place it into trashbin left arm order low mid tall"
    path_parts = Path(folder_path).parts

    # 查找日期目录(YYYYMMDD)，提取日期后的一级目录名作为数据集名称
    dataset_name = os.path.basename(folder_path)
    annotation_text = ''
    try:
        date_index = next(
            i for i, part in enumerate(path_parts)
            if re.match(r'^\d{8}$', part)
        )
        if date_index + 1 < len(path_parts):
            dataset_name = path_parts[date_index + 1]

        # 使用日期后的路径生成 annotations.text
        text_parts = path_parts[date_index + 1:]
        annotation_text = ' '.join(p.replace('_', ' ') for p in text_parts if p)
    except StopIteration:
        # 未找到日期目录时，退化为使用当前目录名
        dataset_name = os.path.basename(folder_path)
        annotation_text = dataset_name.replace('_', ' ')
    
    raw_data_list = []
    
    for raw_folder in sorted(raw_folders):
        raw_folder_path = os.path.join(folder_path, raw_folder)
        json_file = os.path.join(folder_path, raw_folder + '.json')
        metadata_yaml_file = os.path.join(raw_folder_path, 'metadata.yaml')
        
        # 读取对应的 JSON 文件获取元数据
        metadata = {}
        if os.path.exists(json_file):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to read {json_file}: {e}")
        
        # 读取 metadata.yaml 获取时间戳信息
        yaml_metadata = {}
        if os.path.exists(metadata_yaml_file):
            try:
                with open(metadata_yaml_file, 'r', encoding='utf-8') as f:
                    yaml_metadata = yaml.safe_load(f)
            except Exception as e:
                print(f"Warning: Failed to read {metadata_yaml_file}: {e}")
        
        # 查找 mcap 文件
        mcap_files = [f for f in os.listdir(raw_folder_path) if f.endswith('.mcap')]
        if not mcap_files:
            print(f"Warning: No mcap file found in {raw_folder_path}")
            continue
        
        mcap_file = mcap_files[0]
        mcap_path = os.path.join(raw_folder_path, mcap_file)
        
        # 提取机器人类型
        robot_type = 'R1Lite'  # 根据路径判断,这里默认是 R1Lite
        
        # 构建数据项
        data_item = {
            "name": mcap_file,
            "path": mcap_path,
            "robotType": robot_type,
        }
        
        # 从 metadata.yaml 和 JSON 构建 annotations
        if yaml_metadata and metadata:
            try:
                bag_info = yaml_metadata.get('rosbag2_bagfile_information', {})
                starting_time_ns = bag_info.get('starting_time', {}).get('nanoseconds_since_epoch', 0)
                duration_ns = bag_info.get('duration', {}).get('nanoseconds', 0)
                
                # 转换为秒
                start_second = int(starting_time_ns // 1_000_000_000)
                start_nanosecond = int(starting_time_ns % 1_000_000_000)
                end_timestamp_ns = starting_time_ns + duration_ns
                end_second = int(end_timestamp_ns // 1_000_000_000)
                end_nanosecond = int(end_timestamp_ns % 1_000_000_000)
                
                # 从 JSON 获取任务描述和质量标签
                task_name = metadata.get('task_info', {}).get('task_name', '')
                fail_label = metadata.get('label', {}).get('fail', '')
                
                # 构建 annotation
                annotation = {
                    "text": annotation_text or task_name,
                    "actionQualityLabel": "unqualified" if fail_label else "qualified",
                    "startSecond": start_second,
                    "startNanoSecond": start_nanosecond,
                    "endSecond": end_second,
                    "endNanoSecond": end_nanosecond
                }
                
                data_item["annotations"] = [annotation]
            except Exception as e:
                print(f"Warning: Failed to create annotation for {raw_folder}: {e}")
        
        raw_data_list.append(data_item)
    
    if not raw_data_list:
        return None
    
    # 构建完整的元数据结构
    # 注意: dataset_converter.py 会自动包装一层 "data"，所以这里不需要
    raw_data_meta = {
        "rawDataSetName": dataset_name,
        "rawDataList": raw_data_list
    }
    
    return raw_data_meta

def main():
    # 如果没有指定路径,则使用当前脚本所在目录,否则使用指定路径
    import sys
    root_dir = ''
    if len(sys.argv) == 2:
        root_dir = sys.argv[1]
    else:
        root_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"扫描目录: {root_dir}")
    
    # 查找所有包含 mcap 的文件夹
    mcap_folders_dict = find_mcap_folders(root_dir)
    
    print(f"\n找到 {len(mcap_folders_dict)} 个包含数据的文件夹:\n")
    
    created_count = 0
    for folder_path, raw_folders in sorted(mcap_folders_dict.items()):
        print(f"处理: {folder_path}")
        print(f"  找到 {len(raw_folders)} 个数据文件夹")
        
        # 创建元数据
        raw_data_meta = create_raw_data_meta(folder_path, raw_folders)
        
        if raw_data_meta:
            # 保存到文件
            output_file = os.path.join(folder_path, 'raw_data_meta.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(raw_data_meta, f, indent=2, ensure_ascii=False)
            
            print(f"  ✓ 创建: {output_file}")
            print(f"    数据集名称: {raw_data_meta['rawDataSetName']}")
            print(f"    数据数量: {len(raw_data_meta['rawDataList'])}")
            created_count += 1
        else:
            print(f"  ✗ 跳过 (无有效数据)")
        
        print()
    
    print(f"\n总计创建了 {created_count} 个 raw_data_meta.json 文件")

if __name__ == '__main__':
    main()
