import os
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import torch

from libs.media_core.utils import utils

# --- 单一工作流名称常量 ---
WORKFLOW_COMMERCIAL_CLIPPING = "workflow_commercial_clipping"

@dataclass
class WorkflowConfig:
    """
    一个为商业广告工作流定制的、单一的配置类。
    引入了 task_id 以统一管理所有输出路径。
    """
    # --- 将没有默认值的字段移到最前面 ---
    asset_dirs: List[str]
    db_path: str
    
    # --- 实例特有参数 (有默认值) ---
    workflow_name: str = WORKFLOW_COMMERCIAL_CLIPPING
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # --- 核心解析参数 (优化) ---
    #  增大间隔，因为我们将依赖 Scene Detection 来捕捉细节，不再依赖密集抽帧
    FRAME_INTERVAL_SEC: int = 4  
    SCENE_DETECT_THRESHOLD: float = 20.0 #稍微降低阈值，更敏感地捕捉镜头切换

    # --- 设备与性能配置 ---
    DEVICE: str = field(default_factory=utils.get_device)
    CLIP_BATCH_SIZE: int = 32
    
    # 渲染配置
    MAX_VIDEO_WIDTH: int = 1920 # 强制限制最大宽度 1080P
    ENABLE_GPU_ENCODING: bool = True # 尝试启用 GPU 编码

    # --- VLM (QwenVL) 相关性能配置 ---
    VISION_LLM_IMAGE_BATCH_SIZE: int = 10
    VISION_LLM_TEXT_BATCH_SIZE: int = 48
    VISION_LLM_TORCH_DTYPE: str = "auto"
    VISION_ANALYSIS_MAX_NEW_TOKENS: int = 512
    VISION_LLM_MODEL_TYPE: str = "qwen3"

    # --- LLM (Qwen) 相关配置 ---
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_DEFAULT_TEMPERATURE: float = 0.1
    LLM_DEFAULT_MAX_TOKENS: int = 8192
    
    # 定义安全边界常量
    START_TIME_SAFETY_MARGIN_SEC = 0.4
    ANALYSIS_INTERVAL_SEC = 0.5

    # --- LLM 语音内容审查 Prompt (集大成版：字数校验 + 混合拆分 + 导演指令 + 结束收尾) ---
    LLM_PROMPT_FILTER_SPEECH: str = (
        "你是一位电商视频剪辑专家，任务是**精准删除无效片段，保留所有正式商品内容**。\n\n"
        
        "**核心原则 (最高优先级)**: \n"
        "1. **保留原则 (Retention Principle)**: \n"
        "   - **宁错勿漏**：任何看似是产品名、品牌名、Slogan、专业术语的词（即使发音不标准、含糊或类似乱码），**必须保留**。\n"
        "   - **正文保护**：带有口音的英语、中式英语、语速极快或极慢的商品介绍，只要是在介绍产品，**必须保留**。\n"
        "   - **短语保护**：短促的有力表达（如'买它！'、'超值！'、'看这里'），**必须保留**。\n"
        "2. **内容驱动判断**：只根据文字内容分类，忽略时间长度。\n"
        "3. **绝对删除**：只有当你**100%确定**这是导演指令、穿帮废话或纯噪音时，才标记为无效。\n\n"
        
        "**必须删除的无效内容 (`invalid_content`)**:\n"
        "1. **拍摄准备/结束**:\n"
        "   - 开场: '3,2,1', 'Action', '开始', '准备好了吗', '镜头OK吗'\n"
        "   - 结尾: '好', '停', '收工', '过了', '拜拜', 'OK', '这样就行', '零', '卡'\n"
        "2. **现场技术调整**:\n"
        "   - 声音问题: '声音太小了', '麦克风没声', '音量调大点'\n"
        "   - 画面问题: '手指遮挡镜头', '画面抖动', '对焦不准', '光线太暗'\n"
        "   - 重新拍摄: '再来一遍', '重新开始', '这条废了', '再来一条'\n"
        "3. **场外沟通/干扰**:\n"
        "   - 团队沟通: '导播切画面', '运营看数据', '助理准备样品', '翻一下过来'\n"
        "   - 环境干扰: '隔壁在装修', '手机静音', '家里孩子哭了'\n"
        "4. **口语冗余 (仅限纯废话)**:\n"
        "   - 纯填充词: 单独出现的 '呃', '啊', '嗯'（若夹杂在正文中则保留）\n"
        "   - 明确修正: '不是不是', '等等我重说', '刚才说错了'\n\n"
        
        "**必须保留的有效内容 (`valid_content`)**:\n"
        "- 所有正式商品介绍（中/英/多语种/方言）\n"
        "- 产品卖点、价格说明、使用演示\n"
        "- 促销信息、用户见证、品牌故事\n"
        "- 情感表达: '太棒了！', '绝对值得！', '买它！'\n"
        "- **重要**: 即使内容很短或听起来像乱码（可能是专用名词），只要不是明确的无效指令，一律保留。\n\n"
        
        "**混合内容处理 (最简规则)**:\n"
        "- 如果一句话**同时包含**无效前缀和有效商品内容：\n"
        "  • 优先删除无效前缀部分\n"
        "  • 保留商品介绍部分\n"
        "  • 拆分点：在无效词结束处自然分割\n"
        "- **例外**: 如果删除后剩余内容<1秒，**整句保留**（避免碎片化）\n\n"
        
        "**输入格式**: `[时间范围] 字幕文本`\n"
        "**输出格式**: 严格JSON数组，包含 `start_sec`, `end_sec`, `type`, `content`\n\n"
        
        "### 🌟 专业示例\n"
        "**输入1 (准备+正式内容)**:\n"
        "00:00:00,100 --> 00:00:05,500\n"
        "3,2,1...好嘞大家看这个 watch, it's waterproof!\n\n"
        "**输出1**:\n"
        "```json\n"
        "[\n"
        "  {\n"
        "    \"start_sec\": 0.1,\n"
        "    \"end_sec\": 1.8,\n"
        "    \"type\": \"invalid_content\",\n"
        "    \"content\": \"3,2,1...好嘞大家看这个 watch,\"\n"
        "  },\n"
        "  {\n"
        "    \"start_sec\": 1.8,\n"
        "    \"end_sec\": 5.5,\n"
        "    \"type\": \"valid_content\",\n"
        "    \"content\": \"it's waterproof!\"\n"
        "  }\n"
        "]\n"
        "```\n\n"
        
        "**输入2 (结尾收场)**:\n"
        "00:00:12,300 --> 00:00:15,800\n"
        "好了，今天的介绍就到这里，大家记得点击购买！\n\n"
        "**输出2**:\n"
        "```json\n"
        "[\n"
        "  {\n"
        "    \"start_sec\": 12.3,\n"
        "    \"end_sec\": 13.9,\n"
        "    \"type\": \"invalid_content\",\n"
        "    \"content\": \"好了，今天的介绍就到这里，\"\n"
        "  },\n"
        "  {\n"
        "    \"start_sec\": 13.9,\n"
        "    \"end_sec\": 15.8,\n"
        "    \"type\": \"valid_content\",\n"
        "    \"content\": \"大家记得点击购买！\"\n"
        "  }\n"
        "]\n"
        "```\n\n"
        
        "### ✅ 执行保障 \n"
        "- **简单优先**: 只判断内容类型，不计算精确时间\n"
        "- **安全兜底**: 任何不确定的内容归类为 `valid_content`\n"
        "- **异常处理**: 遇到格式错误时返回原始时间段+`invalid_content`类型"
    )

    # --- 视觉描述 Prompt (强调动作力度和测试术语，用于匹配) ---
    VISION_ANALYSIS_PROMPT_DESC: str = (
        "你是一位专业的媒体资产分析师。你的任务是为给定的视频帧生成一段精准的描述，分为两部分：\n"
        "1.  **客观描述**: 严格按照“主体-动作-场景-镜头”的结构，描述画面的客观内容。**特别注意描述动作的力度（如：剧烈翻滚、用力撞击、静止不动）。**\n"
        "2.  **商业意图**: 根据画面内容，推断这个镜头最可能想展示的产品卖点或商业信息。**如果画面是产品测试，请务必使用准确的测试术语（如'暴力测试', '耐久性实验', '防水测试'）。**\n\n"
        "**格式要求**: 必须严格遵循以下格式，用' || '作为分隔符。\n"
        "[客观描述] || [商业意图]\n\n"
        "**示例1 - 画面：一个行李箱在滚筒里翻滚**\n"
        "一个银色行李箱正在一个大型滚筒机器中持续剧烈翻滚，不断撞击内壁，采用中景镜头。 || 意图：展示行李箱的耐磨、抗摔和结构坚固特性，属于【暴力测试】和【耐久性实验】。\n\n"
        "**示例2 - 画面：一个男人站在行李箱上跳**\n"
        "一位男士正在纯白背景的演播室中站在一个行李箱上进行跳跃，箱面略微下陷但迅速回弹，采用中景镜头。 || 意图：展示行李箱的超强承重能力和坚固性。\n\n"
        "**示例3 - 画面：机械臂反复拉伸拉杆**\n"
        "一个行李箱的拉杆正在被机械臂反复、快速地拉伸和收回，采用特写镜头。 || 意图：展示拉杆的顺滑度和耐久性（疲劳测试）。"
    )

    # --- 特征提取 Prompt (结构化拆分为 Actions 和 Objects，用于匹配) ---
    VISION_ANALYSIS_PROMPT_FEATURES: str = (
        "你是一位顶级商业广告导演。请分析这帧画面，提取用于**精准视频检索**的原子标签。\n"
        "**提取规则（非常重要）**：\n"
        "1. **visual_actions (视觉动作)**: 画面中正在发生的**物理运动**。必须是动词。区分动作的力度（如：'撞击' vs '触摸'，'翻滚' vs '滑动'）。如果是静止画面，请填'静止'。\n"
        "2. **visual_objects (关键物体)**: 画面中除产品外，最显眼的道具、机器或环境物体（如：'滚筒机', '跑步机', '水珠', '锤子'）。\n"
        "3. **visual_style (视觉风格)**: 光影、构图或氛围（如：'特写', '慢动作', '工业风', '纯净背景'）。\n"
        "**特别强调**:\n"
        "- 如果画面展示产品测试（如行李箱在滚筒中），必须识别测试类型：'暴力测试'、'耐久性实验'、'冲击测试'等\n"
        "- 必须捕捉动作力度：如'剧烈翻滚'、'高速撞击'、'反复冲击'等\n"
        "- 区分测试设备：'滚筒试验机'、'冲击试验台'、'承重测试仪'等\n"
        "**输出格式要求**: 必须只返回一个JSON对象，包含上述三个键，每个键的值都是字符串数组。\n"
        "**示例1 (箱子在滚筒里转)**:\n"
        "```json\n"
        "{\n"
        "  \"visual_actions\": [\"剧烈翻滚\", \"高速撞击\", \"反复跌落\", \"持续旋转\"],\n"
        "  \"visual_objects\": [\"滚筒试验机\", \"金属内壁\", \"测试设备\"],\n"
        "  \"visual_style\": [\"暴力测试\", \"工业级测试\", \"产品耐久性验证\"]\n"
        "}\n"
        "```\n"
        "**示例2 (箱子在传送带上跑)**:\n"
        "```json\n"
        "{\n"
        "  \"visual_actions\": [\"高速滑动\", \"持续滚动\", \"模拟行走\"],\n"
        "  \"visual_objects\": [\"传送带\", \"测试平台\"],\n"
        "  \"visual_style\": [\"耐久性测试\", \"使用场景模拟\"]\n"
        "}\n"
        "```\n"
        "请现在开始分析你看到的画面，并只返回一个JSON对象。"
    )
    
    # --- 功能1：素材预处理所需的质量评估阈值 ---
    QUALITY_SHAKINESS_THRESHOLD: float = 35.0
    
    # [保持 0.0] 彻底禁用模糊检测，防止误删工业/运动画面
    QUALITY_BLUR_THRESHOLD: float = 0.0  
    
    QUALITY_BLUR_NOTE_THRESHOLD: float = 15.0 
    QUALITY_BLUR_SCORE_NORMALIZER: float = 60.0
    
    # [保持 5.0] 防止误删暗光工业场景
    QUALITY_BLACK_SCREEN_THRESHOLD: float = 5.0

    # --- 功能2：智能匹配所需的最低分数阈值 ---
    MATCH_SCORE_THRESHOLD: float = 0.15

    # --- 文件与路径配置 ---
    VIDEO_EXTENSIONS: tuple = ('.mp4', '.mov', '.mkv')
    
    # 默认输出是9:16,1080P
    TARGET_SIZE = (1080, 1920) 
    
    # 路径管理
    WORKFLOW_BASE_OUTPUT_DIR: str = field(init=False)
    analysis_cache_dir: str = field(init=False)
    run_output_dir: str = field(init=False)
    run_temp_dir: str = field(init=False)
    run_debug_dir: str = field(init=False)
    run_final_output_dir: str = field(init=False)
    run_filtered_assets_dir: str = field(init=False)

    def __post_init__(self):
        project_root = utils.get_project_root()
        if not project_root:
            raise EnvironmentError("项目根目录未找到，无法初始化WorkflowConfig。")

        # 1. 定义基础输出目录
        self.WORKFLOW_BASE_OUTPUT_DIR = os.path.join(project_root, 'workflow_output')
        
        # 2. 定义共享资源路径
        db_dir = os.path.dirname(self.db_path)
        self.analysis_cache_dir = os.path.join(self.WORKFLOW_BASE_OUTPUT_DIR, "analysis_cache")
        
        # 3. 定义本次运行的专属路径
        self.run_output_dir = os.path.join(self.WORKFLOW_BASE_OUTPUT_DIR, 'runs', self.task_id)
        self.run_temp_dir = os.path.join(self.run_output_dir, "temp")
        self.run_debug_dir = os.path.join(self.run_output_dir, "debug_info")
        self.run_final_output_dir = os.path.join(self.run_output_dir, "final_output")
        self.run_filtered_assets_dir = os.path.join(self.run_output_dir, "filtered_assets")

        # 4. 创建所有必要的目录
        os.makedirs(self.run_temp_dir, exist_ok=True)
        os.makedirs(self.run_debug_dir, exist_ok=True)
        os.makedirs(self.run_final_output_dir, exist_ok=True)
        os.makedirs(self.run_filtered_assets_dir, exist_ok=True)
        os.makedirs(db_dir, exist_ok=True)
        os.makedirs(self.analysis_cache_dir, exist_ok=True)

class ConfigManager:
    def __init__(self):
        self.project_root = utils.get_project_root()
        if not self.project_root:
            raise EnvironmentError("项目根目录未找到，无法初始化ConfigManager。")
        self.db_path = os.path.join(self.project_root, 'workflow_output', "db", "commercial_assets.db")

    def create_run_config(self, asset_dirs: List[str], task_id: Optional[str] = None) -> WorkflowConfig:
        """为一次新的运行创建专属配置对象"""
        utils.print2(f"构建新的运行配置, 资产目录: {asset_dirs}")
        
        if torch.cuda.is_available():
            properties = torch.cuda.get_device_properties(0)
            vram_gb = properties.total_memory / (1024 ** 3)
            dtype = "bf16" if properties.major >= 8 and torch.cuda.is_bf16_supported() else "fp16"
            
            # 🚀 [H20 极致吞吐优化] 根据显存大小智能设定极高并发 Batch Size
            if vram_gb >= 90: # Targeting H20 (141G) / H100 / A100 80G
                clip_batch_size = 192
            elif vram_gb >= 22: # Targeting 24GB cards like 4090/4090D
                clip_batch_size = 48
            elif vram_gb >= 16:
                clip_batch_size = 32
            else:
                clip_batch_size = 16
        else:
            dtype = "auto"
            clip_batch_size = 8
        
        config_data = {
            "asset_dirs": asset_dirs,
            "db_path": self.db_path,
            "task_id": task_id if task_id else str(uuid.uuid4())[:8],
            "VISION_LLM_TORCH_DTYPE": dtype,
            # 仅将动态计算的 batch_size 用于 CLIP
            "CLIP_BATCH_SIZE": clip_batch_size, 
        }
        
        config_instance = WorkflowConfig(**config_data)
        
        utils.print2(f"配置构建完成: Run ID='{config_instance.task_id}', DB='{os.path.basename(config_instance.db_path)}'")
        utils.print2(f"  - 本次运行的所有输出将保存在: {config_instance.run_output_dir}")
        return config_instance

_global_config_manager_instance: Optional[ConfigManager] = None

def get_config_manager() -> ConfigManager:
    global _global_config_manager_instance
    if _global_config_manager_instance is None:
        _global_config_manager_instance = ConfigManager()
    return _global_config_manager_instance
