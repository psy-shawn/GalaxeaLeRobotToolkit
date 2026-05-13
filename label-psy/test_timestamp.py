"""测试时间戳转换逻辑"""
import json
from pathlib import Path

# 测试数据
print("=" * 80)
print("时间戳转换测试")
print("=" * 80)

# 原始基准时间（从实际数据中获取）
base_second = 1770293857
base_nanosecond = 260645179

print(f"\n原始基准时间:")
print(f"  startSecond: {base_second}")
print(f"  startNanoSecond: {base_nanosecond}")

# VLM输出的相对时间（示例）
vlm_actions = [
    {"start_time": 0, "end_time": 5.5, "description": "右臂抓取纸杯"},
    {"start_time": 5.5, "end_time": 12.3, "description": "右臂扶正纸杯"}
]

print(f"\nVLM输出的相对时间:")
for i, action in enumerate(vlm_actions, 1):
    print(f"  动作{i}: {action['start_time']}s - {action['end_time']}s")

# 转换逻辑
print(f"\n转换后的绝对时间:")
for i, action in enumerate(vlm_actions, 1):
    start_time = action['start_time']
    end_time = action['end_time']
    
    # 计算总纳秒数
    start_total_ns = base_nanosecond + int(start_time * 1e9)
    end_total_ns = base_nanosecond + int(end_time * 1e9)
    
    # 计算最终的秒和纳秒
    start_second = base_second + start_total_ns // 1000000000
    start_nanosecond = start_total_ns % 1000000000
    end_second = base_second + end_total_ns // 1000000000
    end_nanosecond = end_total_ns % 1000000000
    
    print(f"\n  动作{i}: {action['description']}")
    print(f"    startSecond: {int(start_second)}, startNanoSecond: {int(start_nanosecond)}")
    print(f"    endSecond: {int(end_second)}, endNanoSecond: {int(end_nanosecond)}")
    print(f"    时长: {end_time - start_time}秒")

# 验证：第一个动作的开始时间应该等于基准时间
first_action_start = vlm_actions[0]['start_time']
start_total_ns = base_nanosecond + int(first_action_start * 1e9)
start_second = base_second + start_total_ns // 1000000000
start_nanosecond = start_total_ns % 1000000000

print(f"\n验证:")
print(f"  第一个动作的开始时间: {int(start_second)}s + {int(start_nanosecond)}ns")
print(f"  原始基准时间: {base_second}s + {base_nanosecond}ns")
print(f"  ✓ 匹配!" if (int(start_second) == base_second and int(start_nanosecond) == base_nanosecond) else "  ✗ 不匹配!")

# 模拟实际更新
print("\n" + "=" * 80)
print("模拟实际更新（straighten_papercup数据集的episode 0）")
print("=" * 80)

meta_file = Path("/Users/psy/workspace/data/galaxea/lerobot/straighten_papercup/training_data_set_meta.json")
if meta_file.exists():
    with open(meta_file, 'r') as f:
        meta = json.load(f)
    
    if 'rawDataList' in meta and len(meta['rawDataList']) > 0:
        raw_data_0 = meta['rawDataList'][0]
        print(f"\nrawDataList[0]:")
        print(f"  name: {raw_data_0.get('name')}")
        
        if raw_data_0.get('annotations'):
            orig_anno = raw_data_0['annotations'][0]
            print(f"\n  原始annotation:")
            print(f"    text: {orig_anno.get('text')}")
            print(f"    startSecond: {orig_anno.get('startSecond')}")
            print(f"    startNanoSecond: {orig_anno.get('startNanoSecond')}")
            print(f"    endSecond: {orig_anno.get('endSecond')}")
            print(f"    endNanoSecond: {orig_anno.get('endNanoSecond')}")

print("\n" + "=" * 80)
