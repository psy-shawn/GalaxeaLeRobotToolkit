"""测试备份逻辑"""
from data_updater import DatasetUpdater
from pathlib import Path

# 模拟场景
dataset_dir = "/Users/psy/workspace/data/galaxea/lerobot/straighten_papercup"
updater = DatasetUpdater(dataset_dir)

print("=" * 60)
print("测试场景：模拟连续处理3个视频")
print("=" * 60)

# 第1次调用 - 应该进行备份
print("\n第1次处理视频...")
updater.backup_original_files()

# 第2次调用 - 应该跳过备份
print("\n第2次处理视频...")
updater.backup_original_files()

# 第3次调用 - 应该跳过备份
print("\n第3次处理视频...")
updater.backup_original_files()

print("\n✓ 测试完成！应该只看到一次备份信息")
