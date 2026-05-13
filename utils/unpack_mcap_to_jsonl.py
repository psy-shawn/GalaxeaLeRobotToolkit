#!/usr/bin/env python3
"""
将 RB 前缀的 mcap 文件解包为 jsonl 格式，输出结构与 test@MASTER_SLAVE_MODE 一致。

每个 topic 对应一个 jsonl 文件，每行为一条消息，包含 __timestamp_ns 及消息字段。
图像消息的 data 字段以 base64 字符串存储。

用法：
    python utils/unpack_mcap_to_jsonl.py \
        --mcap /path/to/RB***.mcap \
        --output_dir /path/to/output_folder
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

# 需要在 source install/setup.zsh 之后运行
try:
    from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
    from rclpy.serialization import deserialize_message
except ImportError:
    print("ERROR: rosbag2_py / rclpy not found. Please run: source install/setup.zsh")
    sys.exit(1)


# ── 消息类型 → dict 转换器 ─────────────────────────────────────────────────────

def ros_msg_to_dict(msg, timestamp_ns: int) -> dict:
    """将反序列化后的 ROS2 消息转为可 JSON 序列化的 dict。"""
    d = _msg_to_dict(msg)
    d["__timestamp_ns"] = timestamp_ns
    return d


def _msg_to_dict(msg) -> dict:
    """递归地将 ROS2 消息对象转为 dict。"""
    d = {}
    fields = getattr(msg, "get_fields_and_field_types", lambda: {})()

    for field in fields.keys():
        val = getattr(msg, field, None)
        d[field] = _convert_value(val, field_name=field)
    return d


def _convert_value(val, field_name: str = ""):
    if val is None:
        return None
    # bytes / bytearray → base64 string
    if isinstance(val, (bytes, bytearray)):
        raw = bytes(val)
        return base64.b64encode(raw).decode("ascii")
    # numpy arrays → list
    if hasattr(val, "tolist"):
        inner = val.tolist()
        # uint8 list that looks like image/binary data → base64
        if field_name == "data" and isinstance(inner, list) and len(inner) > 256:
            try:
                raw = bytes(inner)
                return {"__bytes_b64": base64.b64encode(raw).decode("ascii"), "__bytes_len": len(raw)}
            except Exception:
                pass
        return inner
    if isinstance(val, (list, tuple)):
        # uint8 list for image data field → base64
        if field_name == "data" and len(val) > 256:
            try:
                raw = bytes(val)
                return {"__bytes_b64": base64.b64encode(raw).decode("ascii"), "__bytes_len": len(raw)}
            except Exception:
                pass
        return [_convert_value(v) for v in val]
    # 基础类型
    if isinstance(val, (int, float, bool, str)):
        return val
    # 嵌套 ROS2 消息对象
    if hasattr(val, "get_fields_and_field_types"):
        return _msg_to_dict(val)
    # 其他（fallback）
    try:
        return str(val)
    except Exception:
        return None


# ── topic 名称 → 文件名转换（与 test 目录命名一致）─────────────────────────────

def topic_to_filename(topic: str) -> str:
    """
    /hdas/feedback_arm_left  →  hdas__feedback_arm_left.jsonl
    规则：去掉开头的 '/'，其余 '/' 替换为 '__'
    """
    name = topic.lstrip("/").replace("/", "__")
    return name + ".jsonl"


# ── 主流程 ────────────────────────────────────────────────────────────────────

def unpack(mcap_path: str, output_dir: str):
    mcap_path = str(Path(mcap_path).resolve())
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Opening: {mcap_path}")
    reader = SequentialReader()
    storage_options = StorageOptions(uri=mcap_path, storage_id="mcap")
    converter_options = ConverterOptions(
        input_serialization_format="cdr",
        output_serialization_format="cdr",
    )
    reader.open(storage_options, converter_options)

    topic_types = reader.get_all_topics_and_types()
    type_map = {t.name: t.type for t in topic_types}

    print(f"Found {len(type_map)} topics:")
    for name, typ in sorted(type_map.items()):
        print(f"  {name}  [{typ}]")

    # 打开所有 topic 对应的文件句柄
    file_handles: dict[str, object] = {}
    counts: dict[str, int] = {}
    errors: dict[str, int] = {}

    def get_fh(topic: str):
        if topic not in file_handles:
            fname = output_dir / topic_to_filename(topic)
            file_handles[topic] = open(fname, "w", encoding="utf-8")
            counts[topic] = 0
            errors[topic] = 0
        return file_handles[topic]

    # 缓存已导入的消息类，避免重复 import
    msg_class_cache: dict[str, type] = {}

    def get_msg_class(msg_type: str):
        if msg_type in msg_class_cache:
            return msg_class_cache[msg_type]
        module_name, class_name = msg_type.rsplit("/", 1)
        module = __import__(module_name.replace("/", "."), fromlist=[class_name])
        cls = getattr(module, class_name)
        msg_class_cache[msg_type] = cls
        return cls

    print("\nExtracting messages...")
    total = 0
    while reader.has_next():
        topic, data, timestamp_ns = reader.read_next()
        msg_type = type_map.get(topic)
        if not msg_type:
            continue
        try:
            msg_cls = get_msg_class(msg_type)
            msg = deserialize_message(data, msg_cls)
            record = ros_msg_to_dict(msg, timestamp_ns)
            fh = get_fh(topic)
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            counts[topic] += 1
            total += 1
        except Exception as e:
            errors[topic] = errors.get(topic, 0) + 1
            if errors.get(topic, 0) <= 3:
                print(f"  [WARN] {topic}: {e}")

    for fh in file_handles.values():
        fh.close()

    print(f"\nDone. {total} messages written to: {output_dir}")
    print("\nPer-topic counts:")
    for topic in sorted(counts.keys()):
        err = errors.get(topic, 0)
        err_str = f"  ({err} errors)" if err else ""
        print(f"  {counts[topic]:6d}  {topic}{err_str}")


def main():
    parser = argparse.ArgumentParser(description="Unpack RB mcap → jsonl (same format as test@MASTER_SLAVE_MODE)")
    parser.add_argument("--mcap", required=True, help="Path to the mcap file")
    parser.add_argument("--output_dir", required=True, help="Output directory for jsonl files")
    args = parser.parse_args()
    unpack(args.mcap, args.output_dir)


if __name__ == "__main__":
    main()
