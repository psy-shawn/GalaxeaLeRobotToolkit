# 自动化数据标注工具

基于VLM（多模态大模型）的机器人操作数据自动标注系统。

## 功能特性

- ✅ 自动从视频中抽取关键帧
- ✅ 使用VLM进行细粒度动作识别和时序分割
- ✅ 自动更新 `episodes.jsonl` 和 `training_data_set_meta.json`
- ✅ 支持网格图模式（降低API成本）
- ✅ 支持断点续传
- ✅ 自动备份原文件

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 配置API（推荐使用环境变量）

**方式1：使用环境变量（推荐）**

```bash
# 设置环境变量
export VLM_API_URL="http://api-hub.inner.chj.cloud/llm-gateway/v1/chat/completions/bailian-qwen3-vl-plus"
export VLM_API_TOKEN="your_api_token_here"

# 运行标注
python auto_annotate.py /path/to/dataset
```

**方式2：使用命令行参数**

```bash
python auto_annotate.py /path/to/dataset \
  --api-url "http://..." \
  --api-token "your_token"
```

**方式3：使用默认配置**

如果不设置环境变量也不传参数，将使用代码中的默认值。

### 1. 基本用法

标注整个数据集：

```bash
python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/straighten_papercup
```

### 2. 测试单个视频

先测试一个episode（推荐）：

```bash
python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/straighten_papercup --single 0
```

### 3. 限制处理数量

只处理前5个episodes（用于测试）：

```bash
python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/straighten_papercup --max-episodes 5
```

### 4. 断点续传

从第10个视频继续处理：

```bash
python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/straighten_papercup --start-index 10
```

### 5. 导出结果

将标注结果导出到JSON文件：

```bash
python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/straighten_papercup --export results.json
```

### 6. 自定义参数

```bash
python auto_annotate.py /path/to/dataset \
  --fps 2 \                    # 抽帧帧率设为2fps
  --no-grid \                  # 不使用网格图模式
  --max-episodes 10 \          # 最多处理10个episodes
  --api-url "http://..." \     # 自定义API地址
  --api-token "your-token"     # 自定义API token
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `dataset_dir` | 数据集目录路径（必需） | - |
| `--api-url` | VLM API地址 | 配置文件中的默认值 |
| `--api-token` | API认证token | 配置文件中的默认值 |
| `--fps` | 视频抽帧帧率 | 1 |
| `--no-grid` | 禁用网格图模式 | False（默认启用）|
| `--max-episodes` | 最大处理episode数 | None（全部）|
| `--start-index` | 起始视频索引 | 0 |
| `--single` | 只处理指定episode | None |
| `--export` | 导出结果文件路径 | None |

## 工作流程

```
1. 视频预处理
   ↓
   - 读取 episode_XXXXXX.mp4
   - 按设定fps抽帧（默认1fps）
   - 将帧编码为base64
   
2. VLM推理
   ↓
   - 创建帧网格图（可选，推荐）
   - 调用VLM API
   - 解析JSON格式的标注结果
   
3. 数据更新
   ↓
   - 更新 episodes.jsonl 的 tasks 字段
   - 更新 training_data_set_meta.json 的 annotations 字段
   - 自动备份原文件
```

## 标注格式规范

### ❌ 错误示例（过度细分）
```json
{
  "actions": [
    {
      "start_time": 2.0,
      "end_time": 4.0,
      "description": "机械臂从右侧接近桌面上的棕色纸杯"
    },
    {
      "start_time": 4.0,
      "end_time": 6.0,
      "description": "机械臂末端夹爪闭合，抓取棕色纸杯"
    },
    {
      "start_time": 6.0,
      "end_time": 8.0,
      "description": "机械臂将棕色纸杯向上提起并略微向左移动"
    },
    {
      "start_time": 8.0,
      "end_time": 10.0,
      "description": "机械臂将棕色纸杯倾斜，使其开口朝下"
    },
    {
      "start_time": 10.0,
      "end_time": 11.0,
      "description": "机械臂释放棕色纸杯，纸杯自由下落"
    }
  ]
}
```
**问题：**
1. ❌ 使用了"机械臂"而非"左臂/右臂"
2. ❌ 过度细分（5个动作描述同一个完整任务）
3. ❌ 包含过多中间过程细节

### ✅ 正确示例（完整动作）
```json
{
  "actions": [
    {
      "start_time": 2.0,
      "end_time": 11.0,
      "description": "右臂抓取并扶正空纸杯",
      "description_en": "Right arm grasps and straightens the empty paper cup"
    }
  ],
  "task_summary": "整理桌面上的纸杯",
  "task_summary_en": "Arrange paper cups on the table"
}
```
**优点：**
1. ✅ 明确使用"右臂"
2. ✅ 将完整任务合并为一个有意义的动作
3. ✅ 描述简洁、目标明确

### 标注要点
- ✅ 臂别标注：使用"左臂"、"右臂"、"双臂"或"本体"
- ❌ 禁止使用：机械臂、手、手臂等模糊表述
- ✅ 动作粒度：保持完整性（如"抓取并扶正"），不要拆分为多个细小步骤
- ✅ 物体区分：多个相似物体用方位（左侧、右边）或序号（第一个、中间）区分
- ✅ 时长控制：建议每个视频3-8个完整动作

## 输出格式

### VLM输出格式

```json
{
  "actions": [
    {
      "start_time": 0.0,
      "end_time": 5.0,
      "description": "右臂抓取并扶正空纸杯",
      "description_en": "Right arm grasps and straightens the empty paper cup"
    },
    {
      "start_time": 5.0,
      "end_time": 10.5,
      "description": "左臂抓取并扶正左侧的红色纸杯",
      "description_en": "Left arm grasps and straightens the red paper cup on the left"
    }
  ],
  "task_summary": "整理桌面上的纸杯",
  "task_summary_en": "Arrange paper cups on the table"
}
```

### episodes.jsonl更新示例

```json
{
  "episode_index": 0,
  "tasks": [
    "右臂抓取并扶正空纸杯@Right arm grasps and straightens the empty paper cup",
    "左臂抓取并扶正左侧的红色纸杯@Left arm grasps and straightens the red paper cup on the left"
  ],
  "length": 263
}
```

**注意：** tasks字段只包含动作描述（actions），不包含任务总结（task_summary）。

### training_data_set_meta.json更新示例

```json
{
  "annotations": [
    {
      "startSecond": 0,
      "startNanoSecond": 0,
      "endSecond": 5,
      "endNanoSecond": 0,
      "text": "右臂抓取并扶正空纸杯",
      "annotatedDuration": 5
    }
  ]
}
```

## 文件结构

```
label/
├── auto_annotate.py          # 主程序
├── video_processor.py        # 视频处理模块
├── vlm_annotator.py          # VLM推理模块
├── data_updater.py           # 数据更新模块
├── config.yaml               # 配置文件
├── requirements.txt          # 依赖列表
├── README_AUTO_ANNOTATE.md   # 本文档
└── test_api.py              # API测试脚本（已有）
```

## 注意事项

1. **备份数据**：首次运行前建议手动备份 `episodes.jsonl` 和 `training_data_set_meta.json`
2. **API成本**：网格图模式可显著降低API调用成本，建议启用
3. **抽帧率**：对于慢速动作，1fps通常足够；快速动作可考虑2fps
4. **错误处理**：程序会自动重试失败的API调用，并记录失败的episodes
5. **断点续传**：程序每处理完一个episode会立即保存，可安全中断

## 故障排查

### 问题1：找不到视频文件

确认数据集目录结构是否正确：
```
dataset_dir/
  dataset_name/
    videos/
      chunk-000/
        observation.images.head_rgb/
          episode_000000.mp4
          episode_000001.mp4
          ...
```

### 问题2：API调用失败

1. 检查网络连接
2. 验证API token是否有效
3. 查看API限流配置

### 问题3：VLM输出格式错误

VLM可能返回非标准JSON，程序会尝试提取JSON部分。如始终失败，可调整提示词。

## 高级用法

### 自定义提示词

编辑 [vlm_annotator.py](vlm_annotator.py#L13-L54) 中的 `SYSTEM_PROMPT` 变量。

### 更换VLM模型

编辑 [config.yaml](config.yaml#L3-L9)，选择不同的模型API。

### 批量处理多个数据集

```bash
for dataset in /path/to/datasets/*; do
  python auto_annotate.py "$dataset" --max-episodes 5
done
```

## 示例

测试straighten_papercup数据集的第一个episode：

```bash
cd /Users/psy/workspace/GalaxeaLeRobotToolkit/label
python auto_annotate.py /Users/psy/workspace/data/galaxea/lerobot/straighten_papercup --single 0
```

## 许可证

与GalaxeaLeRobotToolkit主项目保持一致
