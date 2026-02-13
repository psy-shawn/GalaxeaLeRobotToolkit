## 标注流程架构设计
接入流程分为三个步骤：视频预处理 -> VLM 推理与提示工程 -> 结构化数据解析。

---

## ✨ 自动化标注工具

已实现完整的自动化标注系统！详见 [README_AUTO_ANNOTATE.md](README_AUTO_ANNOTATE.md)

### 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 测试系统
python test_pipeline.py

# 3. 标注单个视频（测试）
python auto_annotate.py /path/to/dataset --single 0

# 4. 批量标注
python auto_annotate.py /path/to/dataset
```

---

### 步骤一：视频抽帧与编码
不要将每一帧都喂给VLM（成本高且噪音大）。对于遥操任务，动作通常较慢，建议：

采样率： 1fps 或 2fps（每秒1-2帧）通常足够。

时间戳映射： 必须记录每张图片对应的真实视频时间（Time Code），以便后续模型输出“第几秒”时能对应回原始数据。

### 步骤二：Prompt Engineering (提示工程) [关键]
这是能否成功区分“可乐瓶”和“雪碧瓶”并准确切割时间的关键。Prompt 需要包含三个要素：角色设定、任务定义、输出格式约束。

推荐 System Prompt 模板：

Role: 你是一个专业的机器人操作数据标注员。你的任务是分析一段机器人遥操视频，将其分解为一系列连续的元操作（Primitive Actions）。

Task:

观看完整视频。

识别视频中包含的所有独立动作。动作通常包括“抓取（Pick）”、“移动（Move）”、“放置（Place/Drop）”。

细粒度识别： 必须准确识别被操作物体的具体特征（例如：区分“可乐瓶”、“雪碧瓶”、“冰红茶瓶”），不要只说“瓶子”。

时序分割： 为每个动作提供精确的开始时间（start_time）和结束时间（end_time），单位为秒。

Start: 机械臂开始向目标物体移动或开始执行动作的瞬间。

End: 动作完成（如物体离开手爪或手爪复位）的瞬间。

Constraint:

如果视频是连续操作（如拿起A扔掉，再拿起B扔掉），必须拆分为独立的事件。

输出必须是纯 JSON 格式。

Output Format Example:

episodes.json
{"episode_index": 0, "tasks": ["双手配合将左侧的抱枕立起来@Coordinate both hands to stand the left cushion upright.", "双手配合将右侧的抱枕立起来@Coordinate both hands to stand the right cushion upright.", "arrange the sofa cushions", "null", "本体后仰至直立，然后本体向左移动靠近左侧抱枕@Tilt body backward to upright, then move left toward the left cushion.", "双手配合将中间的抱枕立起来@Lift the center cushion upright using both hands.", "qualified", "本体后仰至直立@Tilt backward to upright.", "本体回到初始位置@Return to the initial position."], "length": 2733, "raw_file_name": "RB250319017_20250722194341214_RAW.bag"}


training_data_set_meta.json
{
    ...
    "annotations": [
        {
            "startSecond": 1753184621,
            "startNanoSecond": 665024281,
            "endSecond": 1753184678,
            "endNanoSecond": 767085552,
            "text": "\u53cc\u624b\u914d\u5408\u5c06\u4e2d\u95f4\u7684\u62b1\u6795\u7acb\u8d77\u6765",
            "annotatedDuration": 57,
        },
        {
            "startSecond": 1753184678,
            "startNanoSecond": 767085552,
            "endSecond": 1753184683,
            "endNanoSecond": 129048586,
            "text": "\u672c\u4f53\u540e\u4ef0\u81f3\u76f4\u7acb",
            "annotatedDuration": 5,
        }
    ],
    ...
}