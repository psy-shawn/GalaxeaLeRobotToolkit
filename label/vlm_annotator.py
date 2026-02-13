"""
VLM推理模块：负责调用多模态大模型进行视频标注
"""
import uuid
import requests
import json
import os
from typing import List, Dict, Any, Optional
import time


class VLMAnnotator:
    """VLM标注器"""
    
    # 系统提示词模板（根据readme.md的要求设计）
    SYSTEM_PROMPT = """Role: 你是一个专业的机器人操作数据标注员。你的任务是分析一段机器人遥操视频，识别有意义的完整操作动作。

Task:
1. 观看完整视频帧序列（已按时间顺序排列）
2. 识别视频中的完整操作动作（不要过度细分）
   - 动作粒度：将一个有意义的完整任务作为一个动作（如"抓取并扶正"、"移动并放置"）
   - 不要将"接近物体"、"抓取"、"提起"、"移动"拆分成多个动作
3. 物体识别：必须准确识别被操作物体的具体特征
   - 如有多个相似物体，用方位词区分：如"左侧的红色纸杯"、"右边的空纸杯"
   - 如有多个相同物体，用序号区分：如"纸杯1"、"纸杯2"
4. 臂别标注：必须明确是"左臂"还是"右臂"在执行操作
   - 判断标准：从操作者第一人称视角，画面左侧的机械臂是左臂，画面右侧的机械臂是右臂
   - 仔细观察：看清楚是哪只手臂在移动、接触物体、执行操作
   - 如果两只手臂同时协作，使用"双臂"
   - 不要使用"机械臂"、"手"、"手臂"等模糊表述
   - 不要默认都是右臂，必须根据实际画面判断
   - 格式：[左臂/右臂/双臂] + [动作] + [物体]
5. 时序分割：为每个完整动作提供开始和结束时间（秒）
   - 开始时间：臂开始向目标移动的时刻
   - 结束时间：整个操作完成的时刻（如物体已放置好、臂已复位）

Constraint:
- 动作不要过度细分，保持在3-8个完整动作为宜
- 如果是连续操作不同物体，才需要拆分为独立动作
- 输出必须是纯JSON格式，不要包含任何其他文本
- 描述要简洁、具体、可执行

Output Format Examples:

示例1 - 整理纸杯任务：
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

示例2 - 整理抱枕任务：
{
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
        },
        {
            "start_time": 15.0,
            "end_time": 20.0,
            "description": "本体后仰至直立位置",
            "description_en": "Robot body tilts back to upright position"
        }
    ],
    "task_summary": "整理沙发抱枕",
    "task_summary_en": "Arrange sofa cushions"
}

示例3 - 物体转移任务：
{
    "actions": [
        {
            "start_time": 0.0,
            "end_time": 6.0,
            "description": "左臂抓取第一个瓶子并移动到右侧区域",
            "description_en": "Left arm grasps the first bottle and moves it to the right area"
        },
        {
            "start_time": 6.0,
            "end_time": 12.0,
            "description": "左臂抓取第二个瓶子并移动到右侧区域",
            "description_en": "Left arm grasps the second bottle and moves it to the right area"
        }
    ],
    "task_summary": "整理桌面物品",
    "task_summary_en": "Organize items on the table"
}

【重要】左右臂识别技巧：
- 仔细观察画面中哪只机械臂在移动和操作物体
- 画面左侧的机械臂 = 左臂，画面右侧的机械臂 = 右臂
- 不要假设或默认都是右臂，必须根据实际画面判断
- 如果看不清楚，重点观察手臂的起始位置和运动轨迹"""
    
    def __init__(
        self,
        api_url: str = None,
        api_token: str = None,
        max_retries: int = 3,
        retry_delay: int = 2
    ):
        """
        初始化VLM标注器
        
        Args:
            api_url: VLM API地址（可选，默认从环境变量VLM_API_URL读取）
            api_token: API认证token（可选，默认从环境变量VLM_API_TOKEN读取）
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
        """
        # 优先使用传入的参数，否则从环境变量读取
        self.api_url = api_url or os.getenv(
            'VLM_API_URL'
        )
        self.api_token = api_token or os.getenv(
            'VLM_API_TOKEN'
        )
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    def annotate_video_frames(
        self,
        encoded_frames: List[tuple],
        episode_info: Optional[Dict] = None,
        use_grid: bool = True
    ) -> Dict[str, Any]:
        """
        使用VLM标注视频帧
        
        Args:
            encoded_frames: [(timestamp, base64_str), ...] 时间戳和base64编码的帧列表
            episode_info: 额外的episode信息（如当前任务描述）
            use_grid: 是否使用网格图模式（推荐，可减少API调用）
            
        Returns:
            标注结果字典
        """
        if use_grid:
            return self._annotate_with_grid(encoded_frames, episode_info)
        else:
            return self._annotate_with_sequence(encoded_frames, episode_info)
    
    def _annotate_with_grid(
        self,
        encoded_frames: List[tuple],
        episode_info: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """使用网格图模式标注（推荐）"""
        from video_processor import create_frame_grid
        
        # 创建帧网格
        timestamps, grid_base64 = create_frame_grid(encoded_frames, grid_size=12)
        
        if not grid_base64:
            return {"actions": [], "task_summary": "", "task_summary_en": ""}
        
        # 构建用户提示
        user_prompt = f"""请分析这个机器人操作视频的关键帧网格图。

视频信息：
- 总时长: {encoded_frames[-1][0]:.1f}秒
- 网格时间点: {', '.join([f'{t:.1f}s' for t in timestamps])}
- 任务背景: {episode_info.get('task', '未知任务') if episode_info else '未知任务'}

标注要求：
1. 识别完整的操作动作（不要过度细分为接近、抓取、移动等多个小步骤）
2. 明确标注"左臂"、"右臂"或"双臂"（不要使用"机械臂"）
3. 如有多个相似物体，用方位（左侧、右边）或序号（第一个、中间）区分
4. 10s左右的视频，生成1个动作即可，30s的视频生成2-3个动作，60s的视频生成5-8个动作

请仔细观察每一帧，按照要求的JSON格式输出标注结果。"""
        
        # 调用API
        return self._call_vlm_api(grid_base64, user_prompt)
    
    def _annotate_with_sequence(
        self,
        encoded_frames: List[tuple],
        episode_info: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """使用帧序列模式标注（成本较高）"""
        # 采样关键帧（最多12帧）
        step = max(1, len(encoded_frames) // 12)
        selected_frames = encoded_frames[::step][:12]
        
        # 构建多图像消息
        image_contents = []
        timestamps = []
        
        for timestamp, base64_str in selected_frames:
            timestamps.append(timestamp)
            image_contents.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_str}"}
            })
        
        # 构建用户提示
        user_prompt = f"""请分析这段机器人操作视频。

视频信息：
- 总时长: {encoded_frames[-1][0]:.1f}秒
- 关键时间点: {', '.join([f'{t:.1f}s' for t in timestamps])}
- 任务背景: {episode_info.get('task', '未知任务') if episode_info else '未知任务'}

标注要求：
1. 识别完整的操作动作（不要过度细分为接近、抓取、移动等多个小步骤）
2. 明确标注"左臂"、"右臂"或"双臂"（不要使用"机械臂"）
3. 如有多个相似物体，用方位（左侧、右边）或序号（1、2、3）区分
4. 10s左右的视频，生成1个动作即可，30s的视频生成2-3个动作，60s的视频生成5-8个动作

请仔细观察每一帧，按照要求的JSON格式输出标注结果。"""
        
        # 调用API（多图像模式）
        return self._call_vlm_api_multi_image(image_contents, user_prompt)
    
    def _call_vlm_api(self, image_base64: str, user_prompt: str) -> Dict[str, Any]:
        """
        调用VLM API（单图像模式）
        
        Args:
            image_base64: 图像的base64编码
            user_prompt: 用户提示词
            
        Returns:
            解析后的标注结果
        """
        headers = {
            "Content-Type": "application/json",
            "BCS-APIHub-RequestId": str(uuid.uuid4()),
            'X-CHJ-GWToken': self.api_token,
        }
        
        data = {
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                        },
                    ],
                }
            ],
            "enable_thinking": False,
            "temperature": 0.3,  # 降低温度以获得更稳定的输出
        }
        
        # 重试机制
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(self.api_url, headers=headers, json=data, timeout=60)
                resp.raise_for_status()
                
                result = resp.json()
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                
                # 解析JSON
                return self._parse_vlm_response(content)
                
            except Exception as e:
                print(f"API调用失败 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    return {"actions": [], "task_summary": "", "task_summary_en": "", "error": str(e)}
    
    def _call_vlm_api_multi_image(self, image_contents: List[Dict], user_prompt: str) -> Dict[str, Any]:
        """调用VLM API（多图像模式）"""
        headers = {
            "Content-Type": "application/json",
            "BCS-APIHub-RequestId": str(uuid.uuid4()),
            'X-CHJ-GWToken': self.api_token,
        }
        
        content_list = [{"type": "text", "text": user_prompt}] + image_contents
        
        data = {
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": content_list}
            ],
            "enable_thinking": False,
            "temperature": 0.3,
        }
        
        # 重试机制
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(self.api_url, headers=headers, json=data, timeout=120)
                resp.raise_for_status()
                
                result = resp.json()
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                
                return self._parse_vlm_response(content)
                
            except Exception as e:
                print(f"API调用失败 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    return {"actions": [], "task_summary": "", "task_summary_en": "", "error": str(e)}
    
    def _parse_vlm_response(self, response_text: str) -> Dict[str, Any]:
        """
        解析VLM响应文本
        
        Args:
            response_text: VLM返回的文本
            
        Returns:
            解析后的JSON对象
        """
        try:
            # 尝试直接解析JSON
            result = json.loads(response_text)
            return result
        except json.JSONDecodeError:
            # 如果失败，尝试提取JSON部分
            # 寻找```json ... ```包裹的内容
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group(1))
                    return result
                except json.JSONDecodeError:
                    pass
            
            # 尝试寻找{}包裹的内容
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group(0))
                    return result
                except json.JSONDecodeError:
                    pass
            
            print(f"无法解析VLM响应: {response_text[:200]}...")
            return {
                "actions": [],
                "task_summary": "",
                "task_summary_en": "",
                "error": "Failed to parse VLM response",
                "raw_response": response_text
            }
