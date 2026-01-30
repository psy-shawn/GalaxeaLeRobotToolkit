#!/usr/bin/env python3
"""
批量化命名与打标工具
1. 替换 Galaxea 数据集 JSON 文件中的 "xxx" 字段
2. 向 JSON 文件中添加或更新 "label" 标签字段
"""

import os
import json
import argparse
import glob

def update_json_file(json_file_path, replacements, label_updates):
    """
    更新单个JSON文件
    :param json_file_path: 文件路径
    :param replacements: 用于替换 'xxx' 的字典
    :param label_updates: 用于添加/更新 'label' 字段的字典
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        is_modified = False

        # --- 功能 1: 替换现有的 'xxx' 字段 ---
        
        # 更新 project_info
        if 'project_info' in data and 'project_name' in data['project_info']:
            if data['project_info']['project_name'] is not None and 'pname' in replacements:
                data['project_info']['project_name'] = replacements['pname']
                is_modified = True

        # 更新 task_info
        if 'task_info' in data:
            if 'task_name' in data['task_info'] and data['task_info']['task_name'] is not None and 'tname' in replacements:
                data['task_info']['task_name'] = replacements['tname']
                is_modified = True
            if 'task_owner' in data['task_info'] and data['task_info']['task_owner'] is not None and 'towner' in replacements:
                data['task_info']['task_owner'] = replacements['towner']
                is_modified = True

        # 更新 operation_info
        if 'operation_info' in data and 'operator_name' in data['operation_info']:
            if data['operation_info']['operator_name'] is not None and 'opname' in replacements:
                data['operation_info']['operator_name'] = replacements['opname']
                is_modified = True

        # --- 功能 2: 添加或更新 label 字段 ---
        
        if label_updates:
            # 如果 'label' 键不存在，初始化为空字典
            if 'label' not in data:
                data['label'] = {}
                is_modified = True # 新建了 label 肯定算修改
            
            # 遍历需要更新的标签
            for key, value in label_updates.items():
                # 只有当值不为空，且当前值与新值不同时才写入
                if value is not None:
                    # 如果原先没有这个key，或者值不一样，则更新
                    if key not in data['label'] or data['label'][key] != value:
                        data['label'][key] = value
                        is_modified = True

        # 只有在发生修改时才写回文件
        if is_modified:
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        else:
            return False

    except Exception as e:
        print(f"处理文件 {json_file_path} 时出错: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='批量化处理Galaxea数据集JSON：替换xxx字段及添加Label标签')
    
    #原有替换参数
    parser.add_argument('--pname', type=str, help='项目名称 (替换 project_name 中的 xxx)')
    parser.add_argument('--tname', type=str, help='任务名称 (替换 task_name 中的 xxx)')
    parser.add_argument('--towner', type=str, help='任务所有者 (替换 task_owner 中的 xxx)')
    parser.add_argument('--opname', type=str, help='操作员名称 (替换 operator_name 中的 xxx)')
    
    # 新增标签参数
    parser.add_argument('--temporal', type=str, help='标签: 时序长度 (temporal_length)', choices=['short', 'medium', 'long'])
    parser.add_argument('--arm', type=str, help='标签: 手臂模式 (arm_mode)', choices=['single', 'dual', 'interact'])
    parser.add_argument('--obj', type=str, help='标签: 物体类型 (object_type)', choices=['rigidity', 'articulated', 'deformable', 'fluid'])
    parser.add_argument('--inter', type=str, help='标签: 交互模式 (interactive_mode)', choices=['environment', 'tool', 'human'])
    parser.add_argument('--fail', type=str, help='标签: 交互模式 (interactive_mode)', default='')
    
    # 通用参数
    parser.add_argument('--dir', type=str, default='.', help='要处理的文件夹路径 (默认: 当前目录)')

    args = parser.parse_args()

    # 构建替换字典
    replacements = {}
    if args.pname: replacements['pname'] = args.pname
    if args.tname: replacements['tname'] = args.tname
    if args.towner: replacements['towner'] = args.towner
    if args.opname: replacements['opname'] = args.opname

    # 构建标签更新字典
    label_updates = {}
    if args.temporal: label_updates['temporal_length'] = args.temporal
    if args.arm: label_updates['arm_mode'] = args.arm
    if args.obj: label_updates['object_type'] = args.obj
    if args.inter: label_updates['interactive_mode'] = args.inter
    if args.inter: label_updates['fail'] = args.fail

    # 检查至少提供了一个操作参数
    if not replacements and not label_updates:
        parser.error("至少需要提供一个替换参数 (--pname等) 或 一个标签参数 (--temporal等)")

    # 查找所有JSON文件
    search_pattern = os.path.join(args.dir, '**', '*.json')
    json_files = glob.glob(search_pattern, recursive=True)

    if not json_files:
        print(f"在目录 {args.dir} 下未找到JSON文件")
        return

    print(f"找到 {len(json_files)} 个JSON文件需要处理")
    if replacements:
        print(f"替换操作: {replacements}")
    if label_updates:
        print(f"打标操作: {label_updates}")

    # 处理每个JSON文件
    success_count = 0
    for json_file in json_files:
        # print(f"正在检查: {json_file}") # 可选：如果文件太多可以注释掉这行
        if update_json_file(json_file, replacements, label_updates):
            print(f"已修改: {json_file}")
            success_count += 1

    print(f"\n处理完成! 共修改了 {success_count} 个文件 (总计扫描 {len(json_files)} 个)")

"""
使用方法示例:

1. 仅替换现有字段中的 'xxx':
python3 add_name.py --pname pick_task --tname apple_pick --dir ./data

2. 仅添加/更新标签 (Label):
python3 add_name.py --temporal short --arm single --obj rigidity --inter environment --dir ./data

3. 同时替换 'xxx' 并添加标签:
python3 add_name.py --pname manipulation --tname pick_cube --towner operator1 --temporal short --arm single --obj rigidity --inter environment --dir /home/r1lite/GalaxeaDataset/20260119
"""

if __name__ == '__main__':
    main()