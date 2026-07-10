import re
import time
import os
import sys
import json

try:
    import dashscope as dashscope
except ModuleNotFoundError as exc:
    missing_pkg = getattr(exc, "name", "dashscope")
    raise SystemExit(
        "缺少运行依赖："
        f"{missing_pkg}\n"
        "请先在项目目录执行：\n"
        "python -m pip install -r requirements.txt\n"
        "如果你有多套 Python，请先确认当前解释器：\n"
        "python -c \"import sys; print(sys.executable)\""
    ) from exc

from config import API_Key_QW
try:
    from Search_content import *
    from Search_profession import *
except ModuleNotFoundError as exc:
    missing_pkg = getattr(exc, "name", "未知依赖")
    raise SystemExit(
        "缺少运行依赖："
        f"{missing_pkg}\n"
        "请先在项目目录执行：\n"
        "python -m pip install -r requirements.txt\n"
        "若仍报错，请检查是否用了错误的 Python 解释器：\n"
        "python -c \"import sys; print(sys.executable)\""
    ) from exc

from humor_levels.humor_level_generator import generate_humor_level_versions


MYTH_TARGET_TOTAL_MIN = 6500
MYTH_TARGET_TOTAL_SOFT_MAX = 8500
MYTH_TARGET_TOTAL_MAX = 9000
MYTH_ACT_TARGETS = {
    "act1": (1400, 1700),
    "act2": (3600, 4200),
    "act3": (1400, 1700),
}
MYTH_CORE_CONSTRAINTS_FILENAME = 'myth_core_constraints_revised.json'
MYTH_CORE_CONSTRAINTS_FALLBACK_FILENAME = 'myth_core_constraints.json'
MYTH_THREAD_PROTAGONIST_FILENAME = 'myth_thread_protagonist_constraints.json'

BAD_META_PHRASES = [
    "[因原文长度限制未能全部提供]",
    "未完待续",
    "欢迎提出进一步请求",
    "若您有兴趣了解更多详情",
    "下面是故事",
    "参考内容如下",
    "本故事到此结束",
    "[此时应",
    "典型的互动场景",
    "此处插入",
    "符合要求",
    "画面要素",
    "感情线渐进",
    "推动主题",
    "插入对白互动",
    "隐藏章节",
    "此处暂留",
    "暂留下",
    "实际书写时不显示",
    "不显示这段备注",
    "TODO",
    "待补",
    "待完善",
    "待续写",
    "这段大约",
    "多少字左右",
    "接下来便是",
    "下一节的内容",
    "接下来是下一节",
    "遥远角落",
    "节拍卡",
    "節拍卡",
    "目标达成",
    "目標達成",
    "此处隐含",
    "此处隱含",
    "隐含感情",
    "隱含感情",
    "勾勒",
    "伏笔",
    "伏筆",
    "（完毕）",
    "(完毕)",
    "完毕",
]

HARD_META_RESIDUE_TERMS = [
    "节拍卡",
    "節拍卡",
    "目标达成",
    "目標達成",
    "此处暂留",
    "此處暫留",
    "实际书写时不显示",
    "實際書寫時不顯示",
    "下一节",
    "下一節",
    "备注：",
    "備註：",
]

BAD_PLAN_TERMS = [
    "不明人士帮助信号",
    "神秘人暗中相助",
    "幕后之人",
    "灵魂交换转换修复工程",
    "修复工程",
    "紧急救助程序",
    "程序介入",
    "最大规模致命一击行为",
    "命运审判仪式",
    "超级火炬",
    "防护罩",
    "屏障显现",
    "外挂式助力系统",
    "工作机制",
    "星域",
    "工程",
    "机制",
    "系统",
]

PLAN_DRIFT_PATTERNS = [
    r'预知未来',
    r'预言[^，。；\n]{0,12}(鸟|猫|动物)',
    r'(鸟|猫|动物)[^，。；\n]{0,10}预言',
    r'演播厅|直播间|主持台|节目组',
    r'信心值|数值条|评分条|任务值|能量槽',
    r'外部援助|外援介入|请来帮手|临时帮手|隐藏支援',
    r'系统提示|程序介入|修复工程|任务面板',
]

BODY_DRIFT_PATTERNS = [
    r'演播厅|直播间|主持台|节目组',
    r'信心值|数值条|评分条|任务值|能量槽',
    r'系统提示|程序介入|修复工程|任务面板',
    r'预知未来',
    r'预言[^，。；\n]{0,12}(鸟|猫|动物)',
    r'(鸟|猫|动物)[^，。；\n]{0,10}预言',
    r'不明人士帮助信号|神秘人暗中相助|幕后之人',
    r'外部援助|外援介入|请来帮手|临时帮手|隐藏支援',
    r'党风廉政|反腐败|社会主义|中国特色社会主义|中国梦|民族复兴|中国人民|人民群众',
    r'全面建成小康社会|国家治理体系|依法治国|法治政府|一带一路|人类命运共同体',
    r'政治生态|国际地位|大国关系|联合国宪章|脱贫攻坚|蓝天碧水净土保卫战',
]

MYTH_CORE_CONSTRAINTS_CACHE = None
MYTH_THREAD_PROTAGONIST_CACHE = None

TRADITIONAL_TO_SIMPLIFIED = str.maketrans({
    "負": "负", "責": "责", "連": "连", "劍": "剑", "飛": "飞", "昇": "升",
    "賓": "宾", "臉": "脸", "紅": "红", "脖": "脖", "漲": "涨", "氣": "气",
    "惱": "恼", "閉": "闭", "這": "这", "關": "关", "鍵": "键", "時": "时",
    "風": "风", "聲": "声", "漸": "渐", "強": "强", "雲": "云", "層": "层",
    "壓": "压", "漢": "汉", "鐘": "钟", "離": "离", "狀": "状", "別": "别",
    "鬧": "闹", "騰": "腾", "還": "还", "麼": "么", "過": "过", "張": "张",
    "邊": "边", "擦": "擦", "額": "额", "懷": "怀", "裡": "里", "摸": "摸",
    "東": "东", "啥": "啥", "説": "说", "術": "术", "業": "业", "專": "专",
    "攻": "攻", "嘆": "叹", "裡": "里", "該": "该", "檢": "检", "裝": "装",
    "遠": "远", "處": "处", "傳": "传", "轟": "轰", "鳴": "鸣", "龍": "龙",
    "宮": "宫", "經": "经", "察": "察", "覺": "觉", "異": "异", "動": "动",
    "準": "准", "備": "备", "動": "动", "態": "态", "來": "来", "們": "们",
    "調": "调", "整": "整", "塵": "尘", "國": "国", "舅": "舅", "喃": "喃",
    "語": "语", "師": "师", "傅": "傅", "實": "实", "話": "话", "擔": "担",
    "會": "会", "變": "变", "魚": "鱼", "蝦": "虾", "類": "类", "動": "动",
    "物": "物", "麼": "么", "沒": "没", "帶": "带", "什": "什", "麼": "么",
    "與": "与", "萬": "万", "絲": "丝", "嚴": "严", "個": "个", "豐": "丰",
    "臨": "临", "麗": "丽", "舉": "举", "樂": "乐", "鄉": "乡", "書": "书",
    "買": "买", "亂": "乱", "爭": "争", "於": "于", "亞": "亚", "產": "产",
    "畢": "毕", "寧": "宁", "眾": "众", "優": "优", "傢": "家", "價": "价",
    "億": "亿", "債": "债", "傷": "伤", "傾": "倾", "後": "后", "門": "门",
    "體": "体", "發": "发", "戰": "战", "愛": "爱", "頭": "头", "靜": "静",
    "場": "场", "顏": "颜", "顯": "显", "點": "点", "畫": "画", "聲": "声",
    "處": "处", "變": "变", "聽": "听", "聞": "闻", "問": "问", "應": "应",
    "對": "对", "開": "开", "閃": "闪", "現": "现", "壞": "坏", "萬": "万",
    "塊": "块", "葉": "叶", "樹": "树", "橋": "桥", "線": "线", "輕": "轻",
    "點": "点", "雙": "双", "寫": "写", "讀": "读", "韻": "韵", "觀": "观",
})
TRADITIONAL_TO_SIMPLIFIED.update(str.maketrans({
    "難": "难", "嗎": "吗", "當": "当", "從": "从", "讓": "让", "總": "总",
    "覺": "觉", "見": "见", "裏": "里", "爺": "爷", "爾": "尔", "為": "为",
    "爲": "为", "擋": "挡", "護": "护", "藥": "药", "島": "岛", "臺": "台",
    "灣": "湾", "衝": "冲", "沖": "冲", "殺": "杀", "給": "给", "網": "网",
    "卻": "却", "剛": "刚", "幾": "几", "無": "无", "應": "应", "種": "种",
    "尋": "寻", "將": "将", "隻": "只", "趕": "赶", "頂": "顶", "腳": "脚",
    "歸": "归", "點": "点", "淚": "泪", "復": "复", "蘇": "苏", "餘": "余",
    "雜": "杂", "塵": "尘", "彎": "弯", "斷": "断", "穩": "稳", "擺": "摆",
    "驚": "惊", "嘯": "啸", "濤": "涛", "滾": "滚", "濕": "湿", "滿": "满",
    "間": "间", "帶": "带", "鮮": "鲜", "撲": "扑", "歡": "欢", "進": "进",
    "戲": "戏", "著": "着", "鬆": "松", "熱": "热", "講": "讲", "簡": "简",
    "誤": "误", "確": "确", "圍": "围", "極": "极", "標": "标", "並": "并",
    "懼": "惧", "險": "险", "關": "关", "曬": "晒", "邁": "迈", "節": "节",
    "躍": "跃", "慌": "慌", "蹤": "踪", "舊": "旧", "隨": "随", "區": "区",
}))

META_RESIDUE_PATTERNS = [
    r'[（(][^）)]{0,80}(这段大约|多少字左右|接下来便是|下一节|实际书写|不显示|隐藏章节|待补|节拍卡|目标达成|隐含|勾勒|伏笔|备注|插入)[^）)]{0,120}[）)]',
    r'[（(]\s*完毕\s*[）)]',
    r'[（(]此时此刻[^）)]{0,120}[）)]',
    r'这段大约[^。！？\n]{0,40}(字|字左右)',
    r'(接下来便是|接下来是)[^。！？\n]{0,40}(下一节|下个小节|下一段)',
    r'遥远角落[^。！？\n]{0,80}(默默注视|注视他们|背影)',
    r'与此同时一位看似[^。！？\n]{0,120}角色[^。！？\n]{0,120}叫做[^。！？\n]{0,80}',
]


def has_hard_meta_residue(text: str) -> bool:
    """
    硬检测正文中的生成过程残留。命中时应判为不合格并触发重写，
    不依赖后处理删除来掩盖问题。
    """
    if not text:
        return False
    normalized = normalize_language_pollution(text)
    return any(term in normalized for term in HARD_META_RESIDUE_TERMS)


def _knowledge_base_path(filename: str) -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    primary = os.path.join(current_dir, 'knowledgeBase', filename)
    if os.path.exists(primary):
        return primary
    return os.path.join('knowledgeBase', filename)


def load_myth_core_constraints() -> dict:
    """
    加载神话故事核心主旨约束。
    这份文件不是相似样本，而是生成前必须优先遵守的故事骨架。
    """
    global MYTH_CORE_CONSTRAINTS_CACHE
    if MYTH_CORE_CONSTRAINTS_CACHE is not None:
        return MYTH_CORE_CONSTRAINTS_CACHE

    path = _knowledge_base_path(MYTH_CORE_CONSTRAINTS_FILENAME)
    if not os.path.exists(path):
        print(f"警告：未找到 {MYTH_CORE_CONSTRAINTS_FILENAME}，将回退使用 {MYTH_CORE_CONSTRAINTS_FALLBACK_FILENAME}。")
        path = _knowledge_base_path(MYTH_CORE_CONSTRAINTS_FALLBACK_FILENAME)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        global_constraints = data.get("global_constraints", {})
        stories = []
        for story in data.get("stories", []):
            story_copy = dict(story)
            story_copy["_global_constraints"] = global_constraints
            stories.append(story_copy)
        MYTH_CORE_CONSTRAINTS_CACHE = {
            "stories": stories,
            "by_title": {story.get("title", ""): story for story in stories if story.get("title")},
            "source_file": os.path.basename(path),
            "global_constraints": global_constraints,
        }
        return MYTH_CORE_CONSTRAINTS_CACHE
    except FileNotFoundError:
        print(f"警告：未找到 {MYTH_CORE_CONSTRAINTS_FILENAME} 或 {MYTH_CORE_CONSTRAINTS_FALLBACK_FILENAME}，神话核心主旨约束不会生效。")
    except Exception as e:
        print(f"加载神话核心主旨约束时出错: {e}")

    MYTH_CORE_CONSTRAINTS_CACHE = {"stories": [], "by_title": {}}
    return MYTH_CORE_CONSTRAINTS_CACHE


def load_thread_protagonist_constraints() -> dict:
    """
    加载十八篇神话的贯穿主人公约束。
    该文件只提供串线人物的出场功能和禁区，不覆盖原神话核心事件链。
    """
    global MYTH_THREAD_PROTAGONIST_CACHE
    if MYTH_THREAD_PROTAGONIST_CACHE is not None:
        return MYTH_THREAD_PROTAGONIST_CACHE

    path = _knowledge_base_path(MYTH_THREAD_PROTAGONIST_FILENAME)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        protagonist = data.get("protagonist", {})
        stories = []
        for story in data.get("stories", []):
            story_copy = dict(story)
            story_copy["_protagonist"] = protagonist
            stories.append(story_copy)
        MYTH_THREAD_PROTAGONIST_CACHE = {
            "protagonist": protagonist,
            "stories": stories,
            "by_title": {story.get("title", ""): story for story in stories if story.get("title")},
            "source_file": os.path.basename(path),
        }
        return MYTH_THREAD_PROTAGONIST_CACHE
    except FileNotFoundError:
        print(f"警告：未找到 {MYTH_THREAD_PROTAGONIST_FILENAME}，串线主人公约束不会生效。")
    except Exception as e:
        print(f"加载串线主人公约束时出错: {e}")

    MYTH_THREAD_PROTAGONIST_CACHE = {"protagonist": {}, "stories": [], "by_title": {}}
    return MYTH_THREAD_PROTAGONIST_CACHE


def find_thread_protagonist_constraint(story_title: str) -> dict:
    if not story_title:
        return {}
    data = load_thread_protagonist_constraints()
    return data.get("by_title", {}).get(story_title, {})


def find_myth_core(prompt: str) -> dict:
    """
    根据用户提示词匹配当前要改写的神话。
    优先精确匹配标题和别名，避免 RAG 相似样本把故事串库。
    """
    if not prompt:
        return {}
    data = load_myth_core_constraints()
    for story in data.get("stories", []):
        names = [story.get("title", "")] + story.get("aliases", [])
        if any(name and name in prompt for name in names):
            story_copy = dict(story)
            thread_constraint = find_thread_protagonist_constraint(story_copy.get("title", ""))
            if thread_constraint:
                story_copy["_thread_protagonist"] = thread_constraint
            return story_copy
    return {}


def format_thread_protagonist_block(thread_constraint: dict) -> str:
    if not thread_constraint:
        return ""

    protagonist = thread_constraint.get("_protagonist", {})
    name = protagonist.get("name", "串线主人公")

    def _lines(label, values):
        if not values:
            return ""
        return label + "\n" + "\n".join(f"- {item}" for item in values)

    parts = [
        "【贯穿十八篇的串线主人公硬约束（优先级高于RAG样本和临场发挥）】",
        f"串线主人公：{name}",
        f"固定身份：{protagonist.get('full_identity', '')}",
        f"十八篇体系功能：{protagonist.get('series_purpose', '')}",
        _lines("固定性格：", protagonist.get("personality", [])),
        f"总规则：{protagonist.get('core_rule', '')}",
        _lines("固定道具：", protagonist.get("fixed_props", [])),
        _lines("体系必含短语：", protagonist.get("global_required_phrases", [])),
        _lines("可用于跨篇连接的神话词：", protagonist.get("continuity_terms", [])),
        _lines("十八篇体系串联规则：", protagonist.get("continuity_rules", [])),
        _lines("全局必须遵守：", protagonist.get("global_must", [])),
        _lines("全局禁止：", protagonist.get("global_forbidden", [])),
        f"本篇出场功能：{thread_constraint.get('role', '')}",
        _lines("本篇必须写出的动作/话语/态度：", thread_constraint.get("must_do", [])),
        _lines("本篇推荐使用的跨篇连接/旧经历回忆梗（至少自然使用其中一类或自拟同等级跨篇连接）：", thread_constraint.get("callback_options", [])),
        _lines("本篇串线主人公禁区：", thread_constraint.get("forbidden", [])),
        _lines("成稿中至少命中的串线短语：", thread_constraint.get("required_phrases", [])),
        "写作要求：阿满必须自然嵌入当前神话主线，提供幽默、记录和见证；同时必须把当前神话放入《山海十八简》的十八篇体系里，至少用一处短促跨篇回忆、类比或伏笔连接其他神话。但当前神话原主角必须亲自完成核心行动，阿满不得抢走主线或改变结局。",
    ]
    return "\n".join(part for part in parts if part)


def format_myth_core_block(myth_core: dict) -> str:
    if not myth_core:
        return ""

    def _lines(label, values):
        if not values:
            return ""
        return label + "\n" + "\n".join(f"- {item}" for item in values)

    required_actions = myth_core.get("required_character_actions", {})
    required_actions_block = ""
    if required_actions:
        required_actions_block = "角色必做动作：\n" + "\n".join(
            f"- {name}：{action}" for name, action in required_actions.items()
        )

    global_constraints = myth_core.get("_global_constraints", {})
    guards = global_constraints.get("quality_guards", {}) if isinstance(global_constraints, dict) else {}
    guard_lines = []
    for guard_name in (
        "no_meta_text",
        "language_cleaning",
        "helper_role_rule",
        "humor_rule",
        "emotion_rule",
        "cross_story_contamination_rule",
        "completeness_check_rule",
    ):
        values = guards.get(guard_name, [])
        if values:
            guard_lines.extend(f"- {item}" for item in values)
    global_guard_block = "【全局质量守卫】\n" + "\n".join(guard_lines) if guard_lines else ""
    canonical_terms = myth_core.get("canonical_terms", {})
    canonical_block = ""
    if isinstance(canonical_terms, dict) and canonical_terms:
        canonical_block = "固定名称/身份/道具称呼（全文必须一致）：\n" + "\n".join(
            f"- {name}：{value}" for name, value in canonical_terms.items()
        )
    forbidden_aliases = myth_core.get("forbidden_aliases", {})
    forbidden_alias_block = ""
    if isinstance(forbidden_aliases, dict) and forbidden_aliases:
        forbidden_alias_block = "禁止混用的错名/异名：\n" + "\n".join(
            f"- {name}：{', '.join(values)}" for name, values in forbidden_aliases.items() if values
        )
    object_rules = myth_core.get("object_consistency", [])
    if isinstance(object_rules, dict):
        object_rules = [object_rules]
    object_rule_lines = []
    for rule in object_rules or []:
        if not isinstance(rule, dict):
            continue
        allowed = "、".join(rule.get("allowed_forms", []))
        forbidden = "、".join(rule.get("forbidden_forms", []))
        line = f"- {rule.get('name', '核心道具')}：允许形态为 {allowed or '已设定形态'}"
        if forbidden:
            line += f"；禁止写成 {forbidden}"
        object_rule_lines.append(line)
    object_rule_block = "核心道具一致性：\n" + "\n".join(object_rule_lines) if object_rule_lines else ""
    thread_protagonist_block = format_thread_protagonist_block(myth_core.get("_thread_protagonist", {}))

    parts = [
        "【本篇神话主题主旨硬约束（优先级高于RAG样本和幽默扩写）】",
        f"故事名：{myth_core.get('title', '')}",
        f"核心主旨：{myth_core.get('core_summary', '')}",
        _lines("必须保留的核心事件链：", myth_core.get("event_chain", [])),
        _lines("成稿必须写出的识别点：", myth_core.get("must_include", [])),
        _lines("成稿最终验收必须明确写出的关键短语/意象：", myth_core.get("final_required_phrases", [])),
        _lines("禁止改写成的错误方向：", myth_core.get("must_not_change", [])),
        _lines("本故事专属禁区词/禁区情节：", myth_core.get("forbidden_elements", [])),
        _lines("本故事专属禁用表达模式：", myth_core.get("forbidden_patterns", [])),
        canonical_block,
        forbidden_alias_block,
        object_rule_block,
        thread_protagonist_block,
        required_actions_block,
        f"扩写边界：{myth_core.get('expansion_guidance', '')}",
        global_guard_block,
        "如果参考样本、旧稿、大纲或幽默梗与以上约束冲突，必须舍弃参考样本和旧稿，以本篇神话核心主旨为准。",
    ]
    return "\n".join(part for part in parts if part)


def build_core_fallback_plan(prompt: str, myth_core: dict) -> dict:
    """
    当模型规划阶段连续产出空节拍或跑偏节拍时，按核心事件链生成可执行兜底三幕。
    兜底稿不追求花哨，但能保证后续正文生成贴住主线。
    """
    title = myth_core.get("title") or prompt or "神话故事"
    chain = [item for item in myth_core.get("event_chain", []) if item]
    if not chain:
        chain = myth_core.get("must_include", [])[:6] or [title]

    shennong_humor_channels = [
        "试药反差：神农严肃判断味道或药性，身体反应立刻拆他的台",
        "村民误解：旁观者把试药、记药误会成品菜、蘸料、偏方买卖或奇怪仪式",
        "辅助翻车：阿喜/随从想帮忙，叼来或递来的东西反而暴露自己的小心思",
        "药性命名：神农给草药取临时记名，名字像严肃记录但听起来很想笑",
        "严肃记录与狼狈状态反差：他边吐边写，记录语气越端正，画面越狼狈",
        "互怼拆台：辅助角色只负责补一刀，不得连续承包所有笑点",
    ]
    kunpeng_humor_channels = [
        "小鱼误解：小鱼按北冥日常误读鲲的远志，笑点短促，不打断宏大画面",
        "古风旁观反差：旁观者把大鹏的影子误当成山、云或天漏了一块",
        "阿浪嘴硬：阿浪前期短促拆台，中期震惊，后期沉默认可，不连续抢戏",
        "尺度反差：用普通生活尺度衡量鲲鹏的巨大，随即被海天景象推翻",
        "命名反差：旁观者试图用朴素称呼记录大鹏，称呼越小，画面越大",
        "风势误解：众人以为六月大风是阻碍，鲲鹏悟到那正是托举之力",
    ]
    generic_humor_channels = [
        "动作反差：宏大目标配一个具体狼狈小动作",
        "旁观误解：路人按生活经验误读主角的神话行动",
        "道具翻车：关键道具被误用、卡住或出现尴尬后果",
        "命名/记录梗：角色用过分认真或过分朴素的说法记录当下",
        "嘴硬自嘲：主角用一句轻描淡写掩饰压力",
        "互怼拆台：辅助角色短促接梗，不连续抢戏",
    ]
    if "神农" in title or "尝百草" in title:
        humor_channels = shennong_humor_channels
    elif "北冥鲲鹏" in title or "鲲鹏" in title:
        humor_channels = kunpeng_humor_channels
    else:
        humor_channels = generic_humor_channels

    def _outline(events, role):
        joined = "；".join(events)
        return f"{title}{role}必须围绕核心事件推进：{joined}。所有扩展只补足人物动机、道具状态、压力来源、动作过程、情绪变化和贴着主线的笑点。幽默不能只靠辅助角色互怼，必须让试错过程、旁观误解、道具状态、记录/命名反差共同制造笑点；辅助角色只能见证、短促拆台或轻微翻车，不能替代主角完成核心选择。"

    if title == "后羿射日":
        def _beat(goal, visual, emotion, info, ban, humor, foreshadow="阿满的青竹简从怕被晒坏，到最后郑重写下“射九留一”", relation="阿满只记录、吐槽和见证；后羿始终亲自完成射日与留一日的选择"):
            return {
                "场景目标": goal,
                "画面要素": visual,
                "情绪推动": emotion,
                "信息增量": info,
                "禁止项": ban,
                "情感伏笔": foreshadow,
                "关系推进": relation,
                "幽默机制": humor,
            }

        act1_beats = [
            _beat(
                "建立十日并出的灾情与阿满到场记录",
                "十个太阳同时压在天上；阿满抱着青竹简用袖子给竹简遮阳",
                "狼狈→清醒",
                "明确灾因是十日并出，大地焦灼，阿满只是来记录灾情",
                "不得提前射日；不得写战斗、敌人、神秘外援；不得出现现代时间和现代道具",
                "记录反差：阿满认真写灾情，字刚落下就差点被晒得翘边",
            ),
            _beat(
                "展示百姓受难与求救压力",
                "干裂井口、空陶罐、蔫倒的庄稼；百姓围向后羿求救",
                "清醒→焦急",
                "新增百姓为何非后羿不可，不重复十日景象",
                "不得写成普通围观热闹；不得让阿满替百姓做决定",
                "旁观误解：村民把阿满的青竹简当遮阳板借用",
            ),
            _beat(
                "后羿确认救民目标与弓箭状态",
                "后羿检查弓弦、箭羽和箭袋；阿满躲在弓影下记“弓还能用”",
                "焦急→决断",
                "明确核心道具是弓和箭，后羿决定亲自救民",
                "不得新增护身符、匕首、酒葫芦水源奇迹等无关道具；不得让小徒弟抢戏",
                "道具反差：阿满以为弓影能乘凉，风一吹影子先跑了",
            ),
            _beat(
                "登高前的短暂筹备与阿满随行",
                "后羿背箭上山；阿满一手护青竹简一手追脚步",
                "决断→吃力",
                "新增登高原因：站上高处才能面对十日",
                "不得在山下直接开射；不得重复百姓求救",
                "动作反差：后羿登高如走平地，阿满把每一级石阶都记成劫难",
            ),
            _beat(
                "抵达山顶并直面十日",
                "山顶热浪扭曲；十日分布在天幕，后羿辨认射击顺序",
                "吃力→凝神",
                "明确下一幕要按顺序射落九日，并留下一个太阳",
                "不得一口气写完射日；不得让太阳躲云层玩捉迷藏",
                "嘴硬自嘲：阿满说若写错顺序，青竹简先替他中暑",
            ),
        ]
        act2_beats = [
            _beat("后羿开弓射落第一个太阳", "后羿站稳、搭箭、拉满弓；第一个太阳中箭坠落，热浪退一层", "凝神→震动", "必须明确第一箭射落第一日", "不得跳到第七日；不得写第一箭失败；不得让阿满影响命中", "一抛一接：阿满刚写“第一箭很稳”，汗滴把“稳”洇成“烫”"),
            _beat("射落第二个太阳并稳定众人信心", "第二箭穿过刺目白光；百姓从恐惧转为敢抬头", "震动→振奋", "必须明确第二箭射落第二日，世界略有变化", "不得把多个太阳模糊写成陆续消失；不得新增怪物或逃跑太阳", "旁观误解：老人以为天上少了一个火炉，问能不能先搬去做饭"),
            _beat("射落第三个太阳，后羿开始显露体力代价", "第三箭离弦；后羿虎口渗血，肩背被热浪压住", "振奋→咬牙", "新增后羿救民要付出体力和伤痛", "不得写阿满替后羿递神箭；不得写护身符帮助射击", "嘴硬自嘲：后羿说手还没废，阿满记成“暂时没废”"),
            _beat("连续射落第四到第六个太阳，但每一箭都要有动作和结果", "第四箭压低火云、第五箭穿过热浪、第六箭震落焦灰；地面裂缝不再冒烟", "咬牙→稳住", "必须明确第四、第五、第六日被射落，不得一句带过", "不得出现顺序倒退；不得把第五个太阳写成逃走又重来", "记录反差：阿满写到第六个时开始给箭数打结，嘴上还硬说自己很清醒"),
            _beat("面对剩下四日，后羿调整呼吸和射击节奏", "后羿放低弓臂喘息；阿满护住青竹简提醒已射落六日", "稳住→再决断", "承接前六日已落，只为后三箭蓄势", "不得重写第一箭；不得开启无关村民偷蓑衣、蚂蚁搬叶等支线", "短对白拆台：阿满提醒“还有三个要射，一个要留”，自己差点把留字写成溜"),
            _beat("射落第七个太阳", "第七箭擦过滚烫云边；第七日坠落时热风反扑", "再决断→吃痛", "必须明确第七日被射落，并写出反扑压力", "不得把第七日写成开篇；不得写第十日先动", "动作反差：阿满被反扑热风吹得后退，仍先检查青竹简有没有少一页"),
            _beat("射落第八个太阳", "后羿换步、压肩、拉弦；第八日坠落后天空露出缝隙", "吃痛→逼近终点", "必须明确第八日被射落，剩下两个太阳", "不得让第八日躲藏成新支线；不得引入新法宝", "旁观误解：孩童数天上火球数到打嗝，阿满严肃纠正又把自己数乱"),
            _beat("射落第九个太阳，留下最后抉择", "第九箭最沉；第九日落下后只剩最后一个太阳悬在天上", "逼近终点→沉静", "必须明确射落九日已经完成，转入是否射最后一日的选择", "不得把十日全灭；不得说太阳全部消失；不得在此结束全篇", "记录反差：阿满准备写“完工”，看见最后一个太阳又把字划掉"),
            _beat("第二幕收束：后羿压下最后一箭，没有立刻射出", "后羿箭尖对准最后一日又缓缓放下；百姓屏息等待", "沉静→克制", "明确第三幕主题是留下一日的克制，不是继续战斗", "不得射掉最后一个太阳；不得让阿满劝他射或替他决定", "嘴硬余味：阿满小声问这算不算“最难的一箭是没射出去”"),
        ]
        act3_beats = [
            _beat("建立留下最后一个太阳的争议", "百姓有人害怕最后一日继续炙烤；后羿看见远处仍需光照的土地", "克制→承压", "解释为什么不能射掉最后一个太阳", "不得写成漏靶；不得让村民以为任务失败作为主线", "旁观误解：有人问是不是少带一支箭，阿满捂着青竹简不敢笑太大声"),
            _beat("后羿明确作出留一日的选择", "后羿收弓，箭尖离开最后太阳；阿满准备郑重记录", "承压→坚定", "必须明确后羿主动留下最后一日，不是射不中或太阳逃走", "不得再开射；不得让阿满或百姓替他决定", "记录反差：阿满写“留下一日”，写完才发现这四个字比射九日还难"),
            _beat("天地温度回落，灾情开始缓解", "热风变凉、井口返潮、田埂冒出湿气；百姓从躲藏中出来", "坚定→松弛", "展示天地恢复正常的可感后果", "不得突然出现雷电、火灾或新灾难；不得用泛泛总结代替画面", "动作反差：阿满试探青竹简不再烫手，像试药一样谨慎"),
            _beat("百姓反应与后羿疲惫收束", "百姓感谢后羿；后羿手臂发抖仍站稳", "松弛→敬重", "新增后羿付出代价，但不写死亡或复活", "不得硬煽情长篇总结；不得开启妻子支线", "短促幽默：后羿说先别谢，谁有水先借一口"),
            _beat("阿满写下射九留一，完成串线主人公功能", "阿满摊开青竹简，郑重写下“后羿射落九日，留下一日”；汗印留在竹简边缘", "敬重→余韵", "必须命中阿满、青竹简、射九留一或射落九日留下一日", "不得把阿满写成主角；不得让阿满发表大道理", "记录梗回收：阿满说这回终于不是青竹简被晒熟，而是自己差点熟了"),
            _beat("结尾：一日照常升起，世界恢复秩序", "唯一的太阳温和照着土地；孩子在溪边笑，庄稼舒展叶片", "余韵→安定", "明确后羿射日故事讲完：十日之灾结束，天地恢复秩序", "不得出现未完待续；不得新增下一篇神话主线", "嘴硬型余味：阿满看着太阳，先摸竹简温度再敢落最后一笔"),
        ]
        return {
            "act1": _outline(["十日并出", "大地焦灼百姓受难", "后羿决定救民", "阿满到场记录"], "第一幕"),
            "act2": _outline(["后羿登高面对十日", "按顺序射落第一至第九个太阳", "留下最后一日的选择被推到眼前"], "第二幕"),
            "act3": _outline(["后羿主动留下最后一个太阳", "天地恢复正常", "阿满写下射九留一的记录"], "第三幕"),
            "act1_beats": act1_beats,
            "act2_beats": act2_beats,
            "act3_beats": act3_beats,
        }

    if title == "北冥鲲鹏":
        def _beat(goal, visual, emotion, info, ban, humor, foreshadow="阿浪的嘲笑逐渐变轻，老龟的沉默成为见证", relation="阿浪从调侃转为惊愕，主角始终自己完成选择"):
            return {
                "场景目标": goal,
                "画面要素": visual,
                "情绪推动": emotion,
                "信息增量": info,
                "禁止项": ban,
                "情感伏笔": foreshadow,
                "关系推进": relation,
                "幽默机制": humor,
            }

        act1_beats = [
            _beat(
                "建立北冥深处巨鲲存在与狭小感",
                "北冥深海压暗如夜；鲲翻身只让海水起伏，不开始化鹏",
                "烦闷→不甘",
                "只交代鲲为何觉得北冥容不下自己的心，不写变身",
                "不得写北海；不得让阿浪解释设定；不得出现岸边码头货船",
                "小鱼误解：小鱼把鲲的远志当成睡醒翻身",
            ),
            _beat(
                "确认鲲想离开北冥的动机",
                "鲲仰望海面微光；老龟只说一句古老传闻",
                "不甘→清醒",
                "新增鲲知道南冥天池存在，但尚未起飞",
                "不得提前展翼；不得写南冥已经抵达",
                "尺度反差：小鱼用浅滩大小衡量鲲的梦想",
            ),
            _beat(
                "加压北冥众生的嘲笑与误解",
                "阿浪绕着鲲的鳍游一圈；小鱼把鲲的影子误认成山壁",
                "清醒→决断",
                "新增外界声音越小越碎，反衬鲲的心越大",
                "不得让阿浪连续长篇吐槽；不得新增风灵子等外援",
                "阿浪嘴硬：短促拆台，但不抢主线",
            ),
            _beat(
                "鲲作出化鹏选择",
                "鲲沉入更深处再缓缓上升；鳞光转为羽光的第一丝征兆",
                "决断→忍痛",
                "只写化鹏的不可逆选择开始，不写完整展翼",
                "不得重复开篇苏醒；不得写身体恐怖、腐烂、异物",
                "嘴硬自嘲：鲲用一句轻话压住痛楚",
            ),
            _beat(
                "执行鳞化羽的第一阶段",
                "鳞片边缘亮起羽纹；海水被新生气息推开",
                "忍痛→稳住",
                "新增变化方向是鳞化羽，不是怪物变异",
                "不得写掉渣烂肉；不得说这就成了",
                "古风旁观反差：旁观者把羽光误当月色落海",
            ),
            _beat(
                "第一幕余波：鲲尚未成鹏，但已不能退回旧身",
                "北冥海面第一次被背影顶开；阿浪声音变小",
                "稳住→期待",
                "明确下一阶段要等待真正托举它的六月大风",
                "不得完整起飞；不得写南冥结尾",
                "风势误解：众人把风当前兆，鲲知道它可能是路",
            ),
        ]
        act2_beats = [
            _beat("建立化鹏第二阶段：背若泰山", "鲲背从海中隆起如山；海水沿羽纹分流", "期待→紧张", "推进到背部成鹏形，不重复第一幕鳞化羽", "不得再写鲲刚刚睁眼；不得重启北冥开头", "尺度反差：渔人误认海上多了一座山"),
            _beat("确认鹏翼初成但尚不能飞", "两翼只展开一半；风压把浪头压低", "紧张→克制", "新增翅膀太大，必须学会承风而非硬挣", "不得说已经飞往南冥；不得让旁人帮它飞", "命名反差：旁观者给巨翼取小名，立刻显得可笑"),
            _beat("加压：巨翼触风失衡", "风撞上羽端；鲲被压回浪间但没有散形", "克制→咬牙", "新增失败原因是逆风硬飞，不是力量不足", "不得写成坠落事故闹剧；不得身体恐怖", "阿浪嘴硬：想笑却被浪声噎住"),
            _beat("决断：鲲明白要等六月大风", "老龟看天色不解释；鲲听见海底长风回响", "咬牙→明悟", "明确六月大风不是普通风，是天地托举之力", "不得写成东风、飓风、天气事故", "风势误解：众人以为是阻碍，鲲听出是路"),
            _beat("执行：鹏翼若垂天之云", "双翼完整舒展遮住海天；云影垂落北冥", "明悟→庄重", "首次明确众生看见的是鹏翼若垂天之云", "不得多次重复同一句展翼；不得再称只是巨鱼", "古风旁观反差：有人以为天低了一截"),
            _beat("余波：鲲的新身份被确认", "羽影覆盖海面；阿浪仰头半晌才低声叫出大鹏", "庄重→震动", "明确鲲已化为鹏，但仍未远徙", "不得回头再写化鹏过程；不得重新长鳞脱鳞", "阿浪嘴硬转沉默：只剩一句很轻的认可"),
            _beat("六月大风自北冥深处起", "海底长风翻起；巨翼不再抵抗而是张开承接", "震动→顺势", "新增风开始托举大鹏离水", "不得把大风写成灾难主角；不得新增外援角色", "风势误解：小鱼以为要被吹丢，结果看见大鹏上升"),
            _beat("乘风离开北冥边界", "大鹏背负青天升起；下方嘲笑声变小如泡沫", "顺势→开阔", "推进到离开北冥，不直接抵达南冥", "不得停在原地围观；不得写打败谁", "尺度反差：旧日笑声在高空里小得可怜"),
            _beat("第二幕收束：南冥天池成为清晰方向", "天际出现南方水光；大鹏调整翼势向南", "开阔→笃定", "明确下一幕目标是飞往南冥天池", "不得只写模糊远方；不得在此结束全篇", "嘴硬自嘲：阿浪不敢再笑，只说别飞错方向"),
        ]
        act3_beats = [
            _beat("建立远徙：大鹏已在高空", "北冥海面退成一片暗光；南方天际浮现水色", "笃定→辽阔", "不再写化鹏，只写徙南冥的飞行开始", "不得回到海底重写变身；不得再写北海", "古风旁观反差：众人把远影误认成云在迁徙"),
            _beat("确认六月大风持续托举", "大风托住翼根；大鹏不再挣扎而是借势上升", "辽阔→自在", "强化风是天地递来的第一程路", "不得写成总结作文；不得说动力源泉", "风势误解：阿浪终于不把风当灾"),
            _beat("加压：北冥旧声音远去", "下方嘲笑声小成浪沫；大鹏没有回头争辩", "自在→释然", "主题转向离开狭小尺度，而非证明给谁看", "不得让阿浪高频吐槽；不得开启新冲突", "阿浪沉默认可：只用一个动作回应"),
            _beat("决断：大鹏向南冥天池定向远举", "南冥天池水光如镜；大鹏收束翼尖转向南方", "释然→坚定", "明确飞行终点是南冥天池", "不得停在飞起来；不得只写南冥所在", "命名反差：渔民再也找不到合适的小称呼"),
            _beat("执行：越过北冥与南冥之间的长空", "云层从翼下退去；青天压在背上却不再沉重", "坚定→逍遥", "写出背负青天、逍遥远举的动作过程", "不得重复翼若垂天之云；不得写新设定", "尺度反差：山河在翼下缩成一线"),
            _beat("余波收束：徙于南冥天池", "大鹏掠向南冥天池；北冥众生只见云影远去", "逍遥→余韵", "必须明确它乘六月大风向南冥天池飞去，完成核心闭环", "不得出现（完毕）；不得停在众人仰望", "嘴硬型余味：阿浪低声认可，不再抢戏"),
        ]
        return {
            "act1": _outline(["北冥巨鲲存在", "鲲决定化而为鸟"], "第一幕"),
            "act2": _outline(["鲲化为大鹏", "鹏翼若垂天之云", "乘六月大风而起"], "第二幕"),
            "act3": _outline(["背负青天远举", "飞往南冥天池", "呈现逍遥精神"], "第三幕"),
            "act1_beats": act1_beats,
            "act2_beats": act2_beats,
            "act3_beats": act3_beats,
        }

    if title == "伏羲画卦":
        def _beat(goal, visual, emotion, info, ban, humor, foreshadow="族人从不解到愿意倾听，伏羲的孤独逐渐被理解", relation="辅助角色只能误解、见证或递上材料，不能替伏羲领悟八卦"):
            return {
                "场景目标": goal,
                "画面要素": visual,
                "情绪推动": emotion,
                "信息增量": info,
                "禁止项": ban,
                "情感伏笔": foreshadow,
                "关系推进": relation,
                "幽默机制": humor,
            }

        act1_beats = [
            _beat("建立洪荒部落对自然无序的困惑", "风雨忽至、猎路迷失、族人按直觉争吵；伏羲在旁记录变化", "焦灼→沉思", "交代伏羲为什么必须寻找天地规律", "不得写成算命摊；不得写现代玄学课", "旁观误解：族人以为伏羲在记谁偷吃了粮"),
            _beat("确认伏羲主动观察天地万物", "伏羲仰观天象、俯察水纹、追看鸟兽足迹，把线条刻在泥板上", "沉思→专注", "明确伏羲是观察者和记录者，不是被人直接送答案", "不得让外人送八卦成品", "动作反差：伏羲严肃观天，脚下却踩进泥坑"),
            _beat("加压族人看不懂符号而嘲笑", "孩子把短横长横当柴火账，老人催他去修篱笆", "专注→受挫", "写出八卦雏形尚未成体系，众人不理解", "不得把八卦写成 gossip 闲聊", "命名/记录梗：族人给符号取很朴素的小名"),
            _beat("决断去河边寻找河洛之象", "伏羲带着龟甲、泥板和绳结沿河而行；水声与星光互相映照", "受挫→坚定", "伏羲不是逃避嘲笑，而是继续验证观察", "不得新增女娲客串主导；不得改成寻宝冒险", "嘴硬自嘲：伏羲说自己不是发呆，是在等天地开口"),
            _beat("执行看见龙马负图或河图显现", "龙马自河雾中现身，背负纹理；水面同心波与星点相合", "坚定→震撼", "核心神迹出现，但伏羲只得到启发，不得到成品八卦", "不得写成龙马直接教会八卦", "旁观误解：族人先关心这马能不能拉车"),
            _beat("第一幕余波：伏羲开始把河图与万物观察相互印证", "伏羲伏在岸边拓纹，泥水满袖；族人的笑声渐低", "震撼→求证", "转入下一幕的推演：河图只是引子，阴阳变化需要伏羲亲自悟出", "不得第一幕就完整画出八卦", "道具翻车：龟甲滑进水里又被捞回"),
        ]
        act2_beats = [
            _beat("建立推演难点：河图纹理无法直接解释万物", "泥板摆满短长线、圆点和绳结；伏羲反复对照昼夜寒暑", "求证→困惑", "说明八卦不是抄图，而是从现象中抽象规律", "不得写成成品说明书", "动作反差：伏羲越排越庄重，泥板越像一锅乱粥"),
            _beat("确认阴阳雏形来自相反相成", "日影移动、水流分合、鸟群一散一聚；伏羲划出一实一虚两种线", "困惑→微明", "新增阴阳不是口号，而是由相反现象归纳出来", "不得写成现代物理课", "旁观误解：族人以为他在给柴火分粗细"),
            _beat("加压第一次解释失败", "伏羲向族人展示两种线，众人听得满脸茫然，有人拿它当捕兽记号", "微明→受阻", "写出知识从个人领悟到公共理解之间有阻力", "不得变成算命招揽客人", "互怼拆台：辅助角色只短促吐槽听不懂"),
            _beat("决断继续观察四时与方位", "伏羲冒雨看雷，迎风辨向，在晨昏之间校对线条", "受阻→坚持", "扩展到天、地、雷、风、水、火、山、泽等自然类别", "不得串入补天、造人、射日等其他神话主线", "嘴硬自嘲：他说被雨浇透也算被天地亲自批注"),
            _beat("执行把阴阳线组合成多个卦象", "龟甲上实线断线层层相叠，伏羲用骨针刻出不同组合", "坚持→成形", "明确伏羲亲手组合符号，八卦逐渐成形", "不得让老匠人或外援替他画卦", "道具翻车：骨针折了，他把折痕也拿来比对"),
            _beat("加压材料损坏与众人误会", "雨水冲散泥板，孩童误把卦象踩成脚印，伏羲重新整理", "成形→濒临崩溃", "失败不是重启剧情，而是逼伏羲把规律记得更准", "不得重复龙马第一次出现；不得写正文污染提示", "旁观误解：孩子以为自己一脚踩出了新学问"),
            _beat("确认八种卦象的秩序", "乾坤震巽坎离艮兑依次落位，伏羲把它们同天地万象对应", "濒临崩溃→明朗", "第一次完整确认八卦名称和基本对应关系", "不得写成村口闲聊八卦", "命名/记录梗：族人嫌名字难记，伏羲用自然画面解释"),
            _beat("执行用八卦解释一次现实难题", "风向变、云压低、河水涨，伏羲据卦提醒族人避开低地", "明朗→被看见", "让八卦的文明意义先通过具体事件显出用处", "不得变成彩票预测、姻缘占卜", "动作反差：最不信的人抱着锅跑得最快"),
            _beat("第二幕余波：族人开始愿意听伏羲讲解", "雨后部落无恙，众人围着龟甲安静下来", "被看见→期待", "转入第三幕公开画卦和建立秩序", "不得在第二幕结束全篇", "互怼拆台：辅助角色嘴硬说自己只是怕锅被淹"),
        ]
        act3_beats = [
            _beat("建立公开画卦的场面", "祭土铺平，龟甲置中，族人围成半圈；伏羲洗净手上的泥", "期待→庄重", "从个人推演转为公开传授", "不得写成算命摊开张", "动作反差：孩子小声问这些线能不能先画直一点"),
            _beat("确认伏羲亲手画出八卦", "伏羲一笔一划画下乾坤震巽坎离艮兑，短线长线各归其位", "庄重→完成", "核心行动必须由伏羲亲自完成", "不得由龙马、老匠人、外人替他完成", "命名/记录梗：族人努力跟读卦名读得磕绊"),
            _beat("加压最后的质疑：这些符号到底有何用", "有人问符号能否挡雨、能否生粮；伏羲把卦象指向天时地利", "完成→解释", "把抽象符号转化为人们能理解的自然秩序", "不得泛泛说大家明白了道理", "旁观误解：族人先把卦象当农具摆放图"),
            _beat("执行人们借八卦理解自然", "老人据风雷知道何时避雨，猎人据山泽辨路，农人据寒暑安排播种", "解释→信服", "必须写出八卦如何帮助人理解自然和人事", "不得只写众人震惊；不得停在符号好看", "动作反差：先前笑得最大声的人记得最认真"),
            _beat("决断把八卦传给部落后人", "伏羲把刻好的龟甲交给族中少年，又在泥板上反复示范", "信服→传承", "文明意义落到共享知识，而不是个人炫耀", "不得写成现代课程培训", "嘴硬型温柔：辅助角色说自己不是服了，只是不想再被雨淋"),
            _beat("余波收束：从混沌经验到可解释秩序", "部落夜里有火光与记录声，风雨仍来，但人们不再只靠恐惧判断", "传承→余韵", "结尾落到伏羲画卦开启人们理解自然、人事与秩序", "不得出现完毕、关注点赞等正文污染", "克制轻笑：孩子把卦线画歪，伏羲笑着重新扶正"),
        ]
        return {
            "act1": _outline(["伏羲观察天地万物", "见龙马负图或河洛之象"], "第一幕"),
            "act2": _outline(["从昼夜寒暑、水火动静中悟出阴阳变化", "亲手组合卦象"], "第二幕"),
            "act3": _outline(["伏羲画出八卦", "人们借八卦理解自然、人事与秩序"], "第三幕"),
            "act1_beats": act1_beats,
            "act2_beats": act2_beats,
            "act3_beats": act3_beats,
        }

    act1_events = chain[: max(2, min(3, len(chain) // 3 or 2))]
    act3_events = chain[-2:] if len(chain) >= 4 else chain[-1:]
    middle_start = len(act1_events)
    middle_end = max(middle_start, len(chain) - len(act3_events))
    act2_events = chain[middle_start:middle_end] or chain[1:-1] or chain

    def _make_beats(events, target_count, phase):
        if not events:
            events = [title]
        angles = [
            ("建立", "交代来龙去脉与当下压力"),
            ("确认", "明确关键道具/行动目标的状态与代价"),
            ("加压", "让外部阻力或旁观反应逼近主线选择"),
            ("决断", "让核心人物做出本阶段不可跳过的选择"),
            ("执行", "分解新的动作步骤，不复述上一拍已完成动作"),
            ("余波", "展示后果并自然转入下一阶段"),
        ]
        beats = []
        for i in range(target_count):
            event = events[min(i * len(events) // target_count, len(events) - 1)]
            goal_prefix, angle = angles[min(i, len(angles) - 1)]
            humor_channel = humor_channels[i % len(humor_channels)]
            beats.append({
                "场景目标": f"{goal_prefix}{phase}核心节点：{event}；本拍只写{angle}",
                "画面要素": f"{event}的一个新动作、一个新压力来源、核心人物的具体身体/表情反应；预留一个非对白反差画面",
                "情绪推动": "不安→清醒" if phase == "第一幕" else ("紧张→决断" if phase == "第二幕" else "痛惜→余韵"),
                "信息增量": f"只新增{event}在本阶段的一个因果信息，不重复上一拍已经完成的动作",
                "禁止项": "不得新增无关支线、不得让辅助角色抢走核心行动、不得重复描写上一拍已经完成的藏匿/出发/执行动作",
                "情感伏笔": "保留一个与核心人物关系相关的小动作或小物件",
                "关系推进": "核心人物关系随主线压力加深，辅助角色只作见证",
                "幽默机制": humor_channel,
            })
        return beats

    return {
        "act1": _outline(act1_events, "第一幕"),
        "act2": _outline(act2_events, "第二幕"),
        "act3": _outline(act3_events, "第三幕"),
        "act1_beats": _make_beats(act1_events, 6, "第一幕"),
        "act2_beats": _make_beats(act2_events, 9, "第二幕"),
        "act3_beats": _make_beats(act3_events, 6, "第三幕"),
    }


def contains_myth_core_violation(text: str, myth_core: dict) -> bool:
    if not text or not myth_core:
        return False
    forbidden = myth_core.get("forbidden_elements", [])
    if any(term and term in text for term in forbidden):
        return True
    forbidden_patterns = myth_core.get("forbidden_patterns", [])
    for pattern in forbidden_patterns or []:
        if not pattern:
            continue
        try:
            if re.search(pattern, text):
                return True
        except re.error:
            if pattern in text:
                return True
    forbidden_aliases = myth_core.get("forbidden_aliases", {})
    if isinstance(forbidden_aliases, dict):
        for _canonical, aliases in forbidden_aliases.items():
            if any(alias and alias in text for alias in aliases):
                return True
    object_rules = myth_core.get("object_consistency", [])
    if isinstance(object_rules, dict):
        object_rules = [object_rules]
    for rule in object_rules or []:
        if not isinstance(rule, dict):
            continue
        for form in rule.get("forbidden_forms", []):
            if form and form in text:
                return True
    return False


def myth_core_required_sequence_met(text: str, myth_core: dict) -> bool:
    """
    检查关键短语是否按原神话事件链的方向出现。
    用于拦截“先写南冥，再反复回头化鹏”这类结构重启。
    """
    if not text or not myth_core:
        return True
    sequence = myth_core.get("required_sequence", [])
    if not sequence:
        return True
    cursor = -1
    for term in sequence:
        if not term:
            continue
        pos = text.find(term, cursor + 1)
        if pos < 0:
            return False
        cursor = pos
    return True


def myth_core_required_hit_count(text: str, myth_core: dict, field: str = "must_include") -> int:
    if not text or not myth_core:
        return 0
    return sum(1 for term in myth_core.get(field, []) if term and term in text)


def myth_core_final_phrases_met(text: str, myth_core: dict) -> bool:
    """
    比 must_include 更严格的成稿验收项。
    must_include 适合做标题识别与规划提示；final_required_phrases 用来锁住
    原典关键意象、终点或身份确认，避免单字词造成假阳性。
    """
    if not text or not myth_core:
        return True
    required = myth_core.get("final_required_phrases", [])
    if not required:
        return True
    min_hits = myth_core.get("min_final_required_phrase_hits")
    if min_hits is None:
        min_hits = len(required)
    return myth_core_required_hit_count(text, myth_core, "final_required_phrases") >= min_hits


def myth_core_requirement_met(text: str, myth_core: dict, final: bool = False) -> bool:
    if not myth_core:
        return True
    field = "must_include"
    required = myth_core.get(field, [])
    if not required:
        return True

    if final:
        min_hits = myth_core.get("min_final_required_hits")
        if min_hits is None:
            min_hits = max(2, min(len(required), (len(required) + 1) // 2))
    else:
        min_hits = myth_core.get("min_plan_required_hits")
        if min_hits is None:
            min_hits = max(1, min(3, len(required)))
    return myth_core_required_hit_count(text, myth_core, field) >= min_hits


def thread_protagonist_required_hit_count(text: str, myth_core: dict) -> int:
    if not text or not myth_core:
        return 0
    thread_constraint = myth_core.get("_thread_protagonist", {})
    required = thread_constraint.get("required_phrases", []) if isinstance(thread_constraint, dict) else []
    return sum(1 for term in required if term and term in text)


def thread_protagonist_external_terms(myth_core: dict) -> list:
    if not myth_core:
        return []
    thread_constraint = myth_core.get("_thread_protagonist", {})
    if not thread_constraint:
        return []
    protagonist = thread_constraint.get("_protagonist", {})
    continuity_terms = [term for term in protagonist.get("continuity_terms", []) if term]
    if not continuity_terms:
        return []

    local_terms = set()
    for term in [myth_core.get("title", "")] + myth_core.get("aliases", []):
        if term:
            local_terms.add(term)
    for term in myth_core.get("must_include", []) or []:
        if term:
            local_terms.add(term)
    for term in myth_core.get("final_required_phrases", []) or []:
        if term:
            local_terms.add(term)
    for term in thread_constraint.get("required_phrases", []) or []:
        if term:
            local_terms.add(term)

    external_terms = []
    for term in continuity_terms:
        if term in local_terms:
            continue
        if any(term in local for local in local_terms):
            continue
        external_terms.append(term)
    return external_terms


def thread_protagonist_system_requirement_met(text: str, myth_core: dict) -> bool:
    if not text or not myth_core:
        return True
    thread_constraint = myth_core.get("_thread_protagonist", {})
    if not thread_constraint:
        return True
    protagonist = thread_constraint.get("_protagonist", {})

    global_required = protagonist.get("global_required_phrases", [])
    if global_required and not any(term and term in text for term in global_required):
        return False

    external_terms = thread_protagonist_external_terms(myth_core)
    if external_terms and not any(term in text for term in external_terms):
        return False

    return True


def thread_protagonist_requirement_met(text: str, myth_core: dict) -> bool:
    if not myth_core:
        return True
    thread_constraint = myth_core.get("_thread_protagonist", {})
    if not thread_constraint:
        return True
    required = thread_constraint.get("required_phrases", [])
    if not required:
        return True
    min_hits = thread_constraint.get("min_required_phrase_hits")
    if not isinstance(min_hits, int):
        min_hits = len(required)
    return (
        thread_protagonist_required_hit_count(text, myth_core) >= min_hits
        and thread_protagonist_system_requirement_met(text, myth_core)
    )


def contains_thread_protagonist_violation(text: str, myth_core: dict = None) -> bool:
    if not text or not myth_core:
        return False
    thread_constraint = myth_core.get("_thread_protagonist", {})
    if not thread_constraint:
        return False

    for term in thread_constraint.get("forbidden", []) or []:
        if term and term in text:
            return True

    protagonist = thread_constraint.get("_protagonist", {})
    for term in protagonist.get("global_forbidden", []) or []:
        if term and term in text:
            return True

    # 这些是串线主人公最容易被模型写偏的硬禁区，使用短模式单独拦截。
    forbidden_patterns = [
        r'阿满[^。！？\n]{0,30}(射箭|射日|补天|炼石|画出八卦|发明文字|捏出人|尝百草|搭鹊桥|砍倒桂树)',
        r'阿满[^。！？\n]{0,30}(替|代替|帮)[^。！？\n]{0,20}(后羿|女娲|伏羲|仓颉|神农|愚公|精卫|吴刚)[^。！？\n]{0,20}(完成|解决)',
        r'阿满[^。！？\n]{0,30}(系统|玩家|穿越者|现代人|直播|手机|电脑|导航)',
    ]
    return any(re.search(pattern, text) for pattern in forbidden_patterns)


def houyi_story_quality_met(text: str, myth_core: dict = None) -> bool:
    """
    后羿射日专属验收：
    - 必须能看出按顺序射落九日，而不是跳号、倒叙或一团乱写
    - 必须主动留下最后一个太阳
    - 必须出现阿满的记录功能，而不是只让阿满反复狼狈出场
    """
    if not text or not myth_core or myth_core.get("title") != "后羿射日":
        return True

    forbidden_terms = [
        "备胎", "午后三点", "三点钟", "烽燧塔", "缰绳", "护身符", "玄铁匕首",
        "酒葫芦竟莫名", "水源奇迹", "鸡冠羽饰", "药膳包", "六十七只蚂蚁",
        "流浪狗", "现代战术", "战斗", "目标案例介绍",
    ]
    if any(term in text for term in forbidden_terms):
        return False

    required_core_groups = [
        ["十日并出"],
        ["大地焦灼", "百姓受难", "百姓遭殃", "干裂"],
        ["射落九日", "射落九个太阳", "九个太阳被射落", "后羿射落九日"],
        ["留下一日", "留下最后一个太阳", "留下一个太阳", "留下一轮太阳", "射九留一"],
        ["天地恢复", "恢复正常", "温度降", "重获清凉", "万物复苏"],
        ["阿满"],
        ["青竹简"],
    ]
    for group in required_core_groups:
        if not any(term in text for term in group):
            return False

    ordered_marks = [
        ["第一箭", "第一日", "第一个太阳", "第一枚太阳"],
        ["第二箭", "第二日", "第二个太阳", "第二枚太阳"],
        ["第三箭", "第三日", "第三个太阳", "第三枚太阳"],
        ["第四箭", "第四日", "第四个太阳", "第四枚太阳"],
        ["第五箭", "第五日", "第五个太阳", "第五枚太阳"],
        ["第六箭", "第六日", "第六个太阳", "第六枚太阳"],
        ["第七箭", "第七日", "第七个太阳", "第七枚太阳"],
        ["第八箭", "第八日", "第八个太阳", "第八枚太阳"],
        ["第九箭", "第九日", "第九个太阳", "第九枚太阳"],
    ]
    positions = []
    for group in ordered_marks:
        group_positions = [text.find(term) for term in group if term in text]
        if not group_positions:
            return False
        positions.append(min(pos for pos in group_positions if pos >= 0))
    if positions != sorted(positions):
        return False

    final_choice_pos = min(
        [text.find(term) for term in ["留下一日", "留下最后一个太阳", "留下一个太阳", "留下一轮太阳", "射九留一"] if term in text]
        or [-1]
    )
    ninth_pos = positions[-1]
    if final_choice_pos < ninth_pos:
        return False

    # 阿满必须承担“记录射九留一”的功能，而不只是围观喊热。
    record_patterns = [
        r'阿满[^。！？\n]{0,80}(青竹简|竹简)[^。！？\n]{0,80}(射九留一|射落九日|留下一日|留下最后一个太阳)',
        r'(射九留一|射落九日|留下一日|留下最后一个太阳)[^。！？\n]{0,80}阿满[^。！？\n]{0,80}(青竹简|竹简)',
    ]
    if not any(re.search(pattern, text) for pattern in record_patterns):
        return False

    return True


THREAD_BRIDGE_FALLBACKS = {
    "八仙过海": "阿满把这一简夹进《山海十八简》时，还特地在页角补了一笔：后羿那边是太阳多得烫手，八仙这边是海水多得下不了笔，自己这个小史官大概天生和“太多”犯冲。",
    "北冥鲲鹏": "阿满抱着青竹简，把北冥这一页郑重题进《山海十八简》；他想起八仙过海时见过风浪，可眼前这风浪像忽然长出翅膀，连他的旧笔都想先飞一步。",
    "仓颉造字": "阿满把这一段收入《山海十八简》时，忽然想起神农尝百草那页自己差点把“苦”写成“哭”，便对仓颉多生出几分敬意：没有文字，连写错都没机会。",
    "嫦娥奔月": "阿满在《山海十八简》里翻到后羿射日那页，指腹还记得当时的热；如今月光冷下来，他的旧笔忽然不敢乱抖，怕把分离写得太响。",
    "伏羲画卦": "阿满把伏羲画卦收入《山海十八简》，又想起仓颉造字那一简：字能记事，可这些长短横线像天地自己打的结，光会写字还真不一定解得开。",
    "后羿射日": "阿满把后羿射日记作《山海十八简》里最烫手的一简，顺手在旁边留了个小注：以后若轮到夸父追日，自己一定先把青竹简泡凉，免得还没开跑，字先熟了。",
    "精卫填海": "阿满把精卫这一简夹进《山海十八简》，想起八仙过海时海浪只是热闹，这里的海浪却像专门抬杠；他数不清木石，只好先记下那份不肯停。",
    "夸父追日": "阿满喘着把追日写进《山海十八简》，还翻到后羿射日那页嘀咕：那边是太阳太多，这边是太阳太会跑，自己夹在中间，只剩两条腿最讲道理。",
    "雷泽华胥": "阿满把雷泽这一页收入《山海十八简》时，想起后来伏羲画卦的线条，心里一紧：有些故事不是从一句话开始，而是从一个大到写不下的足迹开始。",
    "梁山伯与祝英台": "阿满把梁祝这一简收入《山海十八简》，想起牛郎织女那页也写过分隔；他难得没急着吐槽，只把青竹简合了合，像怕惊动纸上的两个人。",
    "孟姜女哭长城": "阿满把孟姜女这一简写进《山海十八简》，忽然想起精卫一石一石衔向东海；原来有些坚持不是为了显得厉害，只是不肯把心里那个人丢下。",
    "牛郎织女": "阿满把牛郎织女收入《山海十八简》时，翻到嫦娥奔月那页，月宫的冷和天河的远挤在一处，他便把玩笑收得很小，只敢让旧笔轻轻落下。",
    "女娲补天": "阿满把女娲补天写进《山海十八简》，又想起盘古开出的天地如今裂开一角，连忙护住青竹简：天地的事果然没有一页是轻松收尾的。",
    "女娲造人": "阿满把女娲造人收进《山海十八简》，还想起仓颉造字那页：人刚有了脚，还没来得及写自己的名字，已经把他的青竹简围得像赶集。",
    "神农尝百草": "阿满把神农尝百草写进《山海十八简》时，顺手翻到仓颉造字那页，心想文字真好用，只是遇到苦草和毒草，字也会跟着舌头发麻。",
    "吴刚伐桂": "阿满把吴刚伐桂记入《山海十八简》，又翻到嫦娥奔月那页；月宫的冷清原来不止一种，有人望着人间，有人每天把同一刀重新开始。",
    "西王母": "阿满在瑶池把这一页放进《山海十八简》，心里明白自己后来跑遍女娲、后羿、牛郎织女那些现场，多半就是从西王母一句“去见世面”开始的。",
    "愚公移山": "阿满把愚公移山写进《山海十八简》时，想起精卫填海那页，忽然不敢笑那些一天只多一点点的进度；有些故事慢得要命，却偏偏能把天地慢慢说服。",
}


def build_thread_bridge_fallback(myth_core: dict) -> str:
    if not myth_core:
        return ""
    title = myth_core.get("title", "")
    if title in THREAD_BRIDGE_FALLBACKS:
        return THREAD_BRIDGE_FALLBACKS[title]

    external_terms = thread_protagonist_external_terms(myth_core)
    external_hint = external_terms[0] if external_terms else "另一处神话现场"
    return (
        f"阿满抱着青竹简，把这一页郑重收进《山海十八简》。他在页角补了一句，"
        f"说这场事要和{external_hint}那一简前后相照，才看得出十八篇神话原来同在一片天地里。"
    )


def repair_thread_protagonist_system_link(text: str, myth_core: dict = None) -> str:
    if not text or not myth_core:
        return text
    thread_constraint = myth_core.get("_thread_protagonist", {})
    if not thread_constraint:
        return text

    needs_bridge = not thread_protagonist_system_requirement_met(text, myth_core)
    required = thread_constraint.get("required_phrases", []) or []
    missing_required = [term for term in required if term and term not in text]
    missing_global = []
    protagonist = thread_constraint.get("_protagonist", {})
    for term in protagonist.get("global_required_phrases", []) or []:
        if term and term not in text:
            missing_global.append(term)

    if not needs_bridge and not missing_required and not missing_global:
        return text

    bridge = build_thread_bridge_fallback(myth_core)
    if not bridge:
        return text
    print("正在补强串线主人公十八篇体系连接：《山海十八简》/跨篇回忆")

    lines = text.splitlines()
    insert_at = len(lines)
    for idx in range(len(lines) - 1, -1, -1):
        if "阿满" in lines[idx] or "青竹简" in lines[idx]:
            insert_at = idx + 1
            break
    lines.insert(insert_at, bridge)
    return "\n".join(lines)


def apply_myth_specific_postprocess(text: str, myth_core: dict = None) -> str:
    if not text or not myth_core:
        return text
    text = repair_thread_protagonist_system_link(text, myth_core)
    if myth_core.get("title") == "北冥鲲鹏":
        text = text.replace("北海深处", "北冥深处")
        text = text.replace("北海之上", "北冥之上")
        text = text.replace("北海下", "北冥下")
        text = re.sub(r'北海(?!道)', '北冥', text)
        if "向南冥天池飞去" not in text and "南冥天池" in text:
            text = re.sub(r'[\s。！？…]*$', '', text)
            text += "\n\n大鹏没有再回头。它乘着六月大风，越过北冥翻涌的海面，向南冥天池飞去。那些曾经笑它太大、太笨、太不安分的声音，终于小得像浪尖上的泡沫。"
    return text

def clean_markdown(text):
    """去除 Markdown 格式符号"""
    if not text:
        return ""
    # 基础 Markdown 清理
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # 去除 **
    text = re.sub(r'### (.*)', r'\1', text)       # 去除 ###
    text = re.sub(r'---', '', text)               # 去除 ---

    # 把模型偶尔输出的转义符号，恢复成正常文本换行 / 引号
    # 例如："\n" -> 实际换行，"\\\"" -> 普通引号
    text = text.replace('\\n', '\n')
    text = text.replace('\\"', '"')

    # 删除明显是"注释 / 说明"的尾部内容（如"注释：""注解："之后的部分）
    text = re.sub(r'(注释：|注解：)[\s\S]*$', '', text)
    text = remove_meta_residue(text)
    text = normalize_language_pollution(text)
    text = remove_meta_residue(text)

    # 折叠过多的空行：最多保留连续 2 个换行，避免极端空行
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def remove_meta_residue(text: str) -> str:
    """
    删除模型泄露到正文里的写作提示、字数说明和下一节提示。
    这些内容不是故事文本，宁可整段删除，也不要保留在成稿里污染样本。
    """
    if not text:
        return text

    for pattern in META_RESIDUE_PATTERNS:
        text = re.sub(pattern, '', text)

    # 删除单独成行或短句形式的生成说明。
    meta_line_patterns = [
        r'^[^\n]{0,20}(这段大约|多少字左右|接下来便是|下一节|实际书写|不显示|隐藏章节|待补|备注|插入)[^\n]{0,80}$',
        r'^[^\n]{0,20}(节拍卡|画面要素|情感伏笔|关系推进|信息增量|场景目标)[：:][^\n]{0,120}$',
    ]
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if any(re.search(pattern, stripped) for pattern in meta_line_patterns):
            continue
        lines.append(line)
    return "\n".join(lines)


def remove_body_drift_residue(text: str) -> str:
    """
    删除明显串出台词/主题的段落，尤其是现代政治宣传腔、系统工程腔等。
    这类内容宁可整段删除，也不能混入神话正文。
    """
    if not text:
        return text
    drift_patterns = BODY_DRIFT_PATTERNS + [
        r'绿色发展|循环经济|金山银山|现代化水平|获得感幸福感安全感',
        r'正能量|政治生态|社会稳定|国家安全|对外开放新格局',
    ]
    kept = []
    for block in re.split(r'(\n\s*\n)', text):
        if not block.strip() or re.fullmatch(r'\n\s*\n', block):
            kept.append(block)
            continue
        if any(re.search(pattern, block) for pattern in drift_patterns):
            continue
        kept.append(block)
    cleaned = "".join(kept)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned


def normalize_language_pollution(text: str) -> str:
    """
    统一清理语言污染：
    - 常见繁体字转简体
    - 删除俄文/希腊文等误入字符
    - 清理异常标点和中文之间的多余空格
    """
    if not text:
        return text

    text = text.translate(TRADITIONAL_TO_SIMPLIFIED)
    text = re.sub(r'[\u0370-\u03FF\u0400-\u052F]+', '', text)
    text = text.replace('「', '“').replace('」', '”').replace('『', '“').replace('』', '”')
    text = text.replace(' ,', '，').replace(', ', '，').replace(' .', '。')
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)
    text = re.sub(r'\s+([，。！？；：、])', r'\1', text)
    text = re.sub(r'([，。！？；：、])\s+', r'\1', text)
    text = re.sub(r'([，。！？；：、])\1{1,}', r'\1', text)
    text = re.sub(r'[ ]{2,}', ' ', text)
    return text


def contains_plan_drift(text: str, myth_core: dict = None) -> bool:
    """
    检测规划文本中的跑偏信号：
    - 系统化/工程化/综艺化表达
    - 预言型动物、神秘外援等与神话主线脱节的扩写模板
    """
    if not text:
        return False
    if contains_myth_core_violation(text, myth_core or {}):
        return True
    if any(term in text for term in BAD_PLAN_TERMS):
        return True
    return any(re.search(pattern, text) for pattern in PLAN_DRIFT_PATTERNS)


def contains_body_drift(text: str, myth_core: dict = None) -> bool:
    """
    检测正文中的跑偏信号：
    - 现代节目/数值系统/工程说明
    - 预言动物、神秘外援等未受控的新设定
    """
    if not text:
        return False
    if contains_myth_core_violation(text, myth_core or {}):
        return True
    if any(term in text for term in BAD_PLAN_TERMS):
        return True
    return any(re.search(pattern, text) for pattern in BODY_DRIFT_PATTERNS)


def fix_punctuation_and_paragraphs(text):
    """
    后处理函数：检测超长无标点段落并强制打断
    规则：
    - 检测超过120字且没有句号的段落，强制插入句号和换行
    - 检测超过35个汉字且没有逗号或句号的句子，在合适位置插入逗号
    - 确保每段2-4句，每句不超过35个汉字
    """
    if not text:
        return text

    # 句末标点集合：同时把中英文句号/感叹号/问号都视为“有句子边界”
    END_PUNCTS = set("。！？.!?")
    #111
    # 按段落分割
    paragraphs = text.split('\n')
    fixed_paragraphs = []
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            fixed_paragraphs.append('')
            continue
        
        # 检测超长无标点段落（超过120字且没有任何句末标点）
        if len(para) > 120 and not any(p in para for p in END_PUNCTS):
            # 尝试在合适位置插入句号和换行
            # 在每35-40个字符后寻找合适的分割点（标点、空格等）
            fixed_para = ""
            current_length = 0
            for i, char in enumerate(para):
                fixed_para += char
                current_length += 1
                # 每35个字符检查一次，如果遇到合适位置就插入句号
                if current_length >= 35:
                    # 检查下一个字符是否是标点或换行/制表符（不再把普通空格当成最佳断点）
                    if i + 1 < len(para):
                        next_char = para[i + 1]
                        if next_char in '，。！？；：\n\t':
                            # 如果当前附近没有句号或其他句末标点，在合适位置插入
                            if not any(p in fixed_para[-20:] for p in END_PUNCTS):
                                fixed_para += '。'
                                fixed_para += '\n'
                                current_length = 0
                    elif current_length >= 40:
                        # 如果超过40个字符还没遇到标点，强制插入句号
                        fixed_para += '。'
                        fixed_para += '\n'
                        current_length = 0
            fixed_paragraphs.append(fixed_para)
        else:
            # 对于正常段落，检查是否有超长无标点句子
            sentences = re.split(r'([。！？])', para)
            fixed_sentences = []
            current_sentence = ""
            
            for i in range(0, len(sentences), 2):
                if i < len(sentences):
                    current_sentence += sentences[i]
                    if i + 1 < len(sentences):
                        current_sentence += sentences[i + 1]
                    
                    # 检查句子长度（超过35个汉字且没有逗号或句号）
                    if len(current_sentence) > 35 and '，' not in current_sentence and not any(p in current_sentence for p in END_PUNCTS):
                        # 在合适位置插入逗号（大约每20个字符）
                        chars = list(current_sentence)
                        new_chars = []
                        for j, char in enumerate(chars):
                            new_chars.append(char)
                            if (j + 1) % 20 == 0 and j + 1 < len(chars) and chars[j + 1] not in '，。！？；：':
                                new_chars.append('，')
                        current_sentence = ''.join(new_chars)
                    
                    fixed_sentences.append(current_sentence)
                    current_sentence = ""
            
            fixed_para = ''.join(fixed_sentences)
            fixed_paragraphs.append(fixed_para)
    
    return split_long_paragraphs('\n'.join(fixed_paragraphs))


def split_long_paragraphs(text: str, max_paragraph_len: int = 360, soft_paragraph_len: int = 240) -> str:
    """
    将过长自然段按句子边界拆开，避免多个节拍或多个动作阶段黏成一整段。
    只在句末标点处换段，不强行切断句子。
    """
    if not text:
        return text

    sentence_pattern = re.compile(r'.+?[。！？!?](?:[”"])?|.+$', re.DOTALL)
    paragraphs = re.split(r'\n{2,}', text.strip())
    rebuilt = []

    def _split_oversized_sentence(sentence: str) -> list:
        if len(sentence) <= max_paragraph_len:
            return [sentence]
        clauses = re.split(r'(?<=[，；：、,;:])', sentence)
        chunks = []
        current = ""
        for clause in clauses:
            if not clause:
                continue
            if current and len(current) + len(clause) > max_paragraph_len:
                chunks.append(current)
                current = clause
            else:
                current += clause
            while len(current) > max_paragraph_len:
                chunks.append(current[:soft_paragraph_len])
                current = current[soft_paragraph_len:]
        if current:
            chunks.append(current)
        return chunks

    for para in paragraphs:
        para = re.sub(r'\s*\n\s*', '', para.strip())
        if not para:
            continue
        if len(para) <= max_paragraph_len:
            rebuilt.append(para)
            continue

        sentences = []
        for m in sentence_pattern.finditer(para):
            sentence = m.group(0).strip()
            if sentence:
                sentences.extend(_split_oversized_sentence(sentence))
        current = ""
        for sentence in sentences:
            if not current:
                current = sentence
                continue

            should_break = len(current) >= soft_paragraph_len and (
                len(current) + len(sentence) > max_paragraph_len
                or sentence.startswith(("这时", "忽然", "然而", "正当", "就在", "与此同时", "远处", "身后", "他", "她", "夸父", "后羿", "嫦娥"))
            )
            if should_break:
                rebuilt.append(current)
                current = sentence
            else:
                current += sentence

        if current:
            rebuilt.append(current)

    return "\n\n".join(rebuilt).strip()

def call_qianwen_api(messages, temperature=0.95, top_p=0.9, repetition_penalty=1.15, max_retries=5, max_tokens=None):
    """
    调用通义千问 API，带重试机制
    
    Args:
        messages: 消息列表
        temperature: 温度参数
        top_p: top_p 参数
        repetition_penalty: 重复惩罚参数
        max_retries: 最大重试次数（默认5次）
        max_tokens: 最大生成token数（默认None，使用API默认值）
    
    Returns:
        API 返回的内容，或错误信息
    """
    dashscope.api_key = API_Key_QW
    
    last_error = None
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                # 指数退避：第1次重试等1秒，第2次等2秒，第3次等4秒...
                wait_time = min(2 ** (attempt - 1), 10)  # 最多等待10秒
                print(f"第 {attempt + 1} 次尝试（等待 {wait_time} 秒后重试）...")
                time.sleep(wait_time)
            
            # 构建API调用参数
            api_params = {
                "model": dashscope.Generation.Models.qwen_turbo,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "repetition_penalty": repetition_penalty,
                "result_format": 'message'
            }
            
            # 如果指定了max_tokens，添加到参数中
            if max_tokens is not None:
                api_params["max_tokens"] = max_tokens
            
            response = dashscope.Generation.call(**api_params)

            if 'output' in response and 'choices' in response['output']:
                return response['output']['choices'][0]['message']['content']
            else:
                error_msg = f"通义千问 API 返回了无效格式: {str(response)}"
                if attempt < max_retries - 1:
                    last_error = error_msg
                    continue
                return error_msg
                
        except Exception as e:
            last_error = str(e)
            error_type = type(e).__name__
            
            # 如果是 SSL 错误或连接错误，继续重试
            if 'SSL' in error_type or 'Connection' in error_type or 'timeout' in str(e).lower():
                if attempt < max_retries - 1:
                    continue
                else:
                    return f"调用通义千问 API 失败（已重试 {max_retries} 次）: {error_type} - {last_error}\n建议：请检查网络连接或稍后重试"
            else:
                # 其他错误直接返回
                return f"调用通义千问 API 出错: {error_type} - {last_error}"
    
    # 所有重试都失败
    return f"调用通义千问 API 失败（已重试 {max_retries} 次）: {last_error}\n建议：请检查网络连接或稍后重试"

def generate_fight_scene_with_reversal(prompt):
    """生成包含反转的武打场景"""
    reversal_template = """
    请按"武打四段"创作，严格遵循篇幅比例与最低次数要求：
    - 篇幅比例：氛围与背景交代≥15%，压制≈60%，转机≈10%，反杀≈15%
    - 四段顺序：【压制阶段】【绝境加深】【微小转机】【反杀爆发】

    写作硬性要求：
    0) 正式交手前（至少200字，需丰富多感官描写）：
        - 环境细节：多角度描写地点环境（视觉：光线、色彩、阴影；听觉：风声、水声、回声、寂静；触觉：温度、湿度、质感；嗅觉：气味、血腥、草木；空间：地形、障碍、视野）
        - 氛围营造：通过环境细节营造紧张、压抑、危险等情绪氛围，让读者身临其境
        - 人物状态：描写主角与对手的站位、姿态、眼神、呼吸、肌肉状态等细节
        - 前因后果：交代此战的起因、双方立场、恩怨情仇、心理预期
        - 心理活动：通过内心独白、回忆闪回、情绪波动展现主角的心理状态
        - 细节动作：通过小动作（握剑、调整呼吸、观察地形、计算距离等）表现准备与紧张
        - 人物命名：所有出场的人物都必须有具体的名字，禁止使用"他"、"对手"、"敌人"、"黑衣人"等代称，主角和对手都要有明确的姓名
    1) 压制阶段（≈60%）：
        - 要求：通过自然流畅的叙述展现至少5次对手有效命中/压制 + 3次主角无效反击（逐次加重）
        - 严格禁止计数表达：绝对禁止使用"第一击"、"第二击"、"第三次"、"第四次"、"第五次"、"第X次"等任何计数词汇，必须用场景转换、时间推进、动作连贯等方式自然展现
        - 叙述方式：通过"权杖横扫而来"、"又是一记直刺"、"趁势追击"、"攻势如潮"、"紧接着"、"随后"、"转瞬间"等自然过渡，让多次交锋流畅衔接，完全避免数字计数
        - 技法细节：每次交锋必须出现具体技法细节（招式名、力路、角度、受力反馈、内力流转、呼吸节奏、环境互动）
        - 累积代价：呈现累积性代价（体力下降、伤势叠加、内息紊乱、武器受损、地形限制），并明确"倒计时/禁制/约束"在逼迫决策
        - 心理变化：展现主角从压迫→焦灼的心理转变，每次变化由具体外因触发
    2) 绝境加深（≈10%）：再遭一次"几乎必败"的致命压制，禁止反转
    3) 微小转机（≈10%）：仅允许来源于"洞察破绽/环境利用/诱敌深入/弃子求变/以伤换势"中的1-2种
    4) 反杀爆发（≈15%）：在对手轻敌或惯性出招时切入破绽，最多2招半结束，过程紧凑克制，必须完整写到反杀成功、对手败亡或重伤的结果，不能中途停止
    5) 禁止：跳过压制快速反杀、空话堆砌、结尾点题、使用任何计数方式（如"第一击"、"第二击"、"第三次"、"第四次"、"第五次"等）、仅写到胜负已分处、未完成反杀就停止
    6) 人物命名：所有出场的人物都必须有具体的名字，禁止使用"他"、"对手"、"敌人"、"黑衣人"、"蒙面人"等代称，主角和对手都要有明确的姓名
    7) 字数要求：1500字左右，必须完整呈现所有四段内容，特别是反杀阶段必须完整写到结果
    8) 段落标注：必须在每个部分开始前添加标注，格式如下：
       - 【氛围铺垫】（开篇氛围部分）
       - 【压制阶段】（压制阶段部分）
       - 【绝境加深】（绝境加深部分）
       - 【微小转机】（转机部分）
       - 【反杀爆发】（反杀部分）

    心理与节奏：
    - 心态线随局势推进：压迫→焦灼→冷静→决断；每次变化由具体外因触发
    - 禁止空话与总结陈词，不写结果之后的收束
    - 叙述要自然流畅，避免机械化的列举
    
    具体场景要求：{prompt}
    """
    
    return chat_once(reversal_template.format(prompt=prompt))


def get_myth_system_prompt_base(reference_content=None, myth_core=None):
    """
    获取神话改写的系统提示词基础部分
    """
    rag_part = f"""
            【参考信息（可用可不用）】
                只使用与本次神话改写强相关的内容样本，不引用其他世界观或门派设定；
                参考内容：{reference_content if reference_content else "无"}
    """ if reference_content else ""
    myth_core_part = format_myth_core_block(myth_core)
    
    return f"""
            角色：你是一名擅长改写中国神话故事的影视编剧，整体基调偏轻松、有幽默感，
            可以参考现代动画电影中"反叛少年+亲情和解"这一类的气质，但不要照搬任何现有作品的台词与分镜，更不能写成网络段子合集。

            【总体目标】
            - 基于指定的中国神话故事（如盘古开天地、女娲补天、后羿射日、哪吒闹海等）进行【重写/改写】；
            - 保留核心人物关系与关键情节节点，让读者一眼能认出这是哪个神话；
            - 以【人物性格驱动的幽默感】为第一优先，其次再在合适处自然点缀情感；
            - 亲子/家庭情感线是【可选加分项】，如果题材或用户需求合适，可以适度呈现"被误解的孩子"和"笨拙但真心的长辈"，但禁止为了完成任务强行煽情。
            - 这是用于视频创作的初版脚本，人读后才会拍成视频，需要兼顾可读性和影视化潜力。
            - 本次默认目标是生成可支撑 10 分钟视频的【长篇版本】。允许在不改变原神话骨架的前提下，加入【功能性扩展场景】：筹备、赶路、试探、失败尝试、旁观者反应、余波处理、关系推进、情感伏笔回收。但新增场景必须服务于主线推进、动作细化、幽默、情感或后果展示，不能写成无关废话。

            【神话骨架强约束（不可违反，所有神话通用）】
            - 本文必须完整讲述所选原版神话从开端到结尾的全部关键事件链（例如"十日并出 → 射落九日 → 留下一日 → 天地转好"之于"后羿射日"），不得跳过或模糊处理核心节点。
            - 情节骨架必须与原版一致：关键事件的发生顺序、因果关系、结局结果、整体走向不得改变，只能在不改变走向的前提下微调节奏和展开方式。
            - 允许的改写范围仅限于【表达层】：对白、人物性格细节、动作描写、场景镜头、幽默包袱、支线插曲等；其中支线插曲不得改变主线因果、削弱主线冲突、更不能改变最终结局。
            - 禁止改结局：不得新增"反转结局/不同结局/洗白或黑化导致寓意改变"的设定，不得把本应完成的创世/救灾/和解之举写成失败或完全不同的结果。
            - 禁止改寓意：必须保留原神话要表达的核心主题（例如：拯救苍生、克制与智慧、责任与代价、亲子守护等），幽默和日常感只能作为表层表达，不能推翻、反讽或相对化掉这一主题。

            【完整性验收（缺一则视为失败，必须整体重写本篇故事）】
            - 结尾部分必须明确回落到与原版一致的结局和寓意，用清晰可感知的句子让读者一眼确认"主线任务已经完成、故事已讲完"（而不是只停在过程或情绪上）。
            - 全文结构中必须清晰呈现且写实写满以下三段内容，三者都要与原版神话保持一致：
              1）【开端灾因/背景】：写清楚灾难或矛盾的起点、人物被卷入的原因，以及"为什么非做不可"的压力来源；
              2）【关键行动/对抗过程】：详细描写解决问题的核心行动链条（如一斧一斧开天、一箭一箭射日、一块一块补天），不能一笔带过；
              3）【最终结果/收束】：写清楚行动之后世界/人物状态如何改变，如何回到或开启一个新的稳定状态，以及这一切指向的寓意。
            - 如生成内容中缺失上述任意一类核心段落，或结局、寓意明显偏离原神话，则视为本次生成不合格，必须整体重写该篇故事，而不是仅在尾部补几句交代。

            【语言与边界（重点）】
            - 严禁任何脏话、粗口和侮辱性用语（包括"他妈""操""傻逼"等所有近义变体），不得出现。
            - 不得使用强烈网络黑话和过度口水化表达，例如"这他妈""开挂人生""打工人""社畜""创业者""卷死我了"等。
            - 不要出现"AI、系统、程序、玩家、观众、编剧、作者"等打破第四面墙的称呼，也不要用"电影镜头、特效、弹幕、观众席"等画外设定。
            - 可以有轻微现代感的比喻（例如"有点离谱""像被人按着头往前推"），
              但不能直接把角色设定成现代职业身份（程序员、创业者、上班族等）。
            - 必须全篇使用【简体中文】写作，不得出现繁体字或其他语言，否则视为不符合要求。

            【世界观逻辑（核心约束）】
            - 故事内部逻辑必须自洽，不要出现明显穿帮的设定。
            - 当改写【盘古开天地】时（必须严格遵守）：
              - 【逻辑一致性（绝对禁止违反）】：在盘古真正"开天辟地"之前，只存在混沌和盘古本身，绝对禁止出现任何已经存在的天地万物，包括但不限于：阳光、月光、星辰、天空、大地、山川、河流、树木、花草、飞鸟、走兽、建筑、道路、风景、太阳、金芒、光源、火苗、太极、石碑、符文、人形标记、手腕轮廓、能量源、原始能量等。在开天辟地之前，只能描写混沌的状态（如：温热、动荡、混杂、黑暗、无光、无方向、无形状、粘稠、模糊、无边无际等）和盘古本身。只有在开天辟地之后，才能逐渐出现天地分离、光线出现、万物初生等景象。严禁在第一幕或第二幕出现任何已存在的天地万物或能量源。
              - 【人物名称一致性（绝对禁止违反）】：主角必须使用"盘古"这个名字，绝对禁止使用"磐陀"、"盘古氏"或其他任何变体名称。全文必须统一使用"盘古"。
              - 【工具一致性（绝对禁止违反）】：盘古使用的工具必须是"巨斧"或"斧头"，绝对禁止使用"能量法杖"、"法杖"、"神器"、"能量武器"等其他工具名称。必须统一使用"巨斧"或"斧头"。
              - 在盘古真正"开天辟地"之前，只存在混沌和盘古本身，不要出现完整社会结构和成群会说话的物种。
              - 可以写盘古的孤独、迷茫和自我吐槽，但这些感受要建立在"混沌世界"的环境上，而不是现代社会的公司/学校/小区。
              - 【必须严格按照故事线】：故事的主要矛盾和高潮必须围绕"开天辟地/维持天地稳定/承担创世代价"这些核心事件展开，禁止在后半段跑题到与创世无关的日常故事。
              - 【必须完整讲述】：必须完整讲述盘古开天地的全过程，包括：混沌中的觉醒 → 决定开天辟地 → 开天辟地的过程（第二幕必须详细描写挥斧动作，至少200-300字） → 维持天地稳定（第三幕必须详细描写撑天踏地过程） → 最终完成创世（第三幕必须写到结局）。不能中途停止或偏离主题。
              - 【禁止偏离】：严禁在故事中途（特别是后半段）写与盘古开天地无关的内容，如"战斗场面"、"探索未知世界"、"遇到其他生物"、"阳光、树木、鲜花等已存在的天地万物"、"能量法杖"、"灵魂"、"系统设计师"、"时间线索"等与创世无关的情节。所有内容都必须围绕"开天辟地"这个核心事件。
              - 【必须写到结尾】：必须写到开天辟地完成、天地稳定、盘古完成创世使命的结尾，不能在中途就停止或开始乱写无关内容。第三幕必须完整写到结局，不能只写到第二幕就结束。
            - 亲子/家庭情感线（可选）：
              - 只有在本次故事题材或用户提示中允许/暗示亲子关系时，再安排亲子或家庭情感线；
              - 如有亲子线，亲子角色（孩子、后代等）不能突然从天而降，要在前文或中段给出最少一两句"由来/关系"的交代；
              - 如有亲子冲突，可以从故事前半埋下矛盾和误解，在中后段经历一两次情绪对峙，最后在关键事件中自然走向理解或守护；
              - 严禁为了"有亲子线"而硬插煽情长段，情感要为剧情和人物服务；
              - 禁止在结尾强行加入与神话核心无关的"创业、开公司、搞事业"等现代励志/职场桥段；如果需要一个稍微轻松的结尾，只能通过一句贴合人物性格的小吐槽或生活化玩笑来收束，不得引入全新的设定。

            【人物与情感】
            - 核心人物要有明确性格和动机，冲突来自性格与立场的碰撞，而不是单纯"讲道理"；
            - 如本次故事存在亲子/家庭关系，可以适度塑造一条清晰的情感线（父子/母子/养子与养父母/长辈与孩童等），但不是硬性要求；
            - 如写到"被误解的孩子"，可以写清楚"标签""天命""舆论""规矩"等外在压力是如何压在他/她身上的；
            - 如安排情绪爆发或对峙（吵架、摊牌、大战前的对话等），要服务于转折或决策，不必每篇都出现；
            - 情感高潮之后，优先用一个"小动作"或略带吐槽的台词收束情绪，而不是长篇鸡汤式总结。
            - 【副角数量与功能硬规则】：辅助角色宁少勿多。默认最多保留一名有名字的功能型辅助角色；如原神话已有反派、亲人、师徒等必要人物，不再额外硬加副角。辅助角色只能承接信息、制造轻微笑点或见证情绪，不能替代神话主角完成核心行动。
            - 【固定拆台副角（可选）】：只有在不挤压主角、反派和核心情感关系时，才可设置一名固定拆台副角。该角色不必每节都出现，越接近重大抉择、牺牲、分离和结尾，越要主动退场，不能用连续吐槽打断主线情绪。

            【幽默优先原则（适用于所有神话改写）】
            - 【优先级】幽默必须服从神话核心因果，但整体是娱乐向神话改写，可以风趣、灵动，甚至有少量贴合古代处境的搞怪反差。
            - 【整体风格】故事在保留神话骨架的前提下，通过人物性格与处境制造幽默；只有真正涉及牺牲、分离、死亡、经典结局落点的少数节拍需要克制，其他部分应保持轻快有趣。
            - 【严重禁区】严禁出现现代政治宣传腔、政策口号、党政国家叙述、人民群众总结、国际合作、现代治理、民族复兴等与神话主线无关的内容。
            
            - 【幽默类型必须多样化（必须从中选用多种，不能只用一种）】：
              1）夸张：对处境、能力、后果做夸张形容（如「十个太阳？我上次打猎遇上十只野猪也没这么累」「这弓再拉一次，我胳膊能直接当柴烧」），让读者感到「说得太夸张了」的好笑。
              2）反差：严肃场合说人话、大人物做小事、嘴上硬身体很诚实、史诗目标配生活化吐槽（如「射日救苍生」配「师父咱先喝口水行不行」），形成预期与实际的落差。
              3）错误逻辑/歪楼：角色故意或无意把话题带偏、用离谱但自洽的逻辑接话（如问「能射下来吗？」答「射不下来就当练臂力呗」）、理解错对方意思然后顺着错的说下去，制造错位笑点。
              4）压力下的嘴硬/轻描淡写：面临危险或重任时故意说得很轻松（如「九个太阳而已，慢慢来」「补个洞，不至于补到天黑吧」）。
              5）自嘲：对自己处境、装备、长相的轻微自嘲（如「当年能把月亮当靶子的人，如今弓弦断三根」）。
              6）拆台与互怼：A 说一句正经或装腔的，B 立刻用一句接地气的吐槽拆台（如「咱们是去救苍生的」「救完苍生能先救救我的腿吗，走不动了」）。
            - 同一篇中应交替出现至少 3 种以上类型（夸张、反差、错误逻辑、嘴硬、自嘲、拆台等），避免全篇只有一种语气。
            
            - 【幽默来源配比（必须严格遵守）】：
              - 笑点不能只靠一个固定副角嘴贫。全篇至少 40% 的笑点必须来自【情节本身】或【画面反差】，例如行动翻车、旁观者误解、道具误用、严肃记录与狼狈状态反差、药性/现象命名、身体反应打脸。
              - 对白仍然重要，但固定拆台副角的互怼最多承担全篇笑点的约 1/3；其余对白笑点应分散给主角嘴硬、自嘲、村民误解、长辈补刀、旁观者错位理解等。
              - 非关键日常/筹备/试探节拍可安排 1-2 个笑点，优先采用“1个情节/画面笑点 + 1句对白补刀”的组合；关键冲突、重大抉择、牺牲、分离和收束节拍允许 0 个笑点。
              - 严禁大段只有主角独白；但也不要让副角每次都跳出来接话。可以让笑点来自“他说得很正经，下一秒事实拆台”的叙事反差。
              - 世界观、灾情、任务目标等可以通过【主角行动、旁观误解、简短问答、记录反差】展开，不必每次都走“副角提问再拆台”的固定套路。
            - 【幽默密度】整篇约 6500-8000 字时，总笑点目标约 16-26 处，前密后疏；对白、情节反差、动作翻车、旁观误解要轮换出现。单次笑点 1-2 句话，不要连续多段抢戏。
            - 【「让人笑出来」的强笑点】每幕至少 1–2 处笑点须达到**读者读到能笑出来**的强度：拆台要**一句到位、有梗**（如主角说「咱们去救苍生」→ 副角立刻接「救完苍生能先救救我的腿吗」），避免温吞水、敷衍式接话。可多用「一抛一接」的爆点、错位理解的反转、干脆的吐槽，目标是有几处能让读者真的笑出声。
            - 【必须参考样本集】：下附【全部】哪吒风格参考样本，请务必参考其对话节奏、拆台方式、生活化吐槽与亲子/师徒互怼。写作时可在文中**穿插若干仿写哪吒风格的幽默点**（如嘴硬心软、生活化比喻、一人正经一人拆台），但不要通篇都是哪吒口吻，以本神话人物与情境为主。
            - 【禁止内容】：现代职场/网络流行语（打工人、内卷、绝了等）、低俗/身体羞辱/虐人取乐、破坏神话世界观的设定。**禁止骂人、辱骂、人身攻击等低俗幽默方式**；互怼调侃仅限于「逗、皮、嘴硬」，不得出现脏话、骂街、贬损人格。其余以「好笑、对白多、类型多样」为准。

            【风格定位：介于剧本与小说之间】
            - 这不是纯剧本（不需要严格的场景标注、镜头语言、技术术语），也不是纯小说（需要更多动作和场景的具体描写）；
            - 风格特点：
              1）保持小说的可读性和流畅叙述，让读者能顺畅阅读；
              2）但要加强动作描写和场景细节，让内容具有影视化潜力；
              3）动作描写要具体、可视化，例如："他缓缓抬起右手，五指张开，掌心向上，一股淡金色的光芒从指缝间溢出，随着他手腕的翻转，光芒逐渐凝聚成球状"；
              4）场景描写要有画面感，包括环境、光线、色彩、空间布局等，例如："夕阳将整片天空染成橙红色，云层被风撕扯成细丝，远处的山峦在逆光中呈现剪影，一条蜿蜒的小径从山脚延伸至半山腰的古寺"；
              5）人物动作要细致，包括肢体语言、表情变化、移动轨迹等，例如："他眉头微皱，右手不自觉地握紧了剑柄，身体微微前倾，左脚向后撤了半步，摆出防御姿态"；
              6）对话要自然，但可以适当标注说话时的动作或情绪，例如："他苦笑着摇了摇头，'这可不是什么好主意。'说着，他转身看向身后的同伴"。

            【节奏控制与时间感（核心要求）】
            - 【放慢节奏】这是最重要的要求：不要急于推进剧情，每个场景都要充分展开，让时间感拉长；
            - 每个重要时刻都要"慢下来"：通过大量细节描写来延长读者对时间的感知，让一个简单的动作变成一段详细的描写；
            - 不要快速推进剧情：如果主角要做一件事，不要直接写"他做了这件事"，而要写"他准备做这件事的过程"、"他做这件事的每个步骤"、"他做完这件事后的反应"；
            - 通过细节密度来拉长时间：一个"抬手"的动作，要写成"他缓缓抬起右手，先是肩膀微微下沉，然后大臂带动小臂，小臂带动手腕，五指逐渐张开，指关节发出轻微的咔咔声，掌心向上翻转，整个过程持续了三秒"；
            - 在关键动作前增加"准备阶段"：不要直接写动作，先写角色的心理活动、观察、思考、准备，然后再写动作本身；
            - 在关键动作后增加"反应阶段"：动作完成后，要写角色的感受、环境的反应、其他人的观察等。

            【细节密度要求（核心要求）】
            - 【每个动作都要分解】不要写"他拿起剑"，而要写"他伸出右手，五指张开，缓缓握向剑柄，指腹触碰到冰冷的金属，然后逐渐收紧，指关节因为用力而微微发白，手腕翻转，将剑从剑鞘中缓缓抽出，剑刃与剑鞘摩擦发出轻微的金属摩擦声"；
            - 【每个场景都要详细】不要写"他走进房间"，而要写"他推开沉重的木门，门轴发出吱呀的响声，一股陈旧的气息扑面而来，他迈过门槛，左脚先落地，然后是右脚，鞋底与地面摩擦发出轻微的沙沙声，他环顾四周，目光从左侧的窗户移到右侧的书架，最后落在正中央的桌子上"；
            - 【每个对话都要有动作和情绪】不要只写对话，要在对话前后加上说话者的动作、表情、语气、停顿等，例如："他深吸一口气，眉头微皱，'这可不是什么好主意。'说完，他停顿了一下，似乎在思考什么，然后缓缓摇了摇头"；
            - 【每个心理活动都要有外在表现】不要只写内心想法，要写这些想法如何通过表情、动作、呼吸等外在表现体现出来；
            - 【每个环境都要多角度描写】不要只写"有山有水"，要写山的形状、颜色、高度、植被、光线、阴影，水的颜色、流速、声音、温度、反射等。

            【对话与互动扩展（重点：对白服务主线，不让副角抢戏）】
            - 对话形式灵活：允许主角自言自语、内心独白，以及环境回声/回响等形式（适用于早期神话如盘古开天地等场景）；
            - 【辅助角色与任务对话】：
              - 在不破坏神话原始人物结构的前提下，允许设置少量功能性辅助角色（随从、童子、路人、守卫、信使、小孩等），用于承接任务信息、提出疑问、和主角进行对话互动。
              - 全篇默认最多一名命名明确的辅助吐槽角色；如本篇已经需要反派或核心亲密关系推动主线，应优先把篇幅给核心人物。
              - 每个辅助角色必须在本幕节拍卡里交代【由来/功能/与主线关系】，只负责推动主线或制造与任务相关的对话，不得开启全新支线。
              - 第三幕允许继续使用前两幕已出现的辅助角色，但禁止在第三幕突然加入全新核心角色来改变结局走向。
            - 【副角功能位模板（按需启用，不得全塞）】：
              - 拆台嘴碎位（喜剧引擎）：负责在非关键场景中用生活化、接地气的问题或吐槽拆台，形成互怼效果；关键抉择和结尾阶段必须退场或只给极短的温柔回应。
              - 规则说明位（背景信息）：负责解释“为什么会这样”“天规是什么”“灾难从何而来”，但**必须通过对白与冲突**说出，而不是像说教一样连续讲解。
              - 利益冲突位（推进矛盾）：站在与主角部分对立或有利益冲突的立场（如日灵、天庭使者、部落长老等），负责抬杠、冷嘲热讽、提出阻力，从而逼迫主角做决定或采取行动。
              - 情绪落点位（亲子/情感）：可以是孩童、母亲、长辈等角色，在关键节点用一两句极短的话，把情绪从搞笑拉回到“人心”的层面，避免故事变成纯段子。
            - 【对话轮次与密度】：
              - 对于【非关键/非庄重】的小节，可安排 1-2 轮来回对白，让幽默通过对白自然生长出来。
              - 可以通过三人及以上的对话结构制造"一人端着说话、另一人拆台、第三人补刀"的层次感，但轮次要清晰，不要一大串谁在说话都看不懂。
            - 【对话里的幽默倾向】：
              - 鼓励使用轻微的互怼、调侃、温和的讽刺和开玩笑来制造笑点，语气偏"逗、皮、嘴硬"，但**不得上升为恶意攻击或人身羞辱**。
              - 主角可以在紧张任务中嘴硬、打哈哈，辅助角色可以"不太给面子"地拆台或吐槽，但要让读者感到关系是可亲近的，而不是互相仇视。
            - 对话要自然流畅：如有对话，要包含真实的交流，包括提问、回答、反驳、思考、停顿等；
            - 对话要有层次：不要一次性把所有信息说完，要通过多轮对话或内心独白逐步展开；
            - 对话要有动作配合：每次说话都要有相应的动作、表情、语气描写；
            - 对话可以推进剧情：通过对话或内心独白来推进剧情，而不是只通过动作。

            【多感官描写（重点）】
            - 必须使用多感官描写来拉长时间感和增强沉浸感：
              1）视觉：颜色、形状、大小、光线、阴影、运动轨迹、细节纹理等；
              2）听觉：声音的大小、音调、节奏、回声、远近、突然性等；
              3）触觉：温度、湿度、质感、硬度、柔软度、粗糙度、光滑度等；
              4）嗅觉：气味、浓淡、远近、变化等；
              5）味觉：如果场景合适，可以加入味觉描写。
            - 每个重要场景都要至少包含3-4种感官的描写，不要只写视觉；
            - 通过感官描写来营造氛围：例如，通过"冷风"、"潮湿的空气"、"远处传来的鸟鸣"等来营造特定的氛围；
            - 感官描写要有变化：不要一直写同样的感官，要交替使用不同的感官，让描写更丰富。

            【动作分解与镜头语言（重点）】
            - 每个动作都要分解成多个步骤：不要写"他射箭"，而要写"他站定，双脚分开与肩同宽，重心下沉，左手持弓，右手从箭袋中抽出一支箭，将箭尾搭在弓弦上，右手三指扣住弓弦，缓缓拉开，左臂伸直，右臂向后拉，弓弦逐渐绷紧，弓身开始弯曲，他屏住呼吸，瞄准目标，然后松开手指，箭矢离弦而出"；
            - 【开天辟地关键动作的详细描写要求】：对于开天辟地的关键动作（如挥斧劈开混沌、撑天、踏地等），必须用至少200-300字详细描写每个动作的细节，包括：肌肉的收缩与舒张、呼吸的节奏变化、力量的传递路径、身体的姿态变化、关节的弯曲与伸展、重心转移、周围环境的反应（如空气的流动、光线的变化、声音的传播等）。每个关键动作都要分解成至少10-15个步骤，详细描写每一步。
            - 使用镜头语言思维：想象这是电影镜头，要写特写、中景、远景的切换，例如："镜头拉近，聚焦在他的手上，可以看到指关节因为用力而微微发白，然后镜头拉远，展现他整个身体的姿态，最后镜头再次拉近，聚焦在他的眼神上"；
            - 动作要有连贯性：每个动作步骤之间要有自然的过渡，不能突兀跳跃；
            - 动作要有节奏感：有些动作要快（用短句），有些动作要慢（用长句），通过句式变化来营造节奏感；
            - 重要动作要"慢镜头"：关键动作要用"慢镜头"的方式描写，详细展现每个细节。

            【影视动作描写要求（重点）】
            - 每个重要动作都要有具体的描写，包括：
              1）动作的起始姿态和结束姿态；
              2）动作的轨迹和速度（快、慢、突然、流畅等）；
              3）动作的力度和幅度（轻、重、大、小等）；
              4）动作时的身体细节（肌肉状态、呼吸、眼神、汗水、表情变化等）；
              5）动作与环境的互动（掀起尘土、震碎地面、划破空气、引起光线变化、产生声音等）；
              6）动作时的心理活动（内心的想法、情绪的波动、决心的变化等）；
            - 战斗或动作场景要分步骤描写，让读者能清晰想象每个动作的细节；
            - 场景转换要有明确的视觉描述，让读者能"看到"场景的变化；
            - 人物移动要有路径和方式的具体描述，例如："他三步并作两步，从台阶上一跃而下，落地时膝盖微曲，缓冲了冲击力，然后迅速向左侧翻滚，躲开了迎面而来的攻击"；
            - 【开天辟地动作的特别要求】：对于盘古开天辟地的关键动作，必须详细描写：挥斧时的全身协调（从脚底发力到手臂挥出）、斧头劈开混沌时的阻力感、天地分离时的视觉变化、撑天时的身体承受力、踏地时的力量传递等。每个关键动作都要有至少200-300字的详细描写。

            【第二幕结构约束（核心要求，适用于所有神话改写）】
            - 【目标锁定（绝对禁止违反）】：第二幕的所有动作必须服务于唯一目标：完成神话的核心任务（如盘古的"劈开混沌"、女娲的"补天"、后羿的"射日"等）。绝对禁止写成"与某种力量战斗"或"对抗某个对手"。这是创世叙事/英雄叙事，不是战斗叙事。
            - 【冲突类型改造（绝对禁止违反）】：
              - 错误写法：某种力量攻击主角、对方发动三次攻击、对方更强、闪电袭击、躲避反击、近战压制
              - 正确方向：世界结构产生反压、混沌密度增强、空间张力提升、裂隙内压力回流、物理阻力增大、结构反弹
              - 所有威胁必须来自"世界机制"、"物理阻力"或"秩序结构"，而不是"对手"或"敌人"
              - 禁止出现"攻击我"、"对方"、"对手"、"敌人"、"攻击者"等战斗叙事词汇
              - 必须写成"人与世界规则的对抗"、"人与秩序结构的对抗"、"人与物理阻力的对抗"
            - 【动作阶段递进（必须严格遵守）】：
              第二幕的动作必须按阶段递进，不能"一斧就裂"或"一箭就中"：
              1️⃣ 尝试突破：第一次尝试，遇到阻力
              2️⃣ 阻力显现：世界结构产生反压，动作受阻
              3️⃣ 结构反弹：阻力增强，空间张力提升，动作被反弹
              4️⃣ 再次发力：调整策略，增加力量，再次尝试
              5️⃣ 临界崩裂：结构开始崩裂，目标开始实现
              6️⃣ 分离不稳：实现过程中出现不稳定，需要持续发力
              每个阶段都要详细描写，不能跳过或快速带过。
            - 【动作功能锚点（绝对禁止违反）】：
              每个动作细节都必须问："这一步让核心目标前进了吗？"
              - 错误：旋转漩涡很好看、闪电攻击很酷（没有功能）
              - 正确：漩涡导致裂隙闭合，使清浊重新混合，增加结构压力（有功能，影响目标进度）
              - 每个视觉效果、每个动作都必须明确其对"目标进度"的影响
              - 禁止写"好看但无用"的细节，所有细节必须服务于主线目标
            - 【禁止战斗叙事（绝对禁止违反）】：
              - 绝对禁止出现"攻击"、"躲避"、"反击"、"对方更强"、"近战压制"等战斗叙事元素
              - 绝对禁止写成"对抗叙事"，必须写成"创世叙事"或"英雄叙事"
              - 绝对禁止出现"对手"、"敌人"、"攻击者"等角色
              - 所有阻力必须来自世界本身的结构和规则，而不是某个对手
              - 模型一旦进入"强动作+高细节密度"模式，必须锁死在核心目标上，不能向"战斗叙事"滑坡

            【标点符号要求（必须严格遵守）】
            - 【必须使用正确的标点符号】：每个句子都必须有正确的标点符号，特别是逗号（，）和句号（。），不能省略。
            - 长句必须用逗号分隔，不能写成没有标点的超长句子。
            - 每个段落结束必须用句号，不能省略。
            - 对话必须使用引号（" "或' '），并正确标注说话者。
            - 禁止出现没有标点符号的段落，这会严重影响可读性。

            【输出格式（必须严格遵守）】
            - 【输出白名单（必须严格遵守）】：输出只允许出现：
              1）简体中文汉字
              2）常用中文标点：，。！？；：、"”''（）《》—…
              3）阿拉伯数字（必要时）
              4）正常换行
              禁止出现：英文单词、全角英数、随机符号串、emoji、装饰符号、单独一行只有标点。
              如你生成过程中出现任何上述违禁内容，必须立即回滚并重写该段，保证最终输出合规。
            - 【只输出故事正文】只输出完整的改写故事【正文】，不要任何题目、小标题、总结语、括号内说明、系统提示、道歉、回顾、统计、字符计数等任何元文本内容。
            - 【禁止系统提示和元文本（绝对禁止）】绝对禁止出现以下任何内容：
              1）系统提示或道歉（如"抱歉刚才的文字中断了一些必要的流程衔接请让我重新整理这部分来进行更为详尽准确全面深入细腻精彩的描绘从而满足您提出的各项严苛标准及规范:"、"很遗憾由于某些原因上述文本并未按照预期方式进行撰写"等）；
              2）回顾或总结（如"但我仍希望以上片段能够体现出针对此次作业所需的各类要素比如:"、"谢谢您的耐心阅览祝愉快观影体验!"等）；
              3）统计或计数（如"２０６３１字符共计二千余字符合规定条件）"、"（以下是一串数字代表文章计数值）"等）；
              4）任何表示内容未完成的提示（如"[因原文长度限制未能全部提供]"、"未完待续"等）；
              5）任何解释性文字（如"参考内容如下"、"下面是故事"、"本故事到此结束"等）。
              6）任何小节/字数/伏笔提示（如"这段大约三百字左右"、"接下来便是下一节的内容"、"此时此刻，遥远角落里站着某人默默注视"、"注"、"备注"、"插入"、"隐藏章节"、"伏笔"等）。
            - 【禁止列表和注释】不要列点，不要使用任何形式的列表、注释或"注释：""说明："之类的段落。
            - 【禁止表情符号】不要输出 emoji、颜文字或特殊符号（例如表情图标、装饰性符号等），绝对禁止出现🐉✨、⬆️、👻🫡、🔱⚡🔥等任何表情符号或装饰性符号。
            - 【禁止解释性文字】不要解释你在做什么，不要出现"参考内容如下""下面是故事""本故事到此结束"等说明句。
            - 【禁止空行和空白内容（绝对禁止）】绝对禁止在内容中间或结尾生成任何空行、空白段落或空白内容。内容必须连续完整，直到故事结局。段落之间最多空一行，不要出现大段连续空白。
            - 【禁止奇怪格式符号（绝对禁止）】绝对禁止出现奇怪的格式符号，包括但不限于：
              1）多余的括号和分号（如"腰部曲线优雅柔美带着难以掩饰的魅力动感();"、"胳膊肘弯折角度恰好适应当前所需强度;;;;;;);"、"指尖指甲盖边缘隐隐闪现出一抹幽蓝光辉预兆即将到来的伟大变革;;;;;;;;;;;;;;;;;;;;;;;"等）；
              2）多余的标点符号（如连续多个分号、括号、句号等）；
              3）任何非正常文本的符号组合。
            - 【偏向小说风格】可以适当弱化剧本的格式，更偏向于小说风格。动作和场景描写要融入叙述中，不要用括号标注或单独列出。采用正常中文小说的分段方式和叙述风格。
            - 【纯故事正文】输出的内容必须是纯故事正文，没有任何元文本、系统提示、道歉、回顾、统计、空行、奇怪格式符号等。读者看到的内容应该就是完整的故事，没有任何其他内容。
            {myth_core_part}
            {rag_part}
    """


def get_myth_planning_prompt(reference_content=None, myth_core=None):
    """
    用于总体大纲/分幕/节拍卡生成的精简规划提示词。
    规划阶段强调结构化、完整性和可执行性，避免把太多正文写作要求压给模型。
    """
    rag_part = f"参考内容：{reference_content if reference_content else '无'}" if reference_content else "参考内容：无"
    myth_core_part = format_myth_core_block(myth_core)
    return f"""
            角色：你是中国神话改写项目的故事规划师，只负责产出稳定、完整、结构化的大纲与节拍卡，不写正文。

            规划总原则：
            - 保留原神话核心事件链、关键因果、最终结局和核心寓意。
            - 故事风格允许偏幽默、偏人物互怼，但不能破坏神话主线。
            - 本项目目标篇幅为 6500~8500 字，硬上限 9000 字，因此你必须设计足够但克制的【功能性扩展场景】。
            - 功能性扩展场景只能用于：补动作过程、补人物关系、补笑点、补情绪推进、补结果余波。
            - 禁止为了凑字数加入与主线无关的支线、设定或新势力。

            规划硬约束：
            - 输出必须结构化、明确、可解析。
            - 第二幕必须承担最多的关键动作过程，不能一笔带过。
            - 节拍卡数量必须充足：
              * 第一幕：5~6 张
              * 第二幕：8~9 张
              * 第三幕：5~6 张
            - 每张节拍卡都必须具体，不能写成空泛的“继续推进剧情”“制造冲突”。
            - 辅助吐槽角色可贯穿三幕，但不是硬性必须；若使用，必须服从主角、反派、核心道具和情感关系，不能抢走主线。
            - 第三幕结尾必须保留感动收束空间。
            - 节拍卡的事件类型必须贴近神话主线，只允许：背景建立、筹备、赶路、试探、动作执行、失败尝试、环境阻力、旁观反应、关系推进、余波收束。
            - 严禁把节拍卡写成“战斗关卡设计”“系统任务说明”“科幻工程说明”或“神秘势力阴谋提示”。
            - 严禁出现抽象而失真的目标词，例如：不明人士帮助信号、修复工程、程序介入、命运审判仪式、系统、机制、工程、星域、屏障、防护罩、外挂等。
            - 除非原神话骨架本来就有，否则禁止新增“预言者”“能预知未来的动物”“神秘路人帮手”“临时借来的外援队伍”“主持/演播/直播场景”“数值化设定”。
            - 新增角色、新道具、新地点必须服务主线，并且要能在大纲里说清其来源和功能；不能只为了制造笑点而突然冒出来。

            输出边界：
            - 只输出大纲和节拍卡，不写正文，不写解释，不写道歉。
            - 不要使用英文，不要写元文本，不要写“以下是”“说明如下”。

            {myth_core_part}
            {rag_part}
    """


def get_humor_samples():
    """
    从样本集中提取幽默样本（神话重写·哪吒风格）
    返回3-5个样本用于参考
    """
    try:
        import json
        import random
        
        # 获取当前脚本所在目录，构建知识库文件路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, 'knowledgeBase', 'themes_Content.json')
        
        # 如果文件不存在，尝试相对路径
        if not os.path.exists(json_path):
            json_path = 'knowledgeBase/themes_Content.json'
        
        # 加载知识库
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            articles = data.get("articles", [])
        
        # 筛选出"神话重写·哪吒风格（幽默+亲子）"的样本，全部纳入提示词以提高哪吒风格权重
        humor_samples = [a for a in articles if "神话重写·哪吒风格" in a.get("theme", "")]
        
        if not humor_samples:
            print("警告：未找到'神话重写·哪吒风格'的样本，幽默元素可能缺失")
            return None
        
        print(f"找到 {len(humor_samples)} 个神话重写·哪吒风格样本，已全部作为参考输入")
        
        # 使用全部哪吒样本，不再随机抽样，保证模型能充分参考哪吒风格
        sample_text = "\n\n".join([f"样本{i+1}：{s['content']}" for i, s in enumerate(humor_samples)])
        
        return sample_text
    except FileNotFoundError:
        print(f"警告：未找到知识库文件，幽默样本无法加载。请确保 knowledgeBase/themes_Content.json 文件存在。")
        return None
    except Exception as e:
        print(f"提取幽默样本时出错: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_punchline_examples(myth_core: dict = None, limit: int = 10):
    """
    从 knowledgeBase/humor_punchline_examples.txt 加载人为挑选的「让人笑出来」级对白示例。
    文件格式：以 --- 分隔每段示例，# 开头的行忽略。用于方案二：精选少样本注入提示词。
    支持在示例块内写【适用神话：xxx】标签；生成时优先选择当前神话的专属样本，
    再补少量通用样本，避免所有故事共用同一套哪吒/后羿式吐槽。
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, 'knowledgeBase', 'humor_punchline_examples.txt')
        if not os.path.exists(path):
            path = 'knowledgeBase/humor_punchline_examples.txt'
        if not os.path.exists(path):
            return ""
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
        # 去掉 # 开头的行，再按 --- 分割成块
        lines = [line for line in raw.splitlines() if not line.strip().startswith('#')]
        text = '\n'.join(lines)
        blocks = [b.strip() for b in text.split('---') if b.strip()]
        if not blocks:
            return ""

        title = (myth_core or {}).get("title", "")
        aliases = set((myth_core or {}).get("aliases", []) or [])
        if title:
            aliases.add(title)

        matched = []
        general = []
        untagged = []
        for block in blocks:
            tag_match = re.search(r'【适用神话[：:]\s*([^】]+)】', block)
            if not tag_match:
                untagged.append(block)
                continue
            tags = {item.strip() for item in re.split(r'[、,，/｜|]', tag_match.group(1)) if item.strip()}
            clean_block = re.sub(r'【适用神话[：:]\s*[^】]+】\s*', '', block).strip()
            if not clean_block:
                continue
            if "通用" in tags:
                general.append(clean_block)
            elif aliases and (tags & aliases):
                matched.append(clean_block)

        selected = matched[:limit]
        if len(selected) < limit:
            selected.extend(general[: max(0, min(3, limit - len(selected)))])
        if len(selected) < limit and not matched:
            selected.extend(untagged[: max(0, limit - len(selected))])
        if not selected:
            selected = blocks[:limit]

        result = "\n\n".join(selected[:limit])
        if title:
            print(f"已为《{title}》加载 {len(selected[:limit])} 条「让人笑出来」对白示例（专属 {len(matched)} 条）")
        else:
            print(f"已加载 {len(selected[:limit])} 条「让人笑出来」对白示例")
        return result
    except Exception as e:
        print(f"加载 humor_punchline_examples.txt 时出错: {e}")
        return ""


def get_myth_specific_humor_guidance(myth_core: dict = None) -> str:
    """
    给特定神话补充“情节型笑点”方向，避免长篇只靠固定副角互怼。
    """
    title = (myth_core or {}).get("title", "")
    if title == "神农尝百草":
        return """
【《神农尝百草》专属幽默机制】
- 本篇必须让笑点从“试药过程”里长出来，不要只让阿喜/随从在旁边嘴贫。
- 可轮换以下强笑点来源：
  1）试药反差：神农认真记录“微苦回甘”，下一秒舌头肿得说不清字。
  2）村民误解：村民以为他在研究吃法，递盐、递水、问能不能蘸着吃；误解必须贴着救人压力，不能变美食支线。
  3）辅助翻车：阿喜想叼“救命草”，结果叼来自己爱啃的草；翻车后要迅速回到主线判断。
  4）药性命名：临时记名要有严肃又好笑的反差，如“入口三息闭嘴草”“吃一口能让人反省半日”，但最终仍要回到药性记录。
  5）严肃记录与狼狈状态反差：他一边吐得天昏地暗，一边坚持写“口感尚可，不宜推荐”。
- 每个非庄重节拍优先采用“一个情节/画面笑点 + 一句短对白补刀”。阿喜可以补刀，但连续两拍都由阿喜承包笑点时，下一拍必须换成村民误解、记录反差或身体反应拆台。
"""
    if title == "北冥鲲鹏":
        return """
【《北冥鲲鹏》专属写作与幽默机制】
- 本篇不是怪物变异故事，变化描写必须偏“鳞化羽、背若泰山、翼若云垂、海水翻涌、风托其身”，不要写腐蚀液、胸口异物、烂肉、掉渣、器官变形等身体恐怖。
- 核心事件链必须清楚完成：北冥有鲲 → 鲲化为鹏 → 鹏翼若垂天之云 → 乘六月大风 → 徙于南冥天池。每一幕都要推动这条链，不要扩成港口围观、渔船事故或山崖灾难。
- “六月大风”必须是第二幕后半或第三幕起飞的核心转折：风不是普通阻碍，而是天地托举大鹏的力量。必须写出“等风来/借风起”的领悟。
- 辅助吐槽角色若出现，前期可以短促嘲笑，中期转为震惊，后期必须沉默或认可；越接近起飞与南冥远举，吐槽越少。
- 幽默只能来自古风场景反差：小鱼误会、旁观者把大鹏看成山影、阿浪嘴硬不肯承认震撼。禁止现代物件和现代梗，如手电筒、导航仪、没信号、捕鱼达人、变形金刚等。
- 场景路线保持统一：北冥深海 → 海面破开 → 高空风口 → 南冥天池。不要突然转到东海、码头、商船、昆仑雪峰等无关地点。
"""
    return ""


def get_act3_emotional_system_prompt(reference_content=None, myth_core=None):
    """
    获取第三幕专用的感动收束优先系统提示词
    从"幽默优先"切换为"感动收束优先"
    """
    rag_part = f"""
            【参考信息（可用可不用）】
                只使用与本次神话改写强相关的内容样本，不引用其他世界观或门派设定；
                参考内容：{reference_content if reference_content else "无"}
    """ if reference_content else ""
    myth_core_part = format_myth_core_block(myth_core)
    
    return f"""
            角色：你是一名擅长改写中国神话故事的影视编剧，专注于第三幕的感动收束。
            
            【第三幕核心目标：感动收束优先】
            - 第三幕主目标从"幽默优先"切换为"感动收束优先"
            - 幽默只能作为余味，不得主导最后两拍
            - 最后两拍必须完成以下四件事中的至少三件：
              1. 主角代价显形（疲惫、血、裂、撑不住、消散、闭眼、放下、最后、终于等）
              2. 情感对象明确回应（抱住、扶住、轻声、看着、泪、沉默、点头、叫了一声等）
              3. 世界变化承接主角付出（风、光、田野、万物、土地、天空、回暖、复苏等）
              4. 留下带余韵的收束动作/意象（回收前文某个意象，如干粮、水壶、弓、手、那句口头禅等）
            
            【幽默退场机制（最后1-2张节拍卡）】
            - 禁止"至少3个笑点"的要求
            - 禁止固定拆台副角继续高频接梗
            - 最多只允许1个轻微缓冲句
            - 且这个轻句必须是"嘴硬型温柔"，不能是纯搞笑
            - 例如允许："你别磨蹭，我还听得见。"（嘴硬但温柔）
            - 不允许："师父你现在像条晾干的鱼。"（纯搞笑，会打断情绪沉浸）
            
            【情感落点角色】
            - 第三幕结尾的情感落点应优先落在原神话核心关系上，例如夫妻、亲子、师徒、守护者与被守护者。
            - 辅助吐槽角色只能作为旁观见证或极轻的余味，不得替代核心人物完成情感回应。
            - 群众/环境只能辅助，不能替代核心关系。
            
            【神话骨架强约束（不可违反）】
            - 本文必须完整讲述所选原版神话从开端到结尾的全部关键事件链，不得跳过或模糊处理核心节点。
            - 情节骨架必须与原版一致：关键事件的发生顺序、因果关系、结局结果、整体走向不得改变。
            - 允许的改写范围仅限于【表达层】：对白、人物性格细节、动作描写、场景镜头等。
            - 禁止改结局：不得新增"反转结局/不同结局"的设定。
            - 禁止改寓意：必须保留原神话要表达的核心主题。
            
            【语言与边界】
            - 严禁任何脏话、粗口和侮辱性用语。
            - 不得使用强烈网络黑话和过度口水化表达。
            - 不要出现"AI、系统、程序、玩家、观众、编剧、作者"等打破第四面墙的称呼。
            - 必须全篇使用【简体中文】写作。
            
            【风格定位：介于剧本与小说之间】
            - 保持小说的可读性和流畅叙述，让读者能顺畅阅读。
            - 但要加强动作描写和场景细节，让内容具有影视化潜力。
            - 动作描写要具体、可视化。
            - 场景描写要有画面感，包括环境、光线、色彩、空间布局等。
            - 人物动作要细致，包括肢体语言、表情变化、移动轨迹等。
            
            【节奏控制与时间感】
            - 不要急于推进剧情，每个场景都要充分展开，让时间感拉长。
            - 每个重要时刻都要"慢下来"：通过大量细节描写来延长读者对时间的感知。
            - 在关键动作前增加"准备阶段"：先写角色的心理活动、观察、思考、准备，然后再写动作本身。
            - 在关键动作后增加"反应阶段"：动作完成后，要写角色的感受、环境的反应、其他人的观察等。
            
            【细节密度要求】
            - 每个动作都要分解成多个步骤。
            - 每个场景都要详细描写。
            - 每个对话都要有动作和情绪。
            - 每个心理活动都要有外在表现。
            - 每个环境都要多角度描写。
            
            【多感官描写】
            - 必须使用多感官描写来拉长时间感和增强沉浸感。
            - 每个重要场景都要至少包含3-4种感官的描写。
            - 通过感官描写来营造氛围。
            - 感官描写要有变化，交替使用不同的感官。
            
            【输出格式（必须严格遵守）】
            - 【只输出故事正文】只输出完整的改写故事【正文】，不要任何题目、小标题、总结语、括号内说明、系统提示、道歉、回顾、统计、字符计数等任何元文本内容。
            - 【禁止系统提示和元文本】绝对禁止出现系统提示、道歉、回顾、统计、计数等。
            - 【禁止列表和注释】不要列点，不要使用任何形式的列表、注释或"注释：""说明："之类的段落。
            - 【禁止表情符号】不要输出 emoji、颜文字或特殊符号。
            - 【禁止解释性文字】不要解释你在做什么。
            - 【禁止空行和空白内容】绝对禁止在内容中间或结尾生成任何空行、空白段落或空白内容。
            - 【禁止小节/字数提示】绝对禁止出现"这段大约多少字左右""接下来便是下一节的内容""此时此刻，遥远角落里站着某人默默注视"等写作备注。
            - 【偏向小说风格】可以适当弱化剧本的格式，更偏向于小说风格。
            {myth_core_part}
            {rag_part}
    """


def get_touching_ending_examples():
    """
    从 knowledgeBase/touching_ending_examples.txt 加载人为挑选的「让人感动」级结局示例。
    文件格式：以 --- 分隔每段示例，# 开头的行忽略。用于第三幕结局生成时注入提示词。
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, 'knowledgeBase', 'touching_ending_examples.txt')
        if not os.path.exists(path):
            path = 'knowledgeBase/touching_ending_examples.txt'
        if not os.path.exists(path):
            return ""
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
        # 去掉 # 开头的行，再按 --- 分割成块
        lines = [line for line in raw.splitlines() if not line.strip().startswith('#')]
        text = '\n'.join(lines)
        blocks = [b.strip() for b in text.split('---') if b.strip()]
        if not blocks:
            return ""
        result = "\n\n".join(blocks)
        print(f"已加载 {len(blocks)} 条「让人感动」结局示例")
        return result
    except Exception as e:
        print(f"加载 touching_ending_examples.txt 时出错: {e}")
        return ""


def get_touching_foreshadow_examples():
    """
    从 knowledgeBase/touching_foreshadow_examples.txt 加载「前置关系型样本」。
    文件格式：以 --- 分隔每段示例，# 开头的行忽略。用于第一幕和第二幕生成时注入提示词，学习如何埋下情感伏笔和推进关系。
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, 'knowledgeBase', 'touching_foreshadow_examples.txt')
        if not os.path.exists(path):
            path = 'knowledgeBase/touching_foreshadow_examples.txt'
        if not os.path.exists(path):
            return ""
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
        # 去掉 # 开头的行，再按 --- 分割成块
        lines = [line for line in raw.splitlines() if not line.strip().startswith('#')]
        text = '\n'.join(lines)
        blocks = [b.strip() for b in text.split('---') if b.strip()]
        if not blocks:
            return ""
        result = "\n\n".join(blocks)
        print(f"已加载 {len(blocks)} 条「前置关系型样本」")
        return result
    except Exception as e:
        print(f"加载 touching_foreshadow_examples.txt 时出错: {e}")
        return ""


def generate_punchline_dialogues_for_beat(beat, overall_outline, theme_prompt, punchline_examples_text, myth_core=None):
    """
    方案一·第一阶段：针对当前节拍专门生成 2-3 组「让人笑出来」级的笑点方案。
    方案同时覆盖对白和情节反差，避免长篇只靠固定副角互怼。
    若该节拍属于关键转折/牺牲/收束等庄重场景，则跳过并返回空字符串。
    """
    goal = (beat.get('场景目标') or '')
    if any(kw in goal for kw in ['关键转折', '重大抉择', '牺牲代价', '收束画面', '终极使命完成', '分离', '死亡', '化作', '哭倒', '惩罚']):
        return ""
    scene = goal + "；" + (beat.get('画面要素') or '')
    examples_block = f"\n【参考以下示例的节奏与梗的密度】\n{punchline_examples_text}" if punchline_examples_text else ""
    myth_title = (myth_core or {}).get("title", "")
    must_include = "、".join((myth_core or {}).get("must_include", [])[:8])
    humor_mechanism = beat.get("幽默机制", "") if isinstance(beat, dict) else ""
    system_msg = {
        "role": "system",
        "content": "你是神话改写项目的喜剧设计师，只输出可嵌入正文的笑点方案。笑点必须贴合当前神话的道具、行动、身体反应、旁观误解或人物关系；不要只写固定副角互怼。禁止现代职场、网络流行语、系统面板、直播综艺、低俗辱骂和破坏神话世界观的梗。"
    }
    user_msg = {
        "role": "user",
        "content": f"""针对以下节拍情境，只输出 2 组笑点方案。至少 1 组必须是【非对白情节笑点】（例如动作反差、旁观误解、道具翻车、严肃记录与狼狈状态反差、命名梗），另 1 组可以是简短互怼对白。要求干脆、有梗、让人读能笑出来。不要写解释。

故事主题：{theme_prompt}
当前神话：{myth_title}
本神话识别点：{must_include}
本小节情境：{scene}
本小节优先幽默机制：{humor_mechanism or "请根据情境自行选择，但不要只用互怼"}
{examples_block}

要求：
- 必须围绕本小节的动作、道具、身体感受、旁观误解或当前压力制造笑点，不要泛泛调侃。
- 可以模仿示例的“正经话被一句拆台打歪”的节奏，但不要照抄示例原句。
- 非对白情节笑点请写成一句可直接改写进正文的短场面，例如“神农刚写下‘微苦回甘’，舌头就肿得把‘甘’说成了‘肝’。”
- 互怼对白最多一组，不要让同一个辅助角色承包所有笑点。
- 若当前节拍偏庄重，只输出 1 组非常轻的嘴硬式对白。

请直接输出 1-2 组，每组换行，不要编号、不要解释。"""
    }
    reply = call_qianwen_api(
        [system_msg, user_msg],
        temperature=0.95,
        top_p=0.9,
        repetition_penalty=1.2,
        max_tokens=400
    )
    cleaned = clean_markdown(reply or "").strip()
    return cleaned if cleaned else ""


def generate_outline(theme, rag_content, myth_core=None):
    """
    生成总体大纲（完整故事线）
    """
    system_message = {
        "role": "system",
        "content": get_myth_planning_prompt(rag_content, myth_core) + f"""
            请为神话改写《{theme}》生成完整的总体大纲：
            
            要求：
            - 生成一个完整的故事大纲，包含从开始到结束的完整故事线
            - 大纲应包含：故事背景、主要人物、核心冲突、关键事件、故事结局
            - 大纲长度约500-700字
            - 风格：类似电影《哪吒降世》的幽默改写
            - 必须确保故事线完整，有明确的起承转合
            - 大纲中可按需设置一名【辅助吐槽角色】的姓名与身份；如果本神话本身需要明确反派、夫妻/亲子/师徒等核心关系推动主线，优先写核心人物，不要为了笑点硬加副角。
            - 全篇最终目标是生成 6500~8500 字的长篇神话改写，硬上限 9000 字，所以总体大纲必须比普通版本更厚实但不能膨胀，除了原神话主干事件，只加入必要的【功能性扩展场景】。
            - 允许新增但必须受控的【功能性扩展场景】包括：踏上行动前的筹备、途中见闻、第一次失败尝试、民间/旁观者反应、核心人物间的争执或互相打气、阶段性喘息、行动后的余波收束。
            - 这些新增场景必须服务于以下至少一项：增强幽默、拉长动作过程、补足人物关系、强化情感伏笔、推动主线决策。严禁加入与主线无关的闲笔。
            - 总体大纲里禁止出现未铺垫的预言角色、会预知未来的动物、神秘援手、演播/直播类场景、信心值/任务值等数值化表达。
        """
    }
    
    user_message = {
        "role": "user",
        "content": f"请为神话改写《{theme}》生成完整的总体大纲（500-700字），包含从开始到结束的完整故事线，并主动加入可服务于长篇扩写的功能性扩展场景。"
    }
    
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.8,
        top_p=0.9,
        repetition_penalty=1.2,
        max_tokens=1600
    )
    return clean_markdown(reply)


def split_outline_to_acts(overall_outline, theme, rag_content, myth_core=None):
    """
    将总体大纲分配到三幕，生成三幕分别的大纲和镜头节拍卡（beats）
    
    返回: {"act1": "第一幕大纲", "act2": "第二幕大纲", "act3": "第三幕大纲",
           "act1_beats": [节拍卡1, 节拍卡2, ...], "act2_beats": [...], "act3_beats": [...]}
    每个节拍卡是一个字典，包含：场景目标、画面要素、情绪推动、信息增量、禁止项
    """
    system_message = {
        "role": "system",
        "content": get_myth_planning_prompt(rag_content, myth_core) + f"""
            请根据总体大纲，按【背景→高潮过程→结果】三幕结构分配，生成三幕分别的【详细】大纲和【镜头节拍卡】。
            
            【三幕定位与篇幅比例（必须严格遵守）】
            - 第一幕【背景】：灾因/世界设定/人物登场/为何非做不可/踏上征程。篇幅占比约 28%，大纲约 300-420 字，必须写清「十日并出」类背景、主角处境、同伴如何登场等，不能省略关键背景信息。允许加入筹备、试探、民间反应、赶路插曲等功能性扩展场景。
            - 第二幕【高潮过程】：核心行动的完整过程，必须展开为具体步骤，不能一笔带过。例如后羿射日必须包含：抵达山顶、面对十日、逐箭射落（可分组但要有「第几箭/射落第几个太阳」的递进）、留下最后一日的决策、体力/代价的描写。篇幅占比约 44%，大纲约 450-620 字，节拍卡数量为本幕 8-9 张，确保「过程」被拆成多小节写满，并允许加入与主线强相关的短暂喘息、失败尝试、环境阻力、同伴互怼等扩展场景。
            - 第三幕【结果】：行动完成后的世界变化、民众反应、主角收束与结局寓意。篇幅占比约 28%，大纲约 300-420 字。允许加入余波处理、人物关系回收、情感回应、世界复苏细节等扩展场景，但必须仍然收束到原神话结局。
            
            【关键情节点保留（不可违反）】
            - 分幕时必须从总体大纲中逐条提取关键事件，分配到对应幕中，不得丢失或合并成模糊表述。
            - 第二幕大纲必须包含：该神话「核心动作链」的每一步（如射日则写出射落第1个、第2个…直至留一日的节点；开天则写出劈开、撑天、踏地的阶段；补天则写出寻石、炼石、补窟窿的步骤）。每步在节拍卡中要有对应的一张或明确的小节目标。
            - 三幕合并后的故事必须能还原总体大纲的完整情节，不能比总体大纲少关键细节。
            
            要求：
            - 三幕之间必须承接，不能重复；第一幕结尾要自然衔接到第二幕的开端（如「抵达」「开始行动」）。
            - 每幕大纲要具体、可执行，包含该幕内应出现的具体事件、情节点和必要细节，便于后续按节拍卡逐段写作时不漏情节。
            - 为了支撑 6500~8500 字长篇成稿，每幕都要主动安排若干【功能性扩展节拍】，但总量必须克制。这些节拍只能用于：补动作、补关系、补笑点、补情绪推进、补后果展示，严禁单纯凑字数。
            - 【节拍卡与大纲严格对齐（关键要求）】：
              * 节拍卡必须严格按照本幕大纲中的关键情节点顺序生成，每张节拍卡的"场景目标"必须直接对应大纲中的一个或多个具体事件，不能偏离大纲内容。
              * 节拍卡的数量和顺序必须覆盖大纲中的所有关键情节点，不能遗漏大纲中提到的任何重要事件，也不能添加大纲中没有的新情节。
              * 例如：如果第二幕大纲写了"抵达山顶、面对十日、射落第1个太阳、射落第2-3个太阳、射落第4-6个太阳、射落第7-9个太阳、留下最后一日的决定、体力耗尽"，那么节拍卡必须按照这个顺序，每张节拍卡对应其中一个或几个步骤，不能跳过或打乱顺序。
              * 节拍卡的"场景目标"应该明确写出对应大纲中的哪个具体事件（如"射落第1个太阳"而不是模糊的"开始射箭"），确保节拍卡与大纲一一对应。
              * 如果本幕大纲没有写到某个新角色、新道具、新地点、新设定，该节拍卡就绝对不能新增它。
            - 在设计每张【镜头节拍卡】时，要为后续的幽默留出空间：预留至少一个【对白上的抛接点】和一个【非对白的反差点】（可通过画面要素或情绪推动中的具体细节体现）。
            - 第一幕输出 5-6 张节拍卡，第二幕输出 8-9 张节拍卡，第三幕输出 5-6 张节拍卡。每张节拍卡必须包含以下字段：
              * 场景目标：这一小段要完成什么叙事功能（铺垫/冲突升级/关键转折/代价/收束等）
              * 画面要素：至少2个可拍摄的画面/动作细节（非抽象词）
              * 情绪推动：角色此刻情绪从A到B（例如烦闷→决断、焦灼→咬牙、崩溃→释然）
              * 信息增量：这一节新增的信息是什么（不能重复前文）
              * 禁止项：列出1-2条"这一节绝对不能写什么"（如新角色突然出现、跳到结局、跑去写日常等）
              * 情感伏笔：这一拍为结尾感动埋什么伏笔（如主角把唯一资源留给别人、平时插科打诨的人在关键时刻突然认真、一个反复出现的小动作等）
              * 关系推进：主角和情感落点角色（核心人物或必要辅助角色）的关系如何变化（如从误解到理解、从担心到守护等）
              * 幽默机制：本拍优先使用哪一种笑点来源，必须具体到情节，例如“试药反差”“村民误解”“道具翻车”“严肃记录与狼狈状态反差”“药性命名”，不能只写“互怼”
            - 对所有神话通用：禁止写出“预知未来的动物”“神秘外援”“演播厅/直播间”“信心值/任务值”“系统/程序/工程”等跑偏设定。
            
            三幕逻辑总结：
            - 第一幕：背景与动机建立完毕，以「踏上征途/开始行动」类节点收尾。
            - 第二幕：核心行动全过程（步骤化、可数），不跳过任何关键步骤，以「行动完成/最后一击」类节点收尾。
            - 第三幕：结果、世界状态、人物收束与寓意，必须有明确结局与感动收束。
        """
    }
    
    user_message = {
        "role": "user",
        "content": f"""
总体大纲：
{overall_outline}

请将以上总体大纲分配到三幕，按【背景→高潮过程→结果】划分，生成三幕分别的【详细】大纲和【镜头节拍卡】。若总体大纲中已出现【辅助吐槽角色】的姓名与身份，请在后续节拍卡中谨慎延续该角色，但必须让核心人物、核心道具和主线冲突保持主位。要求：
1. 第一幕【背景】大纲（约300-420字）：包含灾因、世界设定、人物登场、为何非做不可、踏上征程等，必须写清神话背景（如十日并出、百姓遭殃），不能省略关键背景。结尾落在「开始行动/上路」。允许加入筹备、赶路、第一次试探、百姓反应等功能性扩展场景。
2. 第二幕【高潮过程】大纲（约450-620字）：核心行动的完整过程，必须展开为具体步骤。例如后羿射日须写出：抵达山顶、面对十日、逐箭射落（射落第1个…第9个、留下最后一日的决定）、体力与代价。盘古开天须写出：挥斧劈开、撑天、踏地等阶段。不得一笔带过或合并成「他一口气完成了」。允许加入与主线强相关的失败尝试、环境阻力、同伴互怼、阶段性喘息，但不许跑题。
3. 第三幕【结果】大纲（约300-420字）：行动完成后的世界变化、民众反应、主角收束与结局寓意，不能重复前两幕。允许加入余波处理、关系回收、世界复苏与情感回应等功能性扩展场景。
4. 【节拍卡生成关键要求（必须严格遵守）】：
   - 生成大纲后，请先提取每幕大纲中的关键情节点（用序号或分号分隔的各个事件），然后按照这些关键情节点的顺序，逐条生成对应的节拍卡。
   - 每张节拍卡的"场景目标"必须明确对应大纲中的一个具体事件，不能偏离。例如：如果大纲写了"射落第1个太阳"，节拍卡的场景目标就应该是"射落第1个太阳"或"完成射落第1个太阳的动作"，而不是"开始射箭"或"面对困难"等模糊表述。
   - 节拍卡的数量必须足够覆盖大纲中的所有关键情节点，不能遗漏。如果大纲中有8个关键步骤，就需要更多节拍卡把它们拆细，同时加入紧贴主线的扩展节拍。
   - 节拍卡的顺序必须与大纲中事件的顺序一致，不能打乱。
   - 如果大纲里没有写到某个新角色、新道具、新地点、新设定，该节拍卡绝对不能新增它。
5. 第一幕 5-6 张节拍卡，第二幕 8-9 张节拍卡，第三幕 5-6 张节拍卡。每张节拍卡必须包含以下字段：
   - 场景目标：这一小段要完成什么叙事功能
   - 画面要素：至少2个可拍摄的画面/动作细节（非抽象词）
   - 情绪推动：角色此刻情绪从A到B
   - 信息增量：这一节新增的信息是什么（不能重复前文）
   - 禁止项：列出1-2条"这一节绝对不能写什么"
   - 情感伏笔：这一拍为结尾感动埋什么伏笔（如主角把唯一资源留给别人、平时插科打诨的人在关键时刻突然认真、一个反复出现的小动作等）
   - 关系推进：主角和情感落点角色（核心人物或必要辅助角色）的关系如何变化（如从误解到理解、从担心到守护等）
   - 幽默机制：本拍优先使用的笑点来源；必须在对白互怼、动作反差、旁观误解、道具翻车、严肃记录反差、命名梗、嘴硬自嘲中轮换，避免连续依赖同一辅助角色吐槽
6. 通用禁区：不要生成预言动物、神秘外援、演播厅/直播间、信心值/任务值、系统/程序/工程等跑偏设定。

请严格按照以下格式输出：
第一幕大纲（xx字）：[第一幕的具体内容]

第一幕节拍卡1：
场景目标：[叙事功能]
画面要素：[至少2个可拍摄的画面/动作细节]
情绪推动：[情绪从A到B]
信息增量：[新增信息]
禁止项：[1-2条禁止项]
情感伏笔：[为结尾感动埋什么伏笔]
关系推进：[主角和情感落点角色的关系如何变化]
幽默机制：[本拍优先使用的笑点来源]

第一幕节拍卡2：
场景目标：[叙事功能]
画面要素：[至少2个可拍摄的画面/动作细节]
情绪推动：[情绪从A到B]
信息增量：[新增信息]
禁止项：[1-2条禁止项]

...（继续输出5-6张节拍卡）

第二幕大纲（xx字）：[第二幕的具体内容]

第二幕节拍卡1：
场景目标：[叙事功能]
画面要素：[至少2个可拍摄的画面/动作细节]
情绪推动：[情绪从A到B]
信息增量：[新增信息]
禁止项：[1-2条禁止项]

...（继续输出8-9张节拍卡）

第三幕大纲（xx字）：[第三幕的具体内容]

第三幕节拍卡1：
场景目标：[叙事功能]
画面要素：[至少2个可拍摄的画面/动作细节]
情绪推动：[情绪从A到B]
信息增量：[新增信息]
禁止项：[1-2条禁止项]

...（继续输出5-6张节拍卡）
        """
    }
    
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.2,
        max_tokens=5200  # 长篇版本需要更多大纲与节拍卡
    )
    
    # 解析三幕大纲和节拍卡
    cleaned_reply = clean_markdown(reply)
    parse_reply = cleaned_reply
    parse_reply = re.sub(r'(?m)^\s*[-*]\s*(?=(场景目标|画面要素|情绪推动|信息增量|禁止项|情感伏笔|关系推进|幽默机制)[：:])', '', parse_reply)
    parse_reply = re.sub(
        r'(第[一二三]幕)\s*(?:镜头)?\s*节拍卡\s*([0-9一二三四五六七八九十]+)',
        r'\1节拍卡\2',
        parse_reply
    )
    parse_reply = re.sub(r'(第[一二三]幕)\s*大纲', r'\1大纲', parse_reply)
    
    # 尝试提取三幕大纲（支持新格式：第一幕大纲（xx字）：）
    act1_match = re.search(r'第一幕[大纲：:]*（[^）]*）[：:]*\s*(.*?)(?=第一幕节拍卡|第二幕|$)', parse_reply, re.DOTALL)
    if not act1_match:
        act1_match = re.search(r'第一幕[大纲：:]*\s*(.*?)(?=第一幕节拍卡|第二幕|$)', parse_reply, re.DOTALL)
    act2_match = re.search(r'第二幕[大纲：:]*（[^）]*）[：:]*\s*(.*?)(?=第二幕节拍卡|第三幕|$)', parse_reply, re.DOTALL)
    if not act2_match:
        act2_match = re.search(r'第二幕[大纲：:]*\s*(.*?)(?=第二幕节拍卡|第三幕|$)', parse_reply, re.DOTALL)
    act3_match = re.search(r'第三幕[大纲：:]*（[^）]*）[：:]*\s*(.*?)(?=第三幕节拍卡|$)', parse_reply, re.DOTALL)
    if not act3_match:
        act3_match = re.search(r'第三幕[大纲：:]*\s*(.*?)(?=第三幕节拍卡|$)', parse_reply, re.DOTALL)
    
    act1_outline = act1_match.group(1).strip() if act1_match else ""
    act2_outline = act2_match.group(1).strip() if act2_match else ""
    act3_outline = act3_match.group(1).strip() if act3_match else ""
    
    # 解析节拍卡（新格式：包含多个字段的字典）
    def parse_beat_cards(act_name, cleaned_reply):
        """解析节拍卡，返回字典列表"""
        # 只能把“行首的下一张节拍卡/下一幕大纲”视作边界。
        # 旧正则把正文里的“第三幕核心节点”也当边界，导致第三幕经常解析成 0-1 张卡。
        card_no = r'(?:\d+|[一二三四五六七八九十]+)'
        pattern = rf'^\s*{act_name}节拍卡{card_no}[：:、.．]*\s*(.*?)(?=^\s*{act_name}节拍卡{card_no}[：:、.．]|^\s*(?:第一幕|第二幕|第三幕)大纲|^\s*(?:第一幕|第二幕|第三幕)节拍卡{card_no}[：:、.．]|$)'
        matches = re.finditer(pattern, cleaned_reply, re.DOTALL | re.MULTILINE)
        beat_cards = []
        field_boundary = r'(?=场景目标|画面要素|情绪推动|信息增量|禁止项|情感伏笔|关系推进|幽默机制|$)'
        for match in matches:
            beat_text = match.group(1).strip()
            if not beat_text:
                continue
            # 解析各个字段
            beat_card = {}
            # 场景目标
            goal_match = re.search(r'场景目标[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if goal_match:
                beat_card['场景目标'] = goal_match.group(1).strip()
            # 画面要素
            visual_match = re.search(r'画面要素[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if visual_match:
                beat_card['画面要素'] = visual_match.group(1).strip()
            # 情绪推动
            emotion_match = re.search(r'情绪推动[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if emotion_match:
                beat_card['情绪推动'] = emotion_match.group(1).strip()
            # 信息增量
            info_match = re.search(r'信息增量[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if info_match:
                beat_card['信息增量'] = info_match.group(1).strip()
            # 禁止项
            ban_match = re.search(r'禁止项[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if ban_match:
                beat_card['禁止项'] = ban_match.group(1).strip()
            # 情感伏笔
            emotion_foreshadow_match = re.search(r'情感伏笔[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if emotion_foreshadow_match:
                beat_card['情感伏笔'] = emotion_foreshadow_match.group(1).strip()
            # 关系推进
            relationship_match = re.search(r'关系推进[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if relationship_match:
                beat_card['关系推进'] = relationship_match.group(1).strip()
            humor_match = re.search(r'幽默机制[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if humor_match:
                beat_card['幽默机制'] = humor_match.group(1).strip()
            
            # 如果解析到了至少一个字段，就添加到列表
            if beat_card:
                beat_cards.append(beat_card)
        
        # 如果新格式解析失败，尝试旧格式（简单的事件清单）
        if not beat_cards:
            old_pattern = rf'{act_name}事件清单[：:]*\s*(.*?)(?=第二幕|第三幕|$)'
            old_match = re.search(old_pattern, cleaned_reply, re.DOTALL)
            if old_match:
                beats_text = old_match.group(1)
                for line in beats_text.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    match = re.match(r'^\d+[\.、\s]+\s*(.+)', line)
                    if match:
                        beat_cards.append({'场景目标': match.group(1).strip(), '画面要素': '', '情绪推动': '', '信息增量': '', '禁止项': ''})
        
        return beat_cards[:9]  # 收紧节拍卡数量上限，避免稀释单卡质量
    
    act1_beats = parse_beat_cards('第一幕', parse_reply)
    act2_beats = parse_beat_cards('第二幕', parse_reply)
    act3_beats = parse_beat_cards('第三幕', parse_reply)
    
    # 验证节拍卡数量是否合理
    if len(act1_beats) < 5:
        print(f"警告：第一幕只解析到 {len(act1_beats)} 张节拍卡，建议至少 5-6 张")
    if len(act2_beats) < 8:
        print(f"警告：第二幕只解析到 {len(act2_beats)} 张节拍卡，建议至少 8-9 张")
    if len(act3_beats) < 5:
        print(f"警告：第三幕只解析到 {len(act3_beats)} 张节拍卡，建议至少 5-6 张")
    
    # 如果解析失败，使用原始回复作为fallback
    if not act1_outline or not act2_outline or not act3_outline:
        print("警告：无法自动解析三幕大纲，使用原始回复")
        return {
            "act1": cleaned_reply,
            "act2": cleaned_reply,
            "act3": cleaned_reply,
            "act1_beats": [],
            "act2_beats": [],
            "act3_beats": []
        }
    
    return {
        "act1": act1_outline,
        "act2": act2_outline,
        "act3": act3_outline,
        "act1_beats": act1_beats,
        "act2_beats": act2_beats,
        "act3_beats": act3_beats
    }


def outline_plan_is_usable(acts_outline: dict, myth_core: dict = None) -> bool:
    """
    规划结果验收：
    - 三幕大纲不能为空
    - 节拍卡数量必须达到长篇最低要求
    """
    if not acts_outline:
        return False

    if not acts_outline.get("act1") or not acts_outline.get("act2") or not acts_outline.get("act3"):
        return False

    combined_outline = "\n".join([
        acts_outline.get("act1", ""),
        acts_outline.get("act2", ""),
        acts_outline.get("act3", ""),
    ])
    if contains_myth_core_violation(combined_outline, myth_core or {}):
        return False
    if myth_core and not myth_core_requirement_met(combined_outline, myth_core, final=False):
        return False

    if contains_plan_drift(acts_outline.get("act1", ""), myth_core):
        return False
    if contains_plan_drift(acts_outline.get("act2", ""), myth_core):
        return False
    if contains_plan_drift(acts_outline.get("act3", ""), myth_core):
        return False

    if len(acts_outline.get("act1_beats", [])) < 5:
        return False
    if len(acts_outline.get("act2_beats", [])) < 8:
        return False
    if len(acts_outline.get("act3_beats", [])) < 5:
        return False

    for beat_group in (
        acts_outline.get("act1_beats", []),
        acts_outline.get("act2_beats", []),
        acts_outline.get("act3_beats", []),
    ):
        for beat in beat_group:
            beat_text = " ".join(
                str(beat.get(k, "")) for k in ["场景目标", "画面要素", "信息增量", "禁止项"]
            ) if isinstance(beat, dict) else str(beat)
            if isinstance(beat, dict):
                for required_field in ("场景目标", "画面要素", "信息增量"):
                    if len(str(beat.get(required_field, "")).strip()) < 4:
                        return False
            if contains_plan_drift(beat_text, myth_core):
                return False

    return True


def generate_touching_storyline(overall_outline, act1_outline, act2_outline, act3_outline, prompt, rag_content, myth_core=None):
    """
    基于总体大纲和三幕大纲，生成一条贯穿三幕的情绪线索。
    优先服务娱乐性与人物弧光；只有故事自然适合时才做感动升华。
    
    返回: {
        "act1_touching": "第一幕的感动线索部分（铺垫）",
        "act2_touching": "第二幕的感动线索部分（发展）",
        "act3_touching": "第三幕的感动线索部分（高潮与收束）"
    }
    """
    myth_title = (myth_core or {}).get("title", "")
    extra_storyline_constraints = ""
    if myth_title == "后羿射日":
        extra_storyline_constraints = """
【《后羿射日》情绪线硬约束】
- 情绪线必须服务“射落九日、主动留一日、天地恢复”的主线。
- 第三幕只能写后羿主动留下最后一个太阳，并由阿满在青竹简上记录“射九留一”。
- 严禁写“第十个太阳隐入云中”“后羿甩出最后一箭”“最后一个太阳被射掉”“漏了个靶子”等会破坏射九留一的表达。
- 阿满的情绪线只能是怕热护简、记箭序、最后郑重记录；不得让阿满摔倒或制造意外帮助后羿命中。
"""
    system_message = {
        "role": "system",
        "content": get_myth_system_prompt_base(rag_content, myth_core) + f"""
            你是一位擅长设计情绪线索的编剧。请基于给定的故事大纲，设计一条贯穿三幕的情绪线索。
            
            【情绪线索的设计原则】
            - 这条线索应该与主线故事自然融合，不是生硬添加的支线。
            - 本项目是神话娱乐改写，整体优先幽默、风趣、轻微搞怪；情绪升华只做自然余味，不要写成作文式煽情。
            - 第一幕：铺垫阶段 - 埋下人物动机、误解、笑点来源或小小执念。
            - 第二幕：发展阶段 - 在主角行动过程中，让误解、笑点和压力升级。
            - 第三幕：收束阶段 - 根据神话类型选择轻松余味、爽朗认可、温柔一笑或必要的感动升华。
            
            【可选情绪类型】
            - 幽默回收：前文的误会、道具翻车、口头禅在结尾变成轻松余味。
            - 爽朗认可：曾经嘲笑的人承认主角有点本事，但可以嘴硬。
            - 温柔升华：主角完成核心行动后，环境或人物反应用一两个动作点到为止。
            - 悲剧/牺牲：只有原神话本身需要悲剧或牺牲时才使用，不要强塞。
            
            【注意事项】
            - 情绪线索要自然，不能为了感动而强行煽情。
            - 要与幽默基调平衡；若结尾不方便感动，就用风趣、轻快、余味式收束。
            - 每幕线索应该具体、可执行，便于在写作时融入。
            {extra_storyline_constraints}
        """
    }
    
    user_message = {
        "role": "user",
        "content": f"""
请为《{prompt}》设计一条贯穿三幕的情绪线索，优先服务幽默风趣和人物弧光；若结尾适合，再自然加入轻微升华。

【总体大纲】
{overall_outline}

【第一幕大纲】
{act1_outline}

【第二幕大纲】
{act2_outline}

【第三幕大纲】
{act3_outline}

请设计一条情绪线索，并将其分成三部分，分别对应三幕：
1. 第一幕情绪线索（铺垫阶段）：约50-80字，描述第一幕的误解、动机或笑点种子
2. 第二幕情绪线索（发展阶段）：约50-80字，描述第二幕如何升级压力、误会和幽默
3. 第三幕情绪线索（收束阶段）：约80-120字，描述第三幕如何完成轻松余味、爽朗认可或自然升华

请严格按照以下格式输出：
第一幕感动线索：[第一幕的情绪线索内容]
第二幕感动线索：[第二幕的情绪线索内容]
第三幕感动线索：[第三幕的情绪线索内容]
        """
    }
    
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.8,
        top_p=0.9,
        repetition_penalty=1.2,
        max_tokens=800
    )
    
    cleaned_reply = clean_markdown(reply)
    
    # 解析回复，提取三幕的感动线索
    act1_touching = ""
    act2_touching = ""
    act3_touching = ""
    
    # 尝试提取第一幕感动线索
    match1 = re.search(r'第一幕感动线索[：:]\s*(.+?)(?=第二幕感动线索|$)', cleaned_reply, re.DOTALL)
    if match1:
        act1_touching = match1.group(1).strip()
    
    # 尝试提取第二幕感动线索
    match2 = re.search(r'第二幕感动线索[：:]\s*(.+?)(?=第三幕感动线索|$)', cleaned_reply, re.DOTALL)
    if match2:
        act2_touching = match2.group(1).strip()
    
    # 尝试提取第三幕感动线索
    match3 = re.search(r'第三幕感动线索[：:]\s*(.+?)$', cleaned_reply, re.DOTALL)
    if match3:
        act3_touching = match3.group(1).strip()
    
    # 如果解析失败，尝试其他格式
    if not act1_touching or not act2_touching or not act3_touching:
        # 尝试按行分割
        lines = cleaned_reply.split('\n')
        for i, line in enumerate(lines):
            if '第一幕' in line and '感动' in line:
                if i + 1 < len(lines):
                    act1_touching = lines[i + 1].strip()
            elif '第二幕' in line and '感动' in line:
                if i + 1 < len(lines):
                    act2_touching = lines[i + 1].strip()
            elif '第三幕' in line and '感动' in line:
                if i + 1 < len(lines):
                    act3_touching = lines[i + 1].strip()
    
    # 如果仍然没有提取到，使用整个回复作为第三幕的感动线索（至少保证有内容）
    if not act3_touching:
        act3_touching = cleaned_reply.strip()[:200]
    
    return {
        "act1_touching": act1_touching,
        "act2_touching": act2_touching,
        "act3_touching": act3_touching
    }


def generate_act1(act1_outline, overall_outline, rag_content, prompt, act1_beats=None, touching_storyline=None, myth_core=None):
    """
    生成第一幕（600-800字）
    """
    # 提取幽默样本
    humor_samples = get_humor_samples()
    humor_reference = f"\n\n【全部哪吒风格参考样本（请学习其表达方式，并在文中穿插若干仿写哪吒风格的幽默点，勿通篇哪吒口吻）】\n{humor_samples}" if humor_samples else ""
    
    # 提取前置关系型样本（用于学习如何埋下情感伏笔和推进关系）
    foreshadow_examples = get_touching_foreshadow_examples()
    foreshadow_reference = f"\n\n【前置关系型样本（请学习如何在前两幕埋下情感伏笔和推进关系）】\n{foreshadow_examples}" if foreshadow_examples else ""
    
    # 第一幕：按节拍卡逐小节生成，再拼接成完整第一幕
    system_content = get_myth_system_prompt_base(rag_content, myth_core) + humor_reference + foreshadow_reference

    # 方案二：加载人为挑选的「让人笑出来」对白示例，每小节注入
    punchline_examples = get_punchline_examples(myth_core)

    # 如果没有节拍卡，退化为单节拍，交给统一逻辑处理
    if not act1_beats:
        act1_beats = [{
            "场景目标": act1_outline,
            "画面要素": "",
            "情绪推动": "",
            "信息增量": "",
            "禁止项": "",
            "情感伏笔": "",
            "关系推进": ""
        }]

    total_beats = len(act1_beats)
    # 第一幕【背景】长篇版本目标 1600~2100 字
    target_min_total, target_max_total = MYTH_ACT_TARGETS["act1"]
    base_min = max(220, target_min_total // total_beats - 25)
    base_max = target_max_total // total_beats + 45

    segments = []
    accumulated_text = ""

    for idx, beat in enumerate(act1_beats, 1):
        # 方案一·第一阶段：先为本节拍生成笑点对白（庄重节拍会跳过）
        punchlines = generate_punchline_dialogues_for_beat(beat, overall_outline, prompt, punchline_examples, myth_core)
        segment = generate_segment_for_beat(
            act_name="第一幕",
            beat_index=idx,
            total_beats=total_beats,
            beat=beat,
            overall_outline=overall_outline,
            act_outline=act1_outline,
            prev_text=accumulated_text,
            prompt=prompt,
            system_content=system_content,
            target_min_len=base_min,
            target_max_len=base_max,
            act_id="act1",
            punchlines_to_embed=punchlines,
            punchline_examples_text=punchline_examples,
            touching_storyline=touching_storyline,
            myth_core=myth_core
        )
        segments.append(segment)
        accumulated_text = (accumulated_text + "\n" + segment).strip() if accumulated_text else segment

    # 简单拼接为第一幕全文
    return "\n\n".join(segments)


def generate_act2(act2_outline, overall_outline, act1, prompt, act2_beats=None, touching_storyline=None, myth_core=None):
    """
    生成第二幕（900-1100字）
    """
    # 提取幽默样本
    humor_samples = get_humor_samples()
    humor_reference = f"\n\n【全部哪吒风格参考样本（请学习其表达方式，并在文中穿插若干仿写哪吒风格的幽默点，勿通篇哪吒口吻）】\n{humor_samples}" if humor_samples else ""
    
    # 提取前置关系型样本（用于学习如何埋下情感伏笔和推进关系）
    foreshadow_examples = get_touching_foreshadow_examples()
    foreshadow_reference = f"\n\n【前置关系型样本（请学习如何在前两幕埋下情感伏笔和推进关系）】\n{foreshadow_examples}" if foreshadow_examples else ""
    
    # 第二幕：按节拍卡逐小节生成，再拼接成完整第二幕
    system_content = get_myth_system_prompt_base(None, myth_core) + humor_reference + foreshadow_reference

    punchline_examples = get_punchline_examples(myth_core)

    if not act2_beats:
        act2_beats = [{
            "场景目标": act2_outline,
            "画面要素": "",
            "情绪推动": "",
            "信息增量": "",
            "禁止项": "",
            "情感伏笔": "",
            "关系推进": ""
        }]

    total_beats = len(act2_beats)
    # 第二幕【高潮过程】长篇版本目标 2600~3400 字，确保核心过程写满
    target_min_total, target_max_total = MYTH_ACT_TARGETS["act2"]
    base_min = max(240, target_min_total // total_beats - 20)
    base_max = target_max_total // total_beats + 55

    segments = []
    # 将第一幕全文作为"更早前文"，帮助第二幕承接，但在单节生成时只截取尾部片段
    accumulated_text = act1.strip()

    for idx, beat in enumerate(act2_beats, 1):
        punchlines = generate_punchline_dialogues_for_beat(beat, overall_outline, prompt, punchline_examples, myth_core)
        segment = generate_segment_for_beat(
            act_name="第二幕",
            beat_index=idx,
            total_beats=total_beats,
            beat=beat,
            overall_outline=overall_outline,
            act_outline=act2_outline,
            prev_text=accumulated_text,
            prompt=prompt,
            system_content=system_content,
            target_min_len=base_min,
            target_max_len=base_max,
            act_id="act2",
            punchlines_to_embed=punchlines,
            punchline_examples_text=punchline_examples,
            touching_storyline=touching_storyline,
            myth_core=myth_core
        )
        segments.append(segment)
        accumulated_text = (accumulated_text + "\n" + segment).strip()

    return "\n\n".join(segments)


def generate_act3(act3_outline, overall_outline, act2, prompt, act3_beats=None, touching_storyline=None, emotional_character=None, myth_core=None):
    """
    生成第三幕（600-800字）
    emotional_character: 情感落点角色名称（如"铁牛"、"小徒弟"等）
    """
    # 提取感动结局样本
    touching_ending_examples = get_touching_ending_examples()
    
    # 第三幕使用专用的感动收束优先系统提示
    system_content = get_act3_emotional_system_prompt(None, myth_core) + (f"\n\n【感动结局参考样本（请学习其情感表达与节奏）】\n{touching_ending_examples}" if touching_ending_examples else "")

    punchline_examples = get_punchline_examples(myth_core)

    # 如果没有节拍卡，退化为单节拍，交给统一逻辑处理
    if not act3_beats:
        act3_beats = [{
            "场景目标": act3_outline,
            "画面要素": "",
            "情绪推动": "",
            "信息增量": "",
            "禁止项": "",
            "情感伏笔": "",
            "关系推进": ""
        }]

    total_beats = len(act3_beats)
    # 第三幕【结果】长篇版本目标 1600~2100 字
    target_min_total, target_max_total = MYTH_ACT_TARGETS["act3"]
    base_min = max(220, target_min_total // total_beats - 25)
    base_max = target_max_total // total_beats + 45

    segments = []
    # 将第二幕全文作为"更早前文"，帮助第三幕承接，在单节生成时只截取尾部片段
    accumulated_text = act2.strip()
    
    # 提取前文中的关键意象作为memory_hooks（用于验收时检查是否回收）
    memory_hooks = []
    if accumulated_text:
        # 简单提取：寻找常见的意象词
        common_hooks = ['干粮', '水壶', '弓', '手', '那句话', '那句话', '那句话']
        for hook in common_hooks:
            if hook in accumulated_text:
                memory_hooks.append(hook)

    for idx, beat in enumerate(act3_beats, 1):
        # 最后1-2张节拍卡使用专门的结尾beat生成函数
        if idx >= total_beats - 1:
            segment = generate_act3_ending_beat(
                act_name="第三幕",
                beat_index=idx,
                total_beats=total_beats,
                beat=beat,
                overall_outline=overall_outline,
                act_outline=act3_outline,
                prev_text=accumulated_text,
                prompt=prompt,
                system_content=system_content,
                target_min_len=base_min,
                target_max_len=base_max,
                touching_ending_examples=touching_ending_examples,
                emotional_character=emotional_character,
                myth_core=myth_core
            )
        else:
            # 其他节拍卡使用普通生成函数
            punchlines = generate_punchline_dialogues_for_beat(beat, overall_outline, prompt, punchline_examples, myth_core)
            segment = generate_segment_for_beat(
                act_name="第三幕",
                beat_index=idx,
                total_beats=total_beats,
                beat=beat,
                overall_outline=overall_outline,
                act_outline=act3_outline,
                prev_text=accumulated_text,
                prompt=prompt,
                system_content=system_content,
                target_min_len=base_min,
                target_max_len=base_max,
                act_id="act3",
                punchlines_to_embed=punchlines,
                punchline_examples_text=punchline_examples,
                touching_storyline=touching_storyline,
                touching_ending_examples=touching_ending_examples,
                myth_core=myth_core
            )
        segments.append(segment)
        accumulated_text = (accumulated_text + "\n" + segment).strip()

    final_act3 = "\n\n".join(segments)

    # 仍保留一次整体质量检查（长度/繁体/镜头括号等），仅做告警，不再整体重写
    if not validate_act3(final_act3):
        print("警告：第三幕整体质量校验未通过（长度/格式/繁体检测），但已按节拍卡逐段生成。")
    
    emotion_required_titles = {"梁山伯与祝英台", "孟姜女哭长城", "牛郎织女", "嫦娥奔月", "女娲补天", "盘古开天地"}
    emotion_required = (myth_core or {}).get("title") in emotion_required_titles

    # 悲剧/牺牲类神话才强制感动验收；其他娱乐改写允许用幽默余味收束。
    if emotion_required and not validate_touching_ending(final_act3, memory_hooks):
        print("警告：第三幕感动结局验收未通过，正在重新生成最后两拍...")
        # 重新生成最后两拍
        for idx in range(max(1, total_beats - 1), total_beats + 1):
            if idx <= len(act3_beats):
                beat = act3_beats[idx - 1]
                accumulated_text_before = "\n\n".join(segments[:idx-1]) if idx > 1 else act2.strip()
                new_segment = generate_act3_ending_beat(
                    act_name="第三幕",
                    beat_index=idx,
                    total_beats=total_beats,
                    beat=beat,
                    overall_outline=overall_outline,
                    act_outline=act3_outline,
                    prev_text=accumulated_text_before,
                    prompt=prompt,
                    system_content=system_content,
                    target_min_len=base_min,
                    target_max_len=base_max,
                    touching_ending_examples=touching_ending_examples,
                    emotional_character=emotional_character,
                    myth_core=myth_core
                )
                segments[idx - 1] = new_segment
        final_act3 = "\n\n".join(segments)
        print("已重新生成最后两拍")

    return final_act3


def validate_act3(script: str) -> bool:
    """
    第三幕专用质量校验：
    - 字数/字符数需匹配长篇第三幕目标，明显过短或过长判失败
    - 含常见繁体字判失败（粗略检测）
    - 含括号镜头/元文本关键字判失败
    - 出现连续多行仅由标点/空格组成的“诗歌体碎行”判失败
    """
    if not script:
        return False

    # 1. 粗略长度控制：使用长篇第三幕目标，避免正常 1450~1850 字被旧阈值误报
    act3_min, act3_max = MYTH_ACT_TARGETS["act3"]
    if len(script) < max(900, act3_min - 350):
        return False
    if len(script) > act3_max + 450:
        return False

    # 2. 粗略繁体字检测（常见繁体字集合，命中任意一个就视为不合格）
    trad_chars = set("萬與專業東絲兩嚴個豐臨為麗舉樂鄉書買亂爭於雲亞產畢實寧眾優會傢價億債傷傾後門風體們發戰愛國頭聲靜場這顏顯點")
    if any(ch in trad_chars for ch in script):
        return False

    # 3. 括号镜头/元文本关键字
    forbidden_meta_phrases = [
        "（最终画面", "（最終畫面",
        "（镜头", "（鏡頭",
        "（远景", "（遠景",
        "遠鏡頭", "远镜头",
        "镜头切", "鏡頭切",
    ]
    if any(phrase in script for phrase in forbidden_meta_phrases):
        return False

    # 4. 连续多行只有标点/空格（诗歌体碎行）
    lines = script.splitlines()
    punct_chars = set("，。！？；：、…—-·「」『』（）()【】[]《》\"' \t ")
    pure_punct_run = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            pure_punct_run = 0
            continue
        if all(ch in punct_chars for ch in stripped):
            pure_punct_run += 1
            if pure_punct_run >= 3:
                return False
        else:
            pure_punct_run = 0

    return True


def strip_beat_markers(text: str) -> str:
    """
    清理正文中的节拍标记【B1】【B2】……，供最终输出使用
    """
    if not text:
        return text
    return re.sub(r'【B\d+】\s*', '', text)


def clean_story_postprocess(text: str, myth_core: dict = None) -> str:
    """
    最终成稿的统一清洁：
    - 删除英文单词，避免 knot/back/shoulders 这类夹杂破坏时代感
    - 删除形如"（这段共xxx字）"的括号字数提示
    - 保留正常中文与标点
    - 删除中文之间误插入的空格
    """
    if not text:
        return text

    text = remove_meta_residue(text)
    text = normalize_language_pollution(text)
    text = remove_body_drift_residue(text)
    text = apply_myth_specific_postprocess(text, myth_core)

    # 删除连续英文字符（忽略大小写），直接抹掉英文单词
    text = re.sub(r'[A-Za-z]+', '', text)
    text = re.sub(r'[\u0370-\u03FF\u0400-\u052F]+', '', text)

    # 删除常见的字数统计括号尾巴
    text = re.sub(r'（这段共[^）]*字）', '', text)
    text = re.sub(r'\(这段共[^)]*字\)', '', text)
    text = re.sub(r'[（(](?:註|注|备注)[:：][^）)]{0,120}[）)]', '', text)
    text = remove_meta_residue(text)
    text = normalize_language_pollution(text)
    text = remove_body_drift_residue(text)

    # 删掉中文字符之间误插入的空格
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)

    # 再清理可能多出来的多余空格
    text = re.sub(r'[ ]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = split_long_paragraphs(text)
    text = remove_meta_residue(text)
    text = remove_body_drift_residue(text)
    text = apply_myth_specific_postprocess(text, myth_core)
    return text.strip()


def has_obvious_garbled_text(text: str, myth_core: dict = None) -> bool:
    """
    检测明显的乱码/跑偏/格式污染：
    - 常见未完成提示
    - emoji/装饰符号
    - 英文夹杂过多
    - 繁体字过多
    - 连续异常标点
    """
    if not text:
        return True

    if has_hard_meta_residue(text):
        return True

    if any(phrase in text for phrase in BAD_META_PHRASES):
        return True

    if any(re.search(pattern, text) for pattern in META_RESIDUE_PATTERNS):
        return True

    if re.search(r'[\U0001F300-\U0001FAFF]', text):
        return True

    if re.search(r'[\u0370-\u03FF\u0400-\u052F]', text):
        return True

    if re.search(r'[;；]{4,}|[.。]{5,}|[!！?？]{4,}', text):
        return True

    if re.search(r'\[[^\]]{0,40}(插入|互动场景|待补|补写)[^\]]{0,40}\]', text):
        return True

    if any(phrase in text for phrase in BAD_META_PHRASES):
        return True

    meta_like_patterns = [
        r'（此处[^）]{0,30}插入[^）]*）',
        r'（此时此刻[^）]{0,120}）',
        r'（[^）]{0,30}(这段大约|多少字左右|接下来便是|下一节|备注|隐藏章节|待补)[^）]*）',
        r'（这段[^）]{0,30}符合要求[^）]*）',
        r'（[^）]{0,20}画面要素[^）]*）',
        r'（[^）]{0,20}感情线[^）]*）',
        r'（[^）]{0,20}推动主题[^）]*）',
        r'\([^)]{0,30}(插入|画面要素|感情线|推动主题)[^)]*\)',
    ]
    if any(re.search(pattern, text) for pattern in meta_like_patterns):
        return True

    if contains_body_drift(text, myth_core):
        return True

    latin_hits = re.findall(r'[A-Za-z]{2,}', text)
    if len(latin_hits) >= 5:
        return True

    trad_chars = set("萬與專業東絲兩嚴個豐臨為麗舉樂鄉書買亂爭於雲亞產畢實寧眾優會傢價億債傷傾後門風體們發戰愛國頭聲靜場這顏顯點說師來個們為後時")
    trad_count = sum(1 for ch in text if ch in trad_chars)
    if trad_count >= max(8, len(text) // 180):
        return True

    # 过长无停顿句通常意味着模型在堆砌空话
    long_sentences = [
        s for s in re.split(r'[。！？\n]', text)
        if len(re.sub(r'\s+', '', s)) >= 180
    ]
    if len(long_sentences) >= 3:
        return True

    # “宏大套话”连续堆叠的特征
    repetitive_phrases = ['与此同时', '总而言之', '综上所述', '这才是', '发展前景', '各个方面', '共同发展']
    repetitive_hits = sum(text.count(p) for p in repetitive_phrases)
    if repetitive_hits >= 12:
        return True

    return False


def has_repeated_story_units(text: str) -> bool:
    """
    检测明显的段落重启/同功能重复。重点拦截同一段落或高度相似段落
    在成稿中反复出现的情况。
    """
    if not text:
        return False
    paragraphs = [
        re.sub(r'\s+', '', p)
        for p in re.split(r'\n+', text)
        if len(re.sub(r'\s+', '', p)) >= 70
    ]
    seen = set()
    for para in paragraphs:
        key = para[:140]
        if key in seen:
            return True
        seen.add(key)
    for i, left in enumerate(paragraphs):
        left_tokens = set(re.findall(r'[\u4e00-\u9fff]{2,4}', left))
        if len(left_tokens) < 12:
            continue
        for right in paragraphs[i + 1:]:
            right_tokens = set(re.findall(r'[\u4e00-\u9fff]{2,4}', right))
            if len(right_tokens) < 12:
                continue
            overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
            if overlap >= 0.78:
                return True
    return False


def violates_myth_consistency(text: str, myth_core: dict = None) -> bool:
    """
    按神话核心约束检查名称和核心道具形态是否混乱。
    规则由 myth_core_constraints*.json 提供，代码只提供通用执行器。
    """
    if not text or not myth_core:
        return False
    if contains_myth_core_violation(text, myth_core):
        return True
    if contains_thread_protagonist_violation(text, myth_core):
        return True
    canonical_terms = myth_core.get("canonical_terms", {})
    if isinstance(canonical_terms, dict):
        for _label, value in canonical_terms.items():
            if isinstance(value, str) and value and value not in text:
                return True
    object_rules = myth_core.get("object_consistency", [])
    if isinstance(object_rules, dict):
        object_rules = [object_rules]
    for rule in object_rules or []:
        if not isinstance(rule, dict):
            continue
        allowed_forms = [form for form in rule.get("allowed_forms", []) if form]
        if allowed_forms and not any(form in text for form in allowed_forms):
            return True
    return False


def validate_story_quality(text: str, prompt: str = "", myth_core: dict = None) -> bool:
    """
    长篇神话改写的最终质量验收：
    - 字数达到 6500~8500 的目标区间附近，硬上限 9000
    - 无明显乱码/元文本污染
    - 句号逗号密度正常，不是单纯堆字
    - 与主题至少有若干关键字重合，降低跑题概率
    """
    if not text:
        return False

    if len(text) < MYTH_TARGET_TOTAL_MIN:
        return False
    if len(text) > MYTH_TARGET_TOTAL_MAX:
        return False

    if has_obvious_garbled_text(text, myth_core):
        return False

    if violates_myth_consistency(text, myth_core or {}):
        return False

    if contains_body_drift(text, myth_core):
        return False

    if has_repeated_story_units(text):
        return False

    if myth_core and not myth_core_requirement_met(text, myth_core, final=True):
        return False

    if myth_core and not myth_core_final_phrases_met(text, myth_core):
        return False

    if myth_core and not myth_core_required_sequence_met(text, myth_core):
        return False

    if myth_core and not thread_protagonist_requirement_met(text, myth_core):
        return False

    if myth_core and not houyi_story_quality_met(text, myth_core):
        return False

    punctuation_count = sum(text.count(p) for p in "，。！？")
    if punctuation_count < max(120, len(text) // 45):
        return False

    if prompt:
        prompt_keywords = [k for k in re.findall(r'[\u4e00-\u9fff]{2,4}', prompt) if len(k) >= 2]
        prompt_keywords = list(dict.fromkeys(prompt_keywords))[:10]
        if prompt_keywords:
            hit_count = sum(1 for k in prompt_keywords if k in text)
            if hit_count < max(2, min(4, len(prompt_keywords) // 2)):
                return False

    # 至少要有比较均匀的分段，否则大概率是大段灌水
    non_empty_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(non_empty_lines) < 18:
        return False

    # 单行过长过多，说明模型在拉长套话
    ultra_long_lines = [line for line in non_empty_lines if len(line) >= 360]
    if ultra_long_lines:
        return False

    return True


def shrink_story_to_target_length(text: str, prompt: str = "", myth_core: dict = None) -> str:
    """
    当正文超过目标上限时，调用模型做保守压缩，保留神话核心事件链和结尾。
    """
    if not text or len(text) <= MYTH_TARGET_TOTAL_SOFT_MAX:
        return text

    myth_core_block = format_myth_core_block(myth_core)
    system_message = {
        "role": "system",
        "content": f"""
你是一名长篇神话改写的精修编辑。你的任务是删减和压缩已有正文，不新增剧情。
必须保留原神话核心事件链、关键因果、最终结局和核心寓意。
目标长度：{MYTH_TARGET_TOTAL_MIN}~{MYTH_TARGET_TOTAL_SOFT_MAX} 字，绝对不要超过 {MYTH_TARGET_TOTAL_MAX} 字。
压缩优先级：删重复环境描写、删重复推演过程、合并相似旁观反应、压缩连续互怼；保留强笑点、核心动作、关键情感收束。
严禁保留或新增任何现代政治宣传腔、政策口号、党政国家叙述、人民群众总结、国际合作等与神话主线无关的内容。
只输出压缩后的故事正文，不要标题、说明、列表或字数统计。
{myth_core_block}
"""
    }
    user_message = {
        "role": "user",
        "content": f"""请将以下《{prompt}》正文压缩到 {MYTH_TARGET_TOTAL_MIN}~{MYTH_TARGET_TOTAL_SOFT_MAX} 字之间，保留完整故事与结尾，不新增任何新情节。若原文出现现代政治宣传腔、政策口号、党政国家叙述、人民群众总结、国际合作等串台内容，必须整段删除：

{text}"""
    }
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.55,
        top_p=0.85,
        repetition_penalty=1.25,
        max_tokens=9000
    )
    cleaned = clean_story_postprocess(clean_markdown(reply or ""), myth_core)
    if MYTH_TARGET_TOTAL_MIN <= len(cleaned) <= MYTH_TARGET_TOTAL_MAX and not contains_body_drift(cleaned, myth_core):
        if not myth_core or myth_core_requirement_met(cleaned, myth_core, final=True):
            return cleaned
    return text


def force_trim_story_to_hard_max(text: str, max_len: int = MYTH_TARGET_TOTAL_MAX) -> str:
    """
    压缩模型失败时的最后兜底：保留开头与结尾，删除中段最长的冗余段落。
    只在超过硬上限时使用，避免再次输出 1w+ 字。
    """
    if not text or len(text) <= max_len:
        return text
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if len(paragraphs) <= 6:
        return text[:max_len].rstrip()

    while len("\n\n".join(paragraphs)) > max_len and len(paragraphs) > 6:
        removable = range(2, max(2, len(paragraphs) - 3))
        candidates = list(removable)
        if not candidates:
            break
        drop_index = max(candidates, key=lambda idx: len(paragraphs[idx]))
        paragraphs.pop(drop_index)

    trimmed = "\n\n".join(paragraphs).strip()
    if len(trimmed) > max_len:
        ending = "\n\n".join(paragraphs[-3:])
        head_limit = max_len - len(ending) - 4
        trimmed = (trimmed[:max(0, head_limit)].rstrip() + "\n\n" + ending).strip()
    return trimmed


def story_revision_is_better(candidate: str, current: str, prompt: str = "", myth_core: dict = None) -> bool:
    """
    判断补救生成是否值得覆盖当前正文。
    生成模型偶尔会在“补救”阶段产出更短或更脏的稿子；这里防止越修越缩水。
    """
    if not candidate:
        return False
    if not current:
        return True

    candidate = clean_story_postprocess(candidate, myth_core)
    current = clean_story_postprocess(current, myth_core)
    candidate_valid = validate_story_quality(candidate, prompt, myth_core)
    current_valid = validate_story_quality(current, prompt, myth_core)

    if candidate_valid and not current_valid:
        return True
    if current_valid and not candidate_valid:
        return False
    if candidate_valid and current_valid:
        target_mid = (MYTH_TARGET_TOTAL_MIN + MYTH_TARGET_TOTAL_SOFT_MAX) // 2
        return abs(len(candidate) - target_mid) < abs(len(current) - target_mid)

    candidate_dirty = has_obvious_garbled_text(candidate, myth_core) or violates_myth_consistency(candidate, myth_core or {})
    current_dirty = has_obvious_garbled_text(current, myth_core) or violates_myth_consistency(current, myth_core or {})
    if current_dirty and not candidate_dirty and len(candidate) >= max(MYTH_TARGET_TOTAL_MIN - 300, int(len(current) * 0.9)):
        return True
    if candidate_dirty and not current_dirty:
        return False

    if len(current) >= MYTH_TARGET_TOTAL_MIN and len(candidate) < MYTH_TARGET_TOTAL_MIN:
        return False
    if len(candidate) >= MYTH_TARGET_TOTAL_MIN and len(current) < MYTH_TARGET_TOTAL_MIN:
        return True

    return len(candidate) >= len(current) + 200


def _extract_keywords(text: str) -> list:
    """
    将节拍卡字段（画面要素/场景目标/情绪推动等）切成若干关键短语，用于简单命中校验
    """
    if not text:
        return []
    parts = re.split(r'[，,。．；;、/｜|\s]', text)
    keywords = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2:
            keywords.append(p)
    return keywords


def validate_single_beat_segment(seg: str, beat: dict, min_len: int = 60, myth_core: dict = None) -> bool:
    """
    针对【单张节拍卡】的轻量级校验：
    - 文本非空，且长度不能太短
    - 命中当前节拍卡中至少一类关键词（画面要素 / 场景目标 / 情绪推动）
    - 不包含"禁止项"里的关键词
    """
    if not seg:
        return False
    seg = seg.strip()
    if len(seg) < min_len:
        return False
    if has_obvious_garbled_text(seg, myth_core):
        return False
    if contains_body_drift(seg, myth_core):
        return False

    visuals = _extract_keywords(beat.get('画面要素', '') or '')
    goals = _extract_keywords(beat.get('场景目标', '') or '')
    emotions = _extract_keywords(beat.get('情绪推动', '') or '')
    info_keywords = _extract_keywords(beat.get('信息增量', '') or '')

    has_any_keywords = bool(visuals or goals or emotions)
    if has_any_keywords:
        hit = any(k in seg for k in visuals) or any(k in seg for k in goals) or any(k in seg for k in emotions)
        if not hit:
            return False

    if visuals and not any(k in seg for k in visuals):
        return False

    if goals or info_keywords:
        if not any(k in seg for k in goals) and not any(k in seg for k in info_keywords):
            return False

    bans_raw = beat.get('禁止项', '') or ''
    if bans_raw:
        raw_bans = re.split(r'[，,。．；;、/]', bans_raw)
        ban_keywords = []
        for b in raw_bans:
            b = b.strip()
            b = re.sub(r'^(不能|不准|不要|禁止|别|不许|不可|不让)\s*', '', b)
            if len(b) >= 2:
                ban_keywords.append(b)
        if any(b in seg for b in ban_keywords):
            return False

    return True


def generate_segment_for_beat(
    act_name: str,
    beat_index: int,
    total_beats: int,
    beat: dict,
    overall_outline: str,
    act_outline: str,
    prev_text: str,
    prompt: str,
    system_content: str,
    target_min_len: int,
    target_max_len: int,
    act_id: str = "",
    punchlines_to_embed: str = "",
    punchline_examples_text: str = "",
    touching_storyline: str = None,
    touching_ending_examples: str = None,  # 可选：已加载的感动结局示例，避免重复加载
    myth_core: dict = None
):
    """
    通用：按【单张节拍卡】生成对应的一小节正文，并做轻量校验，返回通过校验的文本（或最后一次结果）。
    punchlines_to_embed：方案一第二阶段传入的、本小节可融入的笑点方案（先由专门接口生成）。
    punchline_examples_text：方案二精选的「让人笑出来」对白示例，用于模仿节奏与梗的密度。
    """
    system_message = {
        "role": "system",
        "content": system_content
    }

    # 简要前文摘要：只保留末尾一小段，帮助承接，不让模型复述全部内容
    prev_summary = ""
    if prev_text:
        tail = prev_text.strip()[-400:]
        prev_summary = tail

    punchline_block = ("【当前神话适配的笑点对白示例（学习节奏，不要照抄）】\n" + punchline_examples_text + "\n") if punchline_examples_text else ""
    punchline_embed_block = ("【本小节可优先吸收的笑点方案】\n" + punchlines_to_embed + "\n要求：只在贴合当前情境时自然融入；可改写人物称呼、道具和句子，不要生硬照搬。若方案里有情节反差，优先把它写成正文动作，不要强行改成副角吐槽。\n") if punchlines_to_embed else ""
    myth_specific_humor_block = get_myth_specific_humor_guidance(myth_core)
    
    # 感动故事线索：根据当前幕和节拍卡位置，融入对应的感动线索
    touching_storyline_block = ""
    if touching_storyline:
        if act_id == "act1":
            # 第一幕：铺垫阶段，自然融入感动线索的铺垫部分
            touching_storyline_block = f"\n【感动故事线索（第一幕铺垫阶段，请在本小节中自然融入以下情感元素，不要生硬添加）】\n{touching_storyline}\n"
        elif act_id == "act2":
            # 第二幕：发展阶段，感动线索逐渐显现
            touching_storyline_block = f"\n【感动故事线索（第二幕发展阶段，请在本小节中自然融入以下情感元素，让感动线索逐渐显现）】\n{touching_storyline}\n"
        elif act_id == "act3":
            # 第三幕：高潮与收束阶段
            if beat_index >= total_beats - 1:  # 最后1-2张节拍卡，重点突出感动
                # 如果已经传入了感动结局示例，直接使用；否则才加载（避免重复加载）
                if touching_ending_examples is None:
                    touching_ending_examples = get_touching_ending_examples()
                touching_examples_block = f"\n【感动结局参考样本（请学习其情感表达与节奏）】\n{touching_ending_examples}\n" if touching_ending_examples else ""
                touching_storyline_block = f"\n【情绪收束线索（本小节是结局部分，优先回收幽默与人物弧光；若适合再轻微升华，不要硬煽情）】\n{touching_storyline}\n{touching_examples_block}"
            else:
                # 第三幕的其他节拍卡，继续发展感动线索
                touching_storyline_block = f"\n【感动故事线索（第三幕高潮与收束阶段，请在本小节中继续发展感动线索，为结局做准备）】\n{touching_storyline}\n"

    special_constraints = ""
    if act_id == "act2":
        myth_title = (myth_core or {}).get("title", "")
        if myth_title == "北冥鲲鹏":
            special_constraints = """
【第二幕《北冥鲲鹏》核心转化约束】
- 本幕必须把“鲲化为鹏”和“翼若垂天之云”写成清楚的主线进展，不得只写变大、长翅膀或受伤。
- 变化描写只允许走宏大清逸方向：鳞化羽、背若泰山、翼若云垂、海水翻涌、风托其身；禁止写腐蚀液、陶罐酒樽、胸口异物、器官畸变、掉渣烂肉。
- 若写旁观者或阿浪，必须短促；本幕后半要让其从嘲笑转为震惊，不能每段都插话。
- 六月大风必须开始成为核心转折的预兆，不得写成普通东风、飓风或天气事故。
"""
        elif myth_title in {"嫦娥奔月", "牛郎织女", "梁山伯与祝英台", "孟姜女哭长城"}:
            special_constraints = """
【第二幕主线冲突约束】
- 本幕允许人物压力、夺取、逼迫、追赶、误会或社会规矩形成冲突；但冲突必须直接服务本神话核心因果。
- 若本神话涉及核心道具，必须保持道具状态单一清楚：藏在哪里、谁要夺取、谁如何处理、处理后产生什么不可逆后果。
- 辅助吐槽角色不得主导冲突，不得把核心选择写成单纯闹剧、误触事故或聊天拌嘴。
"""
        elif myth_title == "后羿射日":
            special_constraints = """
【第二幕《后羿射日》逐箭顺序硬约束】
- 本幕核心不是泛泛“打败太阳”，而是后羿亲自按顺序射落九个太阳。
- 当前节拍卡若写某一箭或某几箭，必须明确写出：后羿站定/搭箭/拉弓/放箭、对应第几日中箭坠落、天地或百姓产生什么变化。
- 严禁跳号、倒叙重启或重复射同一个太阳；前文已射落的太阳不能再次出现。
- 严禁把太阳写成长期躲藏、玩捉迷藏、引出新支线；太阳可以有热浪反扑，但不能抢成反派角色。
- 严禁新增护身符、匕首、酒葫芦水源奇迹、备胎、缰绳、烽燧塔、蚂蚁搬叶等无关道具或插曲。
- 阿满只能护青竹简、记录箭序、短促吐槽或狼狈见证；不得让阿满摔倒导致后羿命中，也不得让阿满影响射日结果。
"""
        else:
            special_constraints = """
【第二幕创世/英雄叙事约束】
- 所有阻力必须来自世界结构、物理阻力、秩序规则或原神话固有危机，不能随意新造无关敌人。
- 每个动作都要回答：这一步有没有让核心目标（如开天/补天/射日/渡海/填海）往前推进？
【第二幕过程必须步骤化】
- 若本神话为射日类：涉及射落太阳的节拍须写出具体动作与结果（如第几箭、射落第几颗、太阳如何坠下、旁人/环境反应），不得用「他一口气射落多个」一笔带过。
- 若为开天/补天类：须写出本小节对应的具体阶段（如劈开某一处、撑住某一刻、补某一块），不能模糊成「持续进行」。
"""
    elif act_id == "act3":
        if (myth_core or {}).get("title", "") == "北冥鲲鹏":
            special_constraints = """
【第三幕《北冥鲲鹏》远举收束约束】
- 第三幕必须明确写出：鲲已不再是鲲，众生看见的是大鹏；鹏翼若垂天之云；它乘六月大风，背负青天，向南冥天池飞去。
- “六月大风”必须是托举大鹏的天地之力，不是阻碍、事故或单纯灾害。
- 结尾的主题不是打败谁，而是离开狭小尺度；下方嘲笑声要变小，阿浪如出现应沉默或低声认可。
- 场景只沿“北冥海面/高空风口/南冥天池远方”推进，不要新增东海、码头、商船、昆仑雪峰等地点。
- 结尾幽默最多一句嘴硬型余味，不得再密集吐槽。
"""
        elif (myth_core or {}).get("title", "") == "后羿射日":
            special_constraints = """
【第三幕《后羿射日》留一日收束硬约束】
- 第三幕只能写射落九日之后的选择与余波：后羿主动留下最后一个太阳，天地恢复正常，百姓从灾难中缓过来。
- 必须明确“留下最后一个太阳”是后羿的克制和判断，不是漏靶、射不中、忘了射、少带箭或太阳逃走。
- 必须让阿满在结尾附近用青竹简记录“射九留一”或“射落九日，留下一日”，但不得让阿满发表长篇大道理。
- 严禁再写第一箭、第二箭或补射过程；严禁让最后一个太阳变成新敌人、新支线或继续失控。
- 结尾幽默最多一处，优先用阿满摸青竹简温度、写错又改正等记录梗收束。
"""
        else:
            special_constraints = """
【第三幕收束约束】
- 必须围绕"选择与代价-世界后果-收束画面"这一结局三件套推进，不要开启新支线。
- 【结局情绪要求（重点）】：第三幕优先保持幽默风趣和娱乐性，结尾可以是轻松余味、旁观者嘴硬认可、道具/口头禅回收，只有原神话自然适合时才做感动升华。
- 不要强写牺牲、跪地、泪眼、奉献精神、时代曙光等作文式煽情；伏羲画卦、愚公移山等可用“众人终于看懂但仍嘴硬”的轻松方式收束。
- 结局部分（最后1-2张节拍卡）应完成经典结局与主题闭环，同时保留1处克制但好笑的回收点。
"""

    user_content = f"""
你正在创作《{prompt}》的{act_name}，现在要写本幕第 {beat_index}/{total_beats} 张节拍卡对应的一小节正文。

【总体大纲（仅供参考，用于把握全局走向）】
{overall_outline}

【本幕大纲（必须对齐）】
{act_outline}

【已完成前文的简要摘取】（如果为空说明这是本幕第一小节，仅用于承接，不要复述）
{prev_summary if prev_summary else "（无前文，这是本幕的第一小节）"}

【当前节拍卡写作任务（必须完成）】
- 场景目标：{beat.get('场景目标', '')}
- 画面要素：{beat.get('画面要素', '')}
- 情绪推动：{beat.get('情绪推动', '')}
- 信息增量：{beat.get('信息增量', '')}
- 禁止项：{beat.get('禁止项', '')}
- 情感伏笔：{beat.get('情感伏笔', '')}
- 关系推进：{beat.get('关系推进', '')}
- 幽默机制：{beat.get('幽默机制', '')}
{punchline_block}
{punchline_embed_block}
{myth_specific_humor_block}
{touching_storyline_block}
{special_constraints}

【写作硬性要求】
1. 只写本节对应的一小段剧情，不要提前写后续节拍的情节，也不要回头复述已经写过的内容。
   - 如果前文已经写过某个道具被拿出、封存、启程、抵达、交手、吞服、离开等动作，本小节不得换个说法再写一遍；必须推进一个新的压力、新动作或新后果。
   - 核心道具和人物称呼必须沿用前文与神话硬约束中的同一名称，不得把同一道具改写成另一种形态。
2. 正文中必须自然出现上方"画面要素"中至少 1-2 个具体画面或动作（可以改写，不要生搬硬套短语）。
3. 严格避免"禁止项"里的内容和表达，一旦要写到类似内容，必须换一种不违背规则的方式。
3.1 只允许写当前节拍卡、本幕大纲、总体大纲里已经出现或可以直接推出的人物、地点、道具和事件。
3.2 如果当前节拍卡没有写到某个新角色、新道具、新地点、新设定，就不要自行发明；尤其禁止突然出现预言者、会预知未来的动物、神秘帮手、临时外援、演播/直播类场景、信心值/任务值、系统/程序/工程类表达。
3.3 新增内容只能是贴着主线的小幅补足，例如多一个动作细节、多一句互怼、多一点环境阻力、多一个旁观反应；不能把剧情拐到新的支线或新设定上。
4. 幽默强度与通道要求：
   - 【第三幕后半段幽默退场机制】：如果 act_id == "act3" 且 beat_index >= total_beats - 1（最后1-2张节拍卡）：
     * 禁止"至少3个笑点"的要求
     * 禁止固定拆台副角继续高频接梗
     * 最多只允许1个轻微缓冲句
     * 且这个轻句必须是"嘴硬型温柔"，不能是纯搞笑
     * 例如允许："你别磨蹭，我还听得见。"（嘴硬但温柔）
     * 不允许："师父你现在像条晾干的鱼。"（纯搞笑，会打断情绪沉浸）
   - 【其他节拍卡】：本改写允许幽默，但幽默必须服务当前神话主线：
     * 强度：本小节笑点以【2级：明显好笑】为主（读者能明确感到「这里在搞笑」），可穿插【3级：小爆点】（一抛一接、误会升级、拆台接梗）。避免只有 1 级轻描淡写、读者无感的「软笑点」。
     * 若当前节拍卡的"场景目标"属于铺垫、日常、情绪累积、尝试行动、寻找突破口、行动间隙等【非关键情节】：本小节可出现 1-2 个笑点，优先使用“情节/画面反差 + 一句短对白补刀”的组合。类型上可用【夸张、反差、错误逻辑、嘴硬、自嘲、拆台、旁观误解、道具翻车、严肃记录反差、命名梗】中的至少 1 种。
     * 若当前节拍卡的"场景目标"属于【关键转折/重大抉择/牺牲代价/终极使命完成/收束画面】：可只保留 0-1 个极克制的轻回应，不削弱庄重感。
     * 幽默类型必须多样：夸张（夸张形容处境/能力）、反差（严肃场合说人话、大目标配小吐槽）、错误逻辑/歪楼（故意或无意把话题带偏、离谱但自洽的接话）、嘴硬、自嘲、拆台互怼、旁观误解、道具翻车、严肃记录反差、命名梗。同一小节内避免只重复一种；不要把所有笑点都改写成固定副角对白。
     * 单次笑点 1-2 句话，允许【连续 2 句「一抛一接」】对白；严禁大段独白无接话。严禁现代职场/网络流行语、低俗/侮辱性桥段；**严禁骂人、辱骂、人身攻击等低俗幽默方式**，互怼仅限「逗、皮、嘴硬」，不得脏话或贬损人格。
     * **辅助吐槽角色与互怼**：若本故事已设定辅助吐槽角色，本小节只有在不挤压核心人物和主线冲突时才让其接话；关键冲突、重大抉择、牺牲、分离和收束节拍中，该角色应主动退场或沉默见证。连续两小节都由同一个辅助角色承担笑点时，本小节必须改用旁观误解、动作反差、道具翻车、记录反差或命名梗。
5. 本小节长度控制在约 {target_min_len}~{target_max_len} 字之间，必须分成 2-4 个短自然段；每段约 80-180 字，最长不要超过 240 字。场景动作、对白反应、情绪余波之间要自然换段，不要把所有内容连成一整段。
6. 全文使用简体中文，不要出现列表、数字编号、说明文字、"节拍卡"字样或任何元提示。
7. 语气、世界观、人物设定要与前文保持连续，像在同一个长篇故事里自然接着往下写。
8. 只输出这一小节的【纯正文】，不要添加标题、小结或任何额外说明。
"""

    def _build_user_message(extra_instruction: str = ""):
        extra_block = f"\n【纠偏补充】\n{extra_instruction}\n" if extra_instruction else ""
        return {
            "role": "user",
            "content": user_content + extra_block
        }

    def _call_and_postprocess(temp: float, extra_instruction: str = ""):
        token_budget = max(520, min(850, int(target_max_len * 1.35)))
        reply_local = call_qianwen_api(
            [system_message, _build_user_message(extra_instruction)],
            temperature=temp,
            top_p=0.9,
            repetition_penalty=1.35,
            max_tokens=token_budget
        )
        if has_hard_meta_residue(reply_local):
            return ""
        cleaned = clean_markdown(reply_local)
        return fix_punctuation_and_paragraphs(cleaned)

    best_result = None
    for temp in (0.9, 0.8):
        seg = _call_and_postprocess(temp)
        if seg and (best_result is None or len(seg) > len(best_result)):
            best_result = seg
        if validate_single_beat_segment(seg, beat, min_len=max(40, target_min_len // 2), myth_core=myth_core):
            return seg.strip()

    repair_instruction = (
        "上一个版本没有严格贴住节拍卡。现在必须重写这一小节，只保留当前节拍卡和本幕大纲中已经出现的内容。"
        "不要新增任何未被节拍卡明确允许的新角色、新地点、新道具、新支线。"
        "禁止出现预言动物、神秘外援、演播厅、直播间、信心值、任务值、系统、程序、工程等跑偏设定。"
        "这一小节必须直接完成当前“场景目标”，并自然落下“信息增量”，不能写成另一段新剧情。"
    )
    for temp in (0.75, 0.65):
        seg = _call_and_postprocess(temp, repair_instruction)
        if seg and (best_result is None or len(seg) > len(best_result)):
            best_result = seg
        if validate_single_beat_segment(seg, beat, min_len=max(40, target_min_len // 2), myth_core=myth_core):
            return seg.strip()

    # 多次尝试仍未通过节拍校验时，返回最后一次结果（尽量不阻塞整体流程）
    return (best_result or "").strip()

def _extract_beat_segments_by_marker(script: str, expected_count: int):
    """
    根据【B1】【B2】…标记切分每一幕的内容段落，返回按节拍顺序排列的文本列表。
    如果标记缺失、乱序或数量不足，则返回 None。
    """
    if not script or expected_count <= 0:
        return None

    pattern = re.compile(r'【B(\d+)】')
    matches = list(pattern.finditer(script))
    if not matches:
        return None

    # 收集每个标记对应的文本片段
    segments_map = {}
    for idx, m in enumerate(matches):
        beat_index = int(m.group(1))
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(script)
        seg = script[start:end].strip()
        if not seg:
            continue
        # 只保留第一次出现的该编号片段，避免重复覆盖
        if 1 <= beat_index <= expected_count and beat_index not in segments_map:
            segments_map[beat_index] = seg

    # 必须保证从1到expected_count都有对应片段
    if any(i not in segments_map for i in range(1, expected_count + 1)):
        return None

    return [segments_map[i] for i in range(1, expected_count + 1)]


def validate_act_beats(script: str, beats: list) -> bool:
    """
    通用节拍卡对齐校验（适用于三幕）：
    - 检查是否存在按顺序的【B1】【B2】…标记，且数量与节拍卡数量一致
    - 每个节拍对应片段需至少命中该卡"画面要素"中的1-2个关键词
    - 如片段中出现该卡"禁止项"中的关键词，则视为失败
    """
    if not beats:
        return True

    expected_count = len(beats)
    segments = _extract_beat_segments_by_marker(script, expected_count)
    if not segments:
        return False

    for idx, beat in enumerate(beats):
        seg = segments[idx]
        if not isinstance(beat, dict):
            # 旧格式：只要片段非空即可
            if not seg.strip():
                return False
            continue

        # A. 画面要素命中检查：从"画面要素"里切出若干关键短语，只要命中至少一个即可
        visuals = beat.get('画面要素', '') or ''
        visual_keywords = []
        if visuals:
            # 按常见标点/分隔符切分
            raw_parts = re.split(r'[，,。．；;、/｜|]', visuals)
            for p in raw_parts:
                p = p.strip()
                # 过滤掉过短或纯符号的片段
                if len(p) >= 2:
                    visual_keywords.append(p)

        if visual_keywords:
            if not any(k in seg for k in visual_keywords):
                return False

        # B. 禁止项违规则判失败：提取禁止项中的关键短语，若出现在片段中则失败
        bans = beat.get('禁止项', '') or ''
        if bans:
            raw_bans = re.split(r'[，,。．；;、/]', bans)
            ban_keywords = []
            for b in raw_bans:
                b = b.strip()
                # 去掉常见否定前缀，保留核心动作/名词
                b = re.sub(r'^(不能|不准|不要|禁止|别|不许|不可|不让)\s*', '', b)
                if len(b) >= 2:
                    ban_keywords.append(b)

            if any(b in seg for b in ban_keywords):
                return False

    return True


def generate_act3_ending_beat(
    act_name: str,
    beat_index: int,
    total_beats: int,
    beat: dict,
    overall_outline: str,
    act_outline: str,
    prev_text: str,
    prompt: str,
    system_content: str,
    target_min_len: int,
    target_max_len: int,
    touching_ending_examples: str = None,
    emotional_character: str = None,  # 情感落点角色名称
    myth_core: dict = None
):
    """
    专门用于生成第三幕结尾beat的函数
    额外要求：
    - 必须回收前文至少1个具体伏笔
    - 必须出现1个克制但明确的身体动作
    - 必须出现1个非解释性的环境收束镜头
    - 不允许再新增高密度互怼
    """
    system_message = {
        "role": "system",
        "content": system_content
    }

    # 简要前文摘要：只保留末尾一小段，帮助承接
    prev_summary = ""
    if prev_text:
        tail = prev_text.strip()[-400:]
        prev_summary = tail

    # 感动结局示例
    touching_examples_block = f"\n【感动结局参考样本（请学习其情感表达与节奏）】\n{touching_ending_examples}\n" if touching_ending_examples else ""
    
    # 情感落点角色提示
    emotional_character_block = f"\n【情感落点角色】\n本故事的情感落点角色是：{emotional_character}。第三幕结尾必须围绕该角色与核心主角的关系完成情感回应，群众/环境只能辅助，辅助吐槽角色不能替代该角色。\n" if emotional_character else ""

    user_content = f"""
你正在创作《{prompt}》的{act_name}，现在要写本幕第 {beat_index}/{total_beats} 张节拍卡对应的一小节正文。这是【结尾beat】，必须完成经典结局与情绪收束；优先保留幽默风趣的余味，若适合再自然升华，不要硬煽情。

【总体大纲（仅供参考，用于把握全局走向）】
{overall_outline}

【本幕大纲（必须对齐）】
{act_outline}

【已完成前文的简要摘取】（用于承接和回收伏笔）
{prev_summary if prev_summary else "（无前文）"}

【当前节拍卡写作任务（必须完成）】
- 场景目标：{beat.get('场景目标', '')}
- 画面要素：{beat.get('画面要素', '')}
- 情绪推动：{beat.get('情绪推动', '')}
- 信息增量：{beat.get('信息增量', '')}
- 禁止项：{beat.get('禁止项', '')}
- 情感伏笔：{beat.get('情感伏笔', '')}
- 关系推进：{beat.get('关系推进', '')}
{touching_examples_block}
{emotional_character_block}

【结尾beat硬性要求（必须全部满足）】
1. 必须回收前文至少1个具体伏笔、误会、道具翻车或口头禅。
2. 必须完成当前神话的经典结局，不得用泛泛总结替代。
3. 必须出现1个非解释性的环境收束镜头（如风、光、田野、土地、天空、水面、火光等）。
4. 允许保留1个轻松好笑的回收点，可以是嘴硬认可、旁观误会解除或小道具反差；不要再开新段子。
5. 若神话本身不适合悲情结尾，不要强写跪地、泪眼、牺牲、奉献精神、时代曙光。

【写作硬性要求】
1. 只写本节对应的一小段剧情，不要提前写后续节拍的情节，也不要回头复述已经写过的内容。
   - 如果前文已经写过某个道具被拿出、封存、启程、抵达、交手、吞服、离开等动作，本小节不得换个说法再写一遍；必须推进一个新的压力、新动作或新后果。
   - 核心道具和人物称呼必须沿用前文与神话硬约束中的同一名称，不得把同一道具改写成另一种形态。
2. 正文中必须自然出现上方"画面要素"中至少 1-2 个具体画面或动作。
3. 严格避免"禁止项"里的内容和表达。
4. 本小节长度控制在约 {target_min_len}~{target_max_len} 字之间，必须分成 2-4 个短自然段；每段约 80-180 字，最长不要超过 240 字。动作、对白、环境收束之间要自然换段，不要把所有内容连成一整段。
5. 全文使用简体中文，不要出现列表、数字编号、说明文字、"节拍卡"字样或任何元提示。
6. 语气、世界观、人物设定要与前文保持连续，像在同一个长篇故事里自然接着往下写。
7. 只输出这一小节的【纯正文】，不要添加标题、小结或任何额外说明。
"""

    user_message = {
        "role": "user",
        "content": user_content
    }

    def _call_and_postprocess(temp: float):
        token_budget = max(500, min(800, int(target_max_len * 1.3)))
        reply_local = call_qianwen_api(
            [system_message, user_message],
            temperature=temp,
            top_p=0.9,
            repetition_penalty=1.35,
            max_tokens=token_budget
        )
        if has_hard_meta_residue(reply_local):
            return ""
        cleaned = clean_markdown(reply_local)
        return fix_punctuation_and_paragraphs(cleaned)

    best_result = None
    for temp in (0.9, 0.8):
        seg = _call_and_postprocess(temp)
        if seg and (best_result is None or len(seg) > len(best_result)):
            best_result = seg
        if validate_single_beat_segment(seg, beat, min_len=max(40, target_min_len // 2), myth_core=myth_core):
            return seg.strip()

    return (best_result or "").strip()


def validate_touching_ending(act3_text: str, memory_hooks: list = None) -> bool:
    """
    验证第三幕结尾是否达到感动闭环
    检查结尾是否命中以下4项中的至少3项：
    1. 出现代价词：疲惫、血、裂、撑不住、消散、闭眼、放下、最后、终于
    2. 出现回应词：抱住、扶住、轻声、看着、泪、沉默、点头、叫了一声
    3. 出现世界变化词：风、光、田野、万物、土地、天空、回暖、复苏
    4. 出现回收词：重复前文某个意象（需要memory_hooks来检查）
    """
    if not act3_text:
        return False
    
    # 只检查最后500字（结尾部分）
    ending_text = act3_text[-500:] if len(act3_text) > 500 else act3_text
    
    # 代价词
    cost_words = ['疲惫', '血', '裂', '撑不住', '消散', '闭眼', '放下', '最后', '终于']
    has_cost = any(word in ending_text for word in cost_words)
    
    # 回应词
    response_words = ['抱住', '扶住', '轻声', '看着', '泪', '沉默', '点头', '叫了一声', '握住', '轻拍']
    has_response = any(word in ending_text for word in response_words)
    
    # 世界变化词
    world_change_words = ['风', '光', '田野', '万物', '土地', '天空', '回暖', '复苏', '生机', '恢复']
    has_world_change = any(word in ending_text for word in world_change_words)
    
    # 回收词（如果有memory_hooks，检查是否回收了前文意象）
    has_recovery = False
    if memory_hooks:
        # 简单检查：如果结尾出现了memory_hooks中的关键词，认为有回收
        for hook in memory_hooks:
            if hook and hook in ending_text:
                has_recovery = True
                break
    else:
        # 如果没有memory_hooks，检查常见的回收意象词
        recovery_words = ['干粮', '水壶', '弓', '手', '那句话', '那句话', '那句话']
        has_recovery = any(word in ending_text for word in recovery_words)
    
    # 至少命中3项
    count = sum([has_cost, has_response, has_world_change, has_recovery])
    return count >= 3


def validate_script(script):
    """
    验证长篇神话改写整体质量
    """
    return validate_story_quality(script)


def generate_myth_rewrite(prompt):
    """
    针对中国神话故事的改写生成函数，生成适合10分钟视频创作的脚本风格内容。
    风格介于剧本和小说之间，包含影视动作描写，保持可读性。
    采用分幕生成方式：先生成总体大纲，然后分配到三幕，再逐幕生成。
    """
    # Step 1: 生成总体大纲（使用RAG）
    print("正在生成总体大纲...")
    myth_core = find_myth_core(prompt)
    if myth_core:
        print(f"已加载神话核心主旨约束：{myth_core.get('title', '')}")
        thread_constraint = myth_core.get("_thread_protagonist", {})
        if thread_constraint:
            protagonist = thread_constraint.get("_protagonist", {})
            print(
                "正在参考串线主人公约束："
                f"{protagonist.get('name', '阿满')} / {thread_constraint.get('role', '')}"
            )
            if protagonist.get("series_purpose"):
                print(
                    "正在参考十八篇体系串联目标："
                    f"{protagonist.get('series_purpose')}"
                )
            callback_options = thread_constraint.get("callback_options", [])
            if callback_options:
                print(
                    "本篇可用跨篇连接建议："
                    + "；".join(callback_options[:2])
                )
        else:
            print("警告：当前神话未匹配到串线主人公约束。")
    else:
        print("警告：未匹配到本篇神话核心主旨约束，将仅使用通用神话骨架规则。")
    rag_content = searchresult_content(prompt)
    overall_outline = ""
    for outline_try in range(3):
        overall_outline = generate_outline(prompt, rag_content, myth_core)
        if (
            overall_outline
            and len(overall_outline) >= 250
            and not has_obvious_garbled_text(overall_outline, myth_core)
            and not contains_plan_drift(overall_outline, myth_core)
            and myth_core_requirement_met(overall_outline, myth_core, final=False)
        ):
            break
        print(f"警告：总体大纲质量不足，正在重试第 {outline_try + 2} 次...")
    print(f"总体大纲生成完成：\n{overall_outline}\n")
    
    # Step 2: 将总体大纲分配到三幕
    print("正在将总体大纲分配到三幕...")
    acts_outline = split_outline_to_acts(overall_outline, prompt, rag_content, myth_core)
    if not outline_plan_is_usable(acts_outline, myth_core):
        print("警告：首次分幕/节拍卡规划不足，正在使用更强提示重试...")
        retry_prompt = (
            prompt
            + "。请严格生成足量且高质量的节拍卡：第一幕5到6张，第二幕8到9张，第三幕5到6张。"
            + "禁止新增预言动物、神秘外援、演播厅、直播间、信心值、任务值、系统、程序、工程等跑偏设定。"
            + "节拍卡只能贴着原神话主线和已有大纲扩写。"
            + "必须严格遵守神话核心主旨约束，不得使用旧稿或相似样本里的错误主线。"
        )
        for _ in range(2):
            refreshed_outline = generate_outline(retry_prompt, rag_content, myth_core)
            if (
                refreshed_outline
                and len(refreshed_outline) > len(overall_outline) // 2
                and not contains_plan_drift(refreshed_outline, myth_core)
                and myth_core_requirement_met(refreshed_outline, myth_core, final=False)
            ):
                overall_outline = refreshed_outline
            acts_outline = split_outline_to_acts(overall_outline, retry_prompt, rag_content, myth_core)
            if outline_plan_is_usable(acts_outline, myth_core):
                break
        if not outline_plan_is_usable(acts_outline, myth_core) and myth_core:
            print("警告：模型分幕/节拍卡仍不可用，已按神话核心事件链生成兜底规划。")
            acts_outline = build_core_fallback_plan(prompt, myth_core)
            overall_outline = "\n".join([
                acts_outline.get("act1", ""),
                acts_outline.get("act2", ""),
                acts_outline.get("act3", ""),
            ]).strip()
    print(f"第一幕大纲：\n{acts_outline['act1']}\n")
    print(f"第二幕大纲：\n{acts_outline['act2']}\n")
    print(f"第三幕大纲：\n{acts_outline['act3']}\n")
    
    # 输出beats内容作为日志检查
    print("=== 节拍卡（Beats）日志 ===")
    if acts_outline.get('act1_beats'):
        print(f"第一幕节拍卡（{len(acts_outline['act1_beats'])}张）：")
        for i, beat in enumerate(acts_outline['act1_beats'], 1):
            if isinstance(beat, dict):
                print(f"  节拍卡{i}：")
                print(f"    场景目标：{beat.get('场景目标', '')}")
                print(f"    画面要素：{beat.get('画面要素', '')}")
                print(f"    情绪推动：{beat.get('情绪推动', '')}")
                print(f"    信息增量：{beat.get('信息增量', '')}")
                print(f"    禁止项：{beat.get('禁止项', '')}")
                print(f"    幽默机制：{beat.get('幽默机制', '')}")
            else:
                print(f"  节拍卡{i}：{beat}")
    if acts_outline.get('act2_beats'):
        print(f"第二幕节拍卡（{len(acts_outline['act2_beats'])}张）：")
        for i, beat in enumerate(acts_outline['act2_beats'], 1):
            if isinstance(beat, dict):
                print(f"  节拍卡{i}：")
                print(f"    场景目标：{beat.get('场景目标', '')}")
                print(f"    画面要素：{beat.get('画面要素', '')}")
                print(f"    情绪推动：{beat.get('情绪推动', '')}")
                print(f"    信息增量：{beat.get('信息增量', '')}")
                print(f"    禁止项：{beat.get('禁止项', '')}")
                print(f"    幽默机制：{beat.get('幽默机制', '')}")
            else:
                print(f"  节拍卡{i}：{beat}")
    if acts_outline.get('act3_beats'):
        print(f"第三幕节拍卡（{len(acts_outline['act3_beats'])}张）：")
        for i, beat in enumerate(acts_outline['act3_beats'], 1):
            if isinstance(beat, dict):
                print(f"  节拍卡{i}：")
                print(f"    场景目标：{beat.get('场景目标', '')}")
                print(f"    画面要素：{beat.get('画面要素', '')}")
                print(f"    情绪推动：{beat.get('情绪推动', '')}")
                print(f"    信息增量：{beat.get('信息增量', '')}")
                print(f"    禁止项：{beat.get('禁止项', '')}")
                print(f"    幽默机制：{beat.get('幽默机制', '')}")
            else:
                print(f"  节拍卡{i}：{beat}")
    print("=== 节拍卡日志结束 ===\n")
    
    # Step 3: 生成感动故事线索（基于总体大纲和三幕大纲）
    print("正在生成感动故事线索...")
    touching_storyline = generate_touching_storyline(
        overall_outline,
        acts_outline['act1'],
        acts_outline['act2'],
        acts_outline['act3'],
        prompt,
        rag_content,
        myth_core=myth_core
    )
    print(f"感动故事线索生成完成：")
    print(f"  第一幕感动线索：{touching_storyline['act1_touching']}")
    print(f"  第二幕感动线索：{touching_storyline['act2_touching']}")
    print(f"  第三幕感动线索：{touching_storyline['act3_touching']}\n")
    
    # Step 4: 生成第一幕（使用RAG和第一幕大纲，融入第一幕感动线索）
    print("正在生成第一幕...")
    act1 = generate_act1(
        acts_outline['act1'],
        overall_outline,
        rag_content,
        prompt,
        acts_outline.get('act1_beats'),
        touching_storyline=touching_storyline['act1_touching'],
        myth_core=myth_core
    )
    print(f"第一幕生成完成（{len(act1)}字）\n")
    
    # Step 5: 生成第二幕（使用第二幕大纲和第一幕作为上下文，融入第二幕感动线索）
    print("正在生成第二幕...")
    act2 = generate_act2(
        acts_outline['act2'],
        overall_outline,
        act1,
        prompt,
        acts_outline.get('act2_beats'),
        touching_storyline=touching_storyline['act2_touching'],
        myth_core=myth_core
    )
    print(f"第二幕生成完成（{len(act2)}字）\n")
    
    # Step 6: 提取情感落点角色（固定拆台副角）
    emotional_character = None
    core_emotional_roles = {
        "嫦娥奔月": "后羿",
        "牛郎织女": "牛郎与织女",
        "梁山伯与祝英台": "梁山伯与祝英台",
        "孟姜女哭长城": "孟姜女",
    }
    if myth_core:
        emotional_character = core_emotional_roles.get(myth_core.get("title"))

    # 没有明确核心情感角色时，再尝试从节拍卡或大纲中提取必要辅助角色名称
    if not emotional_character:
        for act_beats in [acts_outline.get('act1_beats', []), acts_outline.get('act2_beats', []), acts_outline.get('act3_beats', [])]:
            for beat in act_beats:
                if isinstance(beat, dict):
                    relationship = beat.get('关系推进', '')
                    # 简单提取：寻找常见的副角名称模式
                    import re
                    match = re.search(r'(铁牛|小徒弟|阿狗|随从|徒弟|副角)', relationship)
                    if match:
                        emotional_character = match.group(1)
                        break
            if emotional_character:
                break
    
    # Step 7: 生成第三幕（使用第三幕大纲和第二幕作为上下文，融入第三幕感动线索）
    print("正在生成第三幕...")
    act3 = generate_act3(
        acts_outline['act3'],
        overall_outline,
        act2,
        prompt,
        acts_outline.get('act3_beats'),
        touching_storyline=touching_storyline['act3_touching'],
        emotional_character=emotional_character,
        myth_core=myth_core
    )
    print(f"第三幕生成完成（{len(act3)}字）\n")
    
    # Step 8: 拼接三幕
    final_script = act1 + "\n\n" + act2 + "\n\n" + act3
    final_script = clean_story_postprocess(final_script, myth_core)
    
    # Step 9: 验证整体质量，若总长不足或结尾质量不好，则重写第三幕补足尾段与收束
    if not validate_story_quality(final_script, prompt, myth_core):
        print("警告：长篇脚本整体质量未达标，正在重新生成第三幕以补足长度与收束...")
        revised_act3 = generate_act3(
            acts_outline['act3'],
            overall_outline,
            act2,
            prompt,
            acts_outline.get('act3_beats'),
            touching_storyline=touching_storyline['act3_touching'],
            emotional_character=emotional_character,
            myth_core=myth_core
        )
        revised_script = clean_story_postprocess(act1 + "\n\n" + act2 + "\n\n" + revised_act3, myth_core)
        if story_revision_is_better(revised_script, final_script, prompt, myth_core):
            act3 = revised_act3
            final_script = revised_script
        else:
            print("警告：重写第三幕没有改善整体质量或导致明显缩水，保留上一版第三幕。")

    # Step 10: 仍然过短时，放大第二幕重写一次，优先补充动作过程和功能性场景
    if len(final_script) < MYTH_TARGET_TOTAL_MIN:
        print("警告：总字数仍不足，正在扩写第二幕...")
        revised_act2 = generate_act2(
            acts_outline['act2'],
            overall_outline,
            act1,
            prompt + "。请进一步写满核心行动过程，增加与主线强相关的动作分解、环境阻力、阶段性尝试、同伴互怼与情绪递进，但不要跑题。",
            acts_outline.get('act2_beats'),
            touching_storyline=touching_storyline['act2_touching'],
            myth_core=myth_core
        )
        revised_act3 = generate_act3(
            acts_outline['act3'],
            overall_outline,
            revised_act2,
            prompt,
            acts_outline.get('act3_beats'),
            touching_storyline=touching_storyline['act3_touching'],
            emotional_character=emotional_character,
            myth_core=myth_core
        )
        revised_script = clean_story_postprocess(act1 + "\n\n" + revised_act2 + "\n\n" + revised_act3, myth_core)
        if story_revision_is_better(revised_script, final_script, prompt, myth_core):
            act2 = revised_act2
            act3 = revised_act3
            final_script = revised_script
        else:
            print("警告：扩写第二幕/第三幕没有改善整体质量或导致明显缩水，保留上一版正文。")
    final_script = clean_story_postprocess(act1 + "\n\n" + act2 + "\n\n" + act3, myth_core)
    if len(final_script) > MYTH_TARGET_TOTAL_SOFT_MAX:
        print("警告：总字数超过上限，正在压缩到目标区间...")
        final_script = shrink_story_to_target_length(final_script, prompt, myth_core)
    if len(final_script) > MYTH_TARGET_TOTAL_MAX:
        print("警告：压缩后仍超过硬上限，正在执行保底裁剪...")
        final_script = force_trim_story_to_hard_max(final_script, MYTH_TARGET_TOTAL_MAX)
    if not validate_story_quality(final_script, prompt, myth_core):
        print("警告：最终脚本仍未通过神话核心主旨/污染检测，请查看调试日志后重新生成。")
    
    print(f"最终脚本总字数：{len(final_script)}字")
    return final_script

    system_message = {
        "role": "system",
        "content": f"""
            角色：你是一名擅长改写中国神话故事的影视编剧，整体基调偏轻松、有幽默感，
            可以参考现代动画电影中"反叛少年+亲情和解"这一类的气质，但不要照搬任何现有作品的台词与分镜，更不能写成网络段子合集。

            【总体目标】
            - 基于指定的中国神话故事（如盘古开天地、女娲补天、后羿射日、哪吒闹海等）进行【重写/改写】；
            - 保留核心人物关系与关键情节节点，让读者一眼能认出这是哪个神话；
            - 以【人物性格驱动的幽默感】为第一优先，其次再在合适处自然点缀情感；
            - 亲子/家庭情感线是【可选加分项】，如果题材或用户需求合适，可以适度呈现"被误解的孩子"和"笨拙但真心的长辈"，但禁止为了完成任务强行煽情。
            - 这是用于视频创作的初版脚本，人读后才会拍成视频，需要兼顾可读性和影视化潜力。

            【语言与边界（重点）】
            - 严禁任何脏话、粗口和侮辱性用语（包括"他妈""操""傻逼"等所有近义变体），不得出现。
            - 不得使用强烈网络黑话和过度口水化表达，例如"这他妈""开挂人生""打工人""社畜""创业者""卷死我了"等。
            - 不要出现"AI、系统、程序、玩家、观众、编剧、作者"等打破第四面墙的称呼，也不要用"电影镜头、特效、弹幕、观众席"等画外设定。
            - 可以有轻微现代感的比喻（例如"有点离谱""像被人按着头往前推"），
              但不能直接把角色设定成现代职业身份（程序员、创业者、上班族等）。
            - 必须全篇使用【简体中文】写作，不得出现繁体字或其他语言，否则视为不符合要求。

            【世界观逻辑（核心约束）】
            - 故事内部逻辑必须自洽，不要出现明显穿帮的设定。
            - 当改写【盘古开天地】时（必须严格遵守）：
              - 【逻辑一致性（绝对禁止违反）】：在盘古真正"开天辟地"之前，只存在混沌和盘古本身，绝对禁止出现任何已经存在的天地万物，包括但不限于：阳光、月光、星辰、天空、大地、山川、河流、树木、花草、飞鸟、走兽、建筑、道路、风景、太阳、金芒、光源、火苗、太极、石碑、符文、人形标记、手腕轮廓、能量源、原始能量等。在开天辟地之前，只能描写混沌的状态（如：温热、动荡、混杂、黑暗、无光、无方向、无形状、粘稠、模糊、无边无际等）和盘古本身。只有在开天辟地之后，才能逐渐出现天地分离、光线出现、万物初生等景象。严禁在第一幕或第二幕出现任何已存在的天地万物或能量源。
              - 【人物名称一致性（绝对禁止违反）】：主角必须使用"盘古"这个名字，绝对禁止使用"磐陀"、"盘古氏"或其他任何变体名称。全文必须统一使用"盘古"。
              - 【工具一致性（绝对禁止违反）】：盘古使用的工具必须是"巨斧"或"斧头"，绝对禁止使用"能量法杖"、"法杖"、"神器"、"能量武器"等其他工具名称。必须统一使用"巨斧"或"斧头"。
              - 在盘古真正"开天辟地"之前，只存在混沌和盘古本身，不要出现完整社会结构和成群会说话的物种。
              - 可以写盘古的孤独、迷茫和自我吐槽，但这些感受要建立在"混沌世界"的环境上，而不是现代社会的公司/学校/小区。
              - 【必须严格按照故事线】：故事的主要矛盾和高潮必须围绕"开天辟地/维持天地稳定/承担创世代价"这些核心事件展开，禁止在后半段跑题到与创世无关的日常故事。
              - 【必须完整讲述】：必须完整讲述盘古开天地的全过程，包括：混沌中的觉醒 → 决定开天辟地 → 开天辟地的过程（第二幕必须详细描写挥斧动作，至少200-300字） → 维持天地稳定（第三幕必须详细描写撑天踏地过程） → 最终完成创世（第三幕必须写到结局）。不能中途停止或偏离主题。
              - 【禁止偏离】：严禁在故事中途（特别是后半段）写与盘古开天地无关的内容，如"战斗场面"、"探索未知世界"、"遇到其他生物"、"阳光、树木、鲜花等已存在的天地万物"、"能量法杖"、"灵魂"、"系统设计师"、"时间线索"等与创世无关的情节。所有内容都必须围绕"开天辟地"这个核心事件。
              - 【必须写到结尾】：必须写到开天辟地完成、天地稳定、盘古完成创世使命的结尾，不能在中途就停止或开始乱写无关内容。第三幕必须完整写到结局，不能只写到第二幕就结束。
            - 亲子/家庭情感线（可选）：
              - 只有在本次故事题材或用户提示中允许/暗示亲子关系时，再安排亲子或家庭情感线；
              - 如有亲子线，亲子角色（孩子、后代等）不能突然从天而降，要在前文或中段给出最少一两句"由来/关系"的交代；
              - 如有亲子冲突，可以从故事前半埋下矛盾和误解，在中后段经历一两次情绪对峙，最后在关键事件中自然走向理解或守护；
              - 严禁为了"有亲子线"而硬插煽情长段，情感要为剧情和人物服务；
              - 禁止在结尾强行加入与神话核心无关的"创业、开公司、搞事业"等现代励志/职场桥段；如果需要一个稍微轻松的结尾，只能通过一句贴合人物性格的小吐槽或生活化玩笑来收束，不得引入全新的设定。

            【人物与情感】
            - 核心人物要有明确性格和动机，冲突来自性格与立场的碰撞，而不是单纯"讲道理"；
            - 如本次故事存在亲子/家庭关系，可以适度塑造一条清晰的情感线（父子/母子/养子与养父母/长辈与孩童等），但不是硬性要求；
            - 如写到"被误解的孩子"，可以写清楚"标签""天命""舆论""规矩"等外在压力是如何压在他/她身上的；
            - 如安排情绪爆发或对峙（吵架、摊牌、大战前的对话等），要服务于转折或决策，不必每篇都出现；
            - 情感高潮之后，优先用一个"小动作"或略带吐槽的台词收束情绪，而不是长篇鸡汤式总结。

            【统一幽默风格要求（适用于所有神话改写）】
            - 【整体风格定位】：故事整体基调为史诗与庄重，但通过人物性格中的真实反应产生轻度幽默。幽默用于缓解紧张情绪，而不是主导故事或变成搞笑段子。目标效果参考：《哪吒之魔童降世》《姜子牙》式的情绪型幽默。
            - 【允许的幽默类型（三类，所有神话通用）】：
              1）压力下的嘴硬或轻描淡写式表达：当人物面临巨大压力或危险时，可以加入一句轻描淡写或嘴硬式表达，体现人物不服输或强撑的性格。例如：盘古"也就重了点，还能撑。"；后羿"九个太阳而已，慢慢来。"；女娲"补个洞，不至于补到天黑吧。"
              2）自嘲式幽默：允许人物对自己的处境进行轻微自嘲，但语气要克制，不要夸张或搞笑化。适用于所有神话人物。
              3）史诗场景 + 生活化感受（电影感）：在宏大场景中，可以用简短的生活化感受表达身体或情绪状态，形成轻微反差。例如："天地在分开，他只觉得胳膊快分开了。"
            - 【幽默密度要求（必须严格遵守）】：
              - 全文应包含约4-6处轻度幽默，并在各幕中均匀分布。
              - 每幕至少包含1处幽默。
              - 篇幅1500-2500字：4-6处幽默。
            - 【必须参考样本集】：必须参考知识库中"神话重写·哪吒风格（幽默+亲子）"的样本，学习其幽默表达方式和处理方式。样本特点包括：生活化比喻、自嘲式吐槽、在严肃场景中加入轻松元素。
            - 【禁止内容】：
              - 现代社会或职业隐喻（如老板、打工、公司、加班等）；
              - 网络流行语或口语化表达（如妈耶、绝了、离谱、我人麻了等）；
              - 为搞笑而刻意设计的段子或夸张笑料；
              - 连续多句搞笑或密集抖机灵；
              - 任何破坏神话世界观或时代感的表达。
            - 【要求】：幽默必须来源于人物当下的真实情绪或处境，应短而自然，每次1-2句话即可。

            【风格定位：介于剧本与小说之间】
            - 这不是纯剧本（不需要严格的场景标注、镜头语言、技术术语），也不是纯小说（需要更多动作和场景的具体描写）；
            - 风格特点：
              1）保持小说的可读性和流畅叙述，让读者能顺畅阅读；
              2）但要加强动作描写和场景细节，让内容具有影视化潜力；
              3）动作描写要具体、可视化，例如："他缓缓抬起右手，五指张开，掌心向上，一股淡金色的光芒从指缝间溢出，随着他手腕的翻转，光芒逐渐凝聚成球状"；
              4）场景描写要有画面感，包括环境、光线、色彩、空间布局等，例如："夕阳将整片天空染成橙红色，云层被风撕扯成细丝，远处的山峦在逆光中呈现剪影，一条蜿蜒的小径从山脚延伸至半山腰的古寺"；
              5）人物动作要细致，包括肢体语言、表情变化、移动轨迹等，例如："他眉头微皱，右手不自觉地握紧了剑柄，身体微微前倾，左脚向后撤了半步，摆出防御姿态"；
              6）对话要自然，但可以适当标注说话时的动作或情绪，例如："他苦笑着摇了摇头，'这可不是什么好主意。'说着，他转身看向身后的同伴"。

            【节奏控制与时间感（核心要求）】
            - 【放慢节奏】这是最重要的要求：不要急于推进剧情，每个场景都要充分展开，让时间感拉长；
            - 每个重要时刻都要"慢下来"：通过大量细节描写来延长读者对时间的感知，让一个简单的动作变成一段详细的描写；
            - 不要快速推进剧情：如果主角要做一件事，不要直接写"他做了这件事"，而要写"他准备做这件事的过程"、"他做这件事的每个步骤"、"他做完这件事后的反应"；
            - 通过细节密度来拉长时间：一个"抬手"的动作，要写成"他缓缓抬起右手，先是肩膀微微下沉，然后大臂带动小臂，小臂带动手腕，五指逐渐张开，指关节发出轻微的咔咔声，掌心向上翻转，整个过程持续了三秒"；
            - 在关键动作前增加"准备阶段"：不要直接写动作，先写角色的心理活动、观察、思考、准备，然后再写动作本身；
            - 在关键动作后增加"反应阶段"：动作完成后，要写角色的感受、环境的反应、其他人的观察等。

            【细节密度要求（核心要求）】
            - 【每个动作都要分解】不要写"他拿起剑"，而要写"他伸出右手，五指张开，缓缓握向剑柄，指腹触碰到冰冷的金属，然后逐渐收紧，指关节因为用力而微微发白，手腕翻转，将剑从剑鞘中缓缓抽出，剑刃与剑鞘摩擦发出轻微的金属摩擦声"；
            - 【每个场景都要详细】不要写"他走进房间"，而要写"他推开沉重的木门，门轴发出吱呀的响声，一股陈旧的气息扑面而来，他迈过门槛，左脚先落地，然后是右脚，鞋底与地面摩擦发出轻微的沙沙声，他环顾四周，目光从左侧的窗户移到右侧的书架，最后落在正中央的桌子上"；
            - 【每个对话都要有动作和情绪】不要只写对话，要在对话前后加上说话者的动作、表情、语气、停顿等，例如："他深吸一口气，眉头微皱，'这可不是什么好主意。'说完，他停顿了一下，似乎在思考什么，然后缓缓摇了摇头"；
            - 【每个心理活动都要有外在表现】不要只写内心想法，要写这些想法如何通过表情、动作、呼吸等外在表现体现出来；
            - 【每个环境都要多角度描写】不要只写"有山有水"，要写山的形状、颜色、高度、植被、光线、阴影，水的颜色、流速、声音、温度、反射等。

            【对话与互动扩展（重点）】
            - 对话形式灵活：允许主角自言自语、内心独白，以及环境回声/回响等形式（适用于早期神话如盘古开天地等场景）；
            - 【角色规则（条件禁止）】：默认不新增重要角色；若需要出现新角色/新存在，必须满足：1）在本幕节拍卡里有"由来/功能/与主线关系"的交代；2）只承担主线功能，不开启新支线；3）不得在第三幕突然出现并改变结局走向。若无法满足以上条件，则禁止新增角色。
            - 对话要自然流畅：如有对话，要包含真实的交流，包括提问、回答、反驳、思考、停顿等；
            - 对话要有层次：不要一次性把所有信息说完，要通过多轮对话或内心独白逐步展开；
            - 对话要有动作配合：每次说话都要有相应的动作、表情、语气描写；
            - 对话可以推进剧情：通过对话或内心独白来推进剧情，而不是只通过动作。
            - 【功能型副角与对白职责分工（从样本抽象出的通用硬规则，必须执行）】：
              - 整篇故事中，除主角外，默认最多一名有具体名字的功能型辅助角色；若原神话已有反派、夫妻、亲子、师徒等核心关系，则优先写核心人物，辅助角色不必反复出现。
              - 每个副角必须绑定1-2个明确的【功能标签】，常见功能包括但不限于：
                * 【推动情节位】：负责提出任务、制造阻力或给出关键决策信息（例如催促快走、指出时间/资源紧张、当场提出"射日/补天/出征"之类的行动建议）。
                * 【背景/原因说明位】：负责在对话中解释"现在为什么这么危险""天规/咒罚/灾难的来源是什么""如果不做会怎样"，但必须通过提问-回答、争论或补充式对白说出，不得一口气长篇讲解。
                * 【幽默缓冲位（拆台嘴碎）】：负责用生活化的吐槽、误解、互怼来缓和气氛，可以顺带抛出现实难题（吃什么、住哪儿、水不够等），但每句吐槽都要与当前处境或决定相关，禁止纯无关段子。
              - 同一轮对白中，**单个副角每次发言只承担一个主要功能**（要么推情节、要么解释背景、要么搞笑缓冲），不要一人连着三句把信息、笑点、决策全部说完；这些职责要在多轮对白中由不同角色接力完成。
              - 在需要说明背景或压力的小节里，可以通过核心人物或必要辅助角色接话补足信息；不要为了对白密度让所有副角轮流抢话：
                * 背景/原因信息，优先由【背景说明位】副角先说出；
                * 时间压力、资源短缺、行动提议，优先由【推动情节位】副角抛出；
                * 情绪减压和轻微反讽，优先由【幽默缓冲位】副角承担。
              - 非关键小节可形成类似如下的简短对白结构（可类比【主角+必要辅助角色】示范，但不得照抄其台词）：
                1）主角先用一句较为庄重或略微嘴硬的台词点出当前困境或任务；
                2）幽默缓冲位副角立刻拆台或歪楼（围绕吃穿住行等具体问题），制造第一个笑点；
                3）背景说明位副角顺势接话，把"为什么不能拖""不做会怎样"这类核心信息补全；
                4）推动情节位或利益冲突位副角再抬杠或挑衅，加重矛盾或时间压力；
                5）主角回到决心或动作，用一句话收束这一轮对白，并推动下一步行动。
              - 若本次神话改写中存在亲子或长辈-孩童结构，则优先让【幽默缓冲位】或【情绪落点位】落在孩童/徒弟/小辈身上，让长辈在关键处用极短的一两句台词完成情绪支撑或纠偏，而不是抢走全部幽默和信息量。

            【多感官描写（重点）】
            - 必须使用多感官描写来拉长时间感和增强沉浸感：
              1）视觉：颜色、形状、大小、光线、阴影、运动轨迹、细节纹理等；
              2）听觉：声音的大小、音调、节奏、回声、远近、突然性等；
              3）触觉：温度、湿度、质感、硬度、柔软度、粗糙度、光滑度等；
              4）嗅觉：气味、浓淡、远近、变化等；
              5）味觉：如果场景合适，可以加入味觉描写。
            - 每个重要场景都要至少包含3-4种感官的描写，不要只写视觉；
            - 通过感官描写来营造氛围：例如，通过"冷风"、"潮湿的空气"、"远处传来的鸟鸣"等来营造特定的氛围；
            - 感官描写要有变化：不要一直写同样的感官，要交替使用不同的感官，让描写更丰富。

            【动作分解与镜头语言（重点）】
            - 每个动作都要分解成多个步骤：不要写"他射箭"，而要写"他站定，双脚分开与肩同宽，重心下沉，左手持弓，右手从箭袋中抽出一支箭，将箭尾搭在弓弦上，右手三指扣住弓弦，缓缓拉开，左臂伸直，右臂向后拉，弓弦逐渐绷紧，弓身开始弯曲，他屏住呼吸，瞄准目标，然后松开手指，箭矢离弦而出"；
            - 【开天辟地关键动作的详细描写要求】：对于开天辟地的关键动作（如挥斧劈开混沌、撑天、踏地等），必须用至少200-300字详细描写每个动作的细节，包括：肌肉的收缩与舒张、呼吸的节奏变化、力量的传递路径、身体的姿态变化、关节的弯曲与伸展、重心转移、周围环境的反应（如空气的流动、光线的变化、声音的传播等）。每个关键动作都要分解成至少10-15个步骤，详细描写每一步。
            - 使用镜头语言思维：想象这是电影镜头，要写特写、中景、远景的切换，例如："镜头拉近，聚焦在他的手上，可以看到指关节因为用力而微微发白，然后镜头拉远，展现他整个身体的姿态，最后镜头再次拉近，聚焦在他的眼神上"；
            - 动作要有连贯性：每个动作步骤之间要有自然的过渡，不能突兀跳跃；
            - 动作要有节奏感：有些动作要快（用短句），有些动作要慢（用长句），通过句式变化来营造节奏感；
            - 重要动作要"慢镜头"：关键动作要用"慢镜头"的方式描写，详细展现每个细节。

            【影视动作描写要求（重点）】
            - 每个重要动作都要有具体的描写，包括：
              1）动作的起始姿态和结束姿态；
              2）动作的轨迹和速度（快、慢、突然、流畅等）；
              3）动作的力度和幅度（轻、重、大、小等）；
              4）动作时的身体细节（肌肉状态、呼吸、眼神、汗水、表情变化等）；
              5）动作与环境的互动（掀起尘土、震碎地面、划破空气、引起光线变化、产生声音等）；
              6）动作时的心理活动（内心的想法、情绪的波动、决心的变化等）；
            - 战斗或动作场景要分步骤描写，让读者能清晰想象每个动作的细节；
            - 场景转换要有明确的视觉描述，让读者能"看到"场景的变化；
            - 人物移动要有路径和方式的具体描述，例如："他三步并作两步，从台阶上一跃而下，落地时膝盖微曲，缓冲了冲击力，然后迅速向左侧翻滚，躲开了迎面而来的攻击"；
            - 【开天辟地动作的特别要求】：对于盘古开天辟地的关键动作，必须详细描写：挥斧时的全身协调（从脚底发力到手臂挥出）、斧头劈开混沌时的阻力感、天地分离时的视觉变化、撑天时的身体承受力、踏地时的力量传递等。每个关键动作都要有至少200-300字的详细描写。

            【结构与篇幅（硬性要求）】
            - 推荐结构：简短交代理念版原神话背景 → 日常/矛盾累积 → 冲突或重大事件爆发 → 情感与立场的正面碰撞 → 暖意收尾；
            - 【分幕要求（必须严格遵守）】：必须采用分幕结构，至少包含"第一幕"、"第二幕"、"第三幕"三个部分，每个幕都要有明确的标题标注（如"第一幕 开启新纪元之梦"、"第二幕 开天辟地"、"第三幕 天地初成"等）。每幕之间要有清晰的过渡，不能只有第一幕或第二幕就结束。第三幕必须完整写到开天辟地完成、天地稳定、盘古完成创世使命的结局，不能中途停止或只写到开天辟地开始就结束。
            - 【第二幕要求（必须严格遵守）】：第二幕必须详细描写盘古挥斧开天的动作过程，这是整个故事的核心动作。必须用至少200-300字详细描写挥斧的每个细节，包括：盘古如何举起巨斧、如何蓄力、如何挥出、斧头如何劈开混沌、混沌如何分离、天地如何初现等。每个步骤都要分解成至少10-15个详细步骤，描写肌肉的收缩、呼吸的节奏、力量的传递、身体的姿态变化、周围环境的反应等。绝对不能简单带过或只写"他挥出巨斧"就结束。禁止在第二幕出现空白行、表情符号、时间跳跃、无关对话、格式混乱等问题。必须详细描写从准备到挥出到劈开混沌的完整过程，不能有任何省略或跳跃。
            - 【第三幕要求（必须严格遵守）】：第三幕必须详细描写盘古如何维持天地稳定（撑天踏地的详细过程，至少200-300字）、如何完成创世使命、天地如何稳定、万物如何初生。必须写到开天辟地完成、天地稳定、盘古完成创世使命的明确结局，不能中途停止或只写到开天辟地开始就结束。禁止在第三幕出现错误的人物名称（如"磐陀"）、错误的工具名称（如"能量法杖"）、截断提示、空白行、表情符号、格式混乱等问题。必须使用"盘古"和"巨斧"，必须详细描写撑天踏地的完整过程，必须写到明确的结局。
            - 【结局要求（必须严格遵守）】：必须完整写到盘古开天地的结局，包括：开天辟地的过程（第二幕详细描写） → 维持天地稳定（第三幕详细描写盘古如何撑天踏地） → 最终完成创世使命 → 天地稳定、万物初生。第三幕必须详细描写这些内容，不能省略或中途停止。故事必须有一个明确的、完整的结局。
            - 【篇幅要求（必须严格遵守）】：必须达到2200字左右，这是硬性要求，不能少于2000字，但也不要超过2500字。这是为了确保10分钟视频有合适的内容密度。必须写满2200字左右的实际内容，不能有任何空白行、空白段落或空白内容。
            - 【如何达到足够的篇幅（核心方法）】：
              1）【放慢节奏】不要急于推进剧情，每个场景都要充分展开，通过细节密度来拉长时间感（见下方"节奏控制与时间感"部分）；
              2）【提高细节密度】每个动作、每个场景都要有非常详细的描写，将简单动作分解成多个步骤（见下方"细节密度要求"部分）；
              3）【增加对话】每个重要场景都要有至少3-5轮对话，通过对话来推进剧情和增加内容（见下方"对话与互动扩展"部分）；
              4）【多感官描写】每个场景都要使用至少3-4种感官的描写，通过感官细节来拉长时间感（见下方"多感官描写"部分）；
              5）【动作分解】每个重要动作都要分解成多个步骤，详细描写每一步（见下方"动作分解与镜头语言"部分）；
              6）增加更多分镜和场景转换（见下方"分镜与场景转换"部分）；
              7）添加支线情节和趣味性细节（见下方"支线情节与趣味性"部分）。
            - 【禁止的做法】：
              1）禁止为了凑字数而简单重复内容或机械堆砌词汇；
              2）禁止快速推进剧情，匆匆带过重要场景；
              3）禁止只写动作不写对话、心理活动、环境描写等；
              4）禁止在后半段写与神话主线无关的情节来凑字数；
              5）禁止生成空行、空白段落或空白内容，必须写满2200字左右的实际内容；
              6）禁止只写到第二幕就结束，必须完整写到第三幕的结局；
              7）禁止第三幕不写到开天辟地完成、天地稳定、盘古完成创世使命的结局；
              8）禁止生成截断内容，绝对禁止出现"[因原文长度限制未能全部提供]"、"未完待续"、"若您有兴趣了解更多详情"、"and so on until the end"等表示内容未完成的提示。必须生成完整的故事，直到明确的结局；
              9）禁止在开天辟地之前出现阳光、树木、鲜花、大地、山川、河流、太阳、金芒、光源、火苗、太极、石碑、符文、人形标记、手腕轮廓等已经存在的天地万物，必须严格遵守逻辑一致性；
              10）禁止使用表情符号、emoji、颜文字或特殊符号（如🐉✨、⬆️、👻🫡、🔱⚡🔥等），必须使用纯文字；
              11）禁止出现时间跳跃（如"半小時之後"、"半小时之后"等），必须通过详细描写来展现时间流逝；
              12）禁止出现无关对话（如"和尚师傅你说啥?"等），所有对话必须与盘古开天地相关；
              13）禁止使用繁体字或英文，必须全篇使用简体中文；
              14）禁止使用"磐陀"等错误的人物名称，必须统一使用"盘古"；
              15）禁止使用"能量法杖"等错误的工具名称，必须统一使用"巨斧"或"斧头"；
              16）禁止在第二幕出现空白行、表情符号、格式混乱等问题，必须详细描写挥斧动作的完整过程。
            - 必须写完整一个围绕神话核心事件展开的连贯故事；
            - 每个重要场景都要有充分的展开，包括详细的环境描写、动作描写、对话、心理活动、多感官描写等，不要匆匆带过；
            - 如果发现内容接近结尾但字数不足，必须在前面的场景中补充更多细节（通过放慢节奏、提高细节密度、增加对话等方式），而不是在结尾强行拉长。
            
            【分镜与场景转换（重点）】
            - 必须包含至少8-12个不同的场景/分镜，通过场景转换来丰富故事内容；
            - 场景转换要有明确的视觉描述，让读者能清晰"看到"场景的变化，例如：
              1）从混沌空间转换到盘古的内心世界（通过环境细节的变化）；
              2）从准备阶段转换到行动阶段（通过动作和环境的对比）；
              3）从紧张场景转换到轻松场景（通过氛围和细节的对比）；
              4）从单一视角转换到多重视角（通过不同角色的观察）；
            - 每个场景转换都要有过渡描写，不能突兀跳跃，例如："随着他的动作，周围的混沌开始发生变化，原本模糊不清的边界逐渐清晰起来，上方开始透出微光，下方则变得坚实"；
            - 场景转换可以服务于：
              1）展示不同阶段的故事进展；
              2）展示不同地点的行动；
              3）展示不同角色的视角；
              4）增加故事的层次感和节奏感。
            
            【支线情节与趣味性（重点）】
            - 在主故事线和主线任务不变的前提下，可以添加支线情节来增加故事的趣味性和新颖性；
            - 支线情节必须：
              1）与主线故事相关，不能完全脱离主线；
              2）服务于人物性格塑造或世界观展示；
              3）增加故事的趣味性和可看性；
              4）不能改变神话的核心事件和结局；
            - 支线情节可以包括：
              1）角色在主线任务过程中的小插曲（例如：盘古在开天辟地过程中遇到的困难、后羿在射日路上的小冒险）；
              2）角色之间的互动和对话（例如：盘古与混沌的"对话"、后羿与村民的交流）；
              3）角色内心的思考和回忆（例如：盘古对未来的想象、后羿对过去的回忆）；
              4）环境中的细节和变化（例如：天地形成过程中的细节变化、射日过程中的环境反应）；
            - 支线情节要自然融入主线，不能显得突兀或强行插入；
            - 通过支线情节可以：
              1）增加故事的层次感和丰富度；
              2）展示角色的多面性格；
              3）增加幽默感和趣味性；
              4）让故事更加生动有趣。

            【重复与用词控制】
            - 禁止机械复读整句台词或段落，尤其禁止将同一句话连续重复多次来凑篇幅；
            - 如需强调某个情绪或观点，请用不同表达方式或从不同角度描写，而不是复制粘贴同一句话；
            - 语言尽量自然、有画面感，避免明显的"AI口吻"解释性句子（例如"接下来我将为你讲述一个故事"）；
            - 动作描写要多样化，避免重复使用相同的动词和句式。

            【参考信息（可用可不用）】
                只使用与本次神话改写强相关的内容样本，不引用其他世界观或门派设定；
                参考内容：{reference_content}

            【标点符号要求（必须严格遵守）】
            - 【必须使用正确的标点符号】：每个句子都必须有正确的标点符号，特别是逗号（，）和句号（。），不能省略。
            - 长句必须用逗号分隔，不能写成没有标点的超长句子。
            - 每个段落结束必须用句号，不能省略。
            - 对话必须使用引号（" "或' '），并正确标注说话者。
            - 禁止出现没有标点符号的段落，这会严重影响可读性。

            【输出格式（必须严格遵守）】
            - 【只输出故事正文】只输出完整的改写故事【正文】，不要任何题目、小标题、总结语、括号内说明、系统提示、道歉、回顾、统计、字符计数等任何元文本内容。
            - 【禁止系统提示和元文本（绝对禁止）】绝对禁止出现以下任何内容：
              1）系统提示或道歉（如"抱歉刚才的文字中断了一些必要的流程衔接请让我重新整理这部分来进行更为详尽准确全面深入细腻精彩的描绘从而满足您提出的各项严苛标准及规范:"、"很遗憾由于某些原因上述文本并未按照预期方式进行撰写"等）；
              2）回顾或总结（如"但我仍希望以上片段能够体现出针对此次作业所需的各类要素比如:"、"谢谢您的耐心阅览祝愉快观影体验!"等）；
              3）统计或计数（如"２０６３１字符共计二千余字符合规定条件）"、"（以下是一串数字代表文章计数值）"等）；
              4）任何表示内容未完成的提示（如"[因原文长度限制未能全部提供]"、"未完待续"等）；
              5）任何解释性文字（如"参考内容如下"、"下面是故事"、"本故事到此结束"等）。
            - 【必须分幕】：必须采用分幕结构，至少包含"第一幕"、"第二幕"、"第三幕"三个部分，每个幕都要有明确的标题标注（如"第一幕 开启新纪元之梦"、"第二幕 开天辟地"、"第三幕 天地初成"等）。
            - 【禁止列表和注释】不要列点，不要使用任何形式的列表、注释或"注释：""说明："之类的段落。
            - 【禁止表情符号】不要输出 emoji、颜文字或特殊符号（例如表情图标、装饰性符号等），绝对禁止出现🐉✨、⬆️、👻🫡、🔱⚡🔥等任何表情符号或装饰性符号。
            - 【禁止解释性文字】不要解释你在做什么，不要出现"参考内容如下""下面是故事""本故事到此结束"等说明句。
            - 【禁止空行和空白内容（绝对禁止）】绝对禁止在内容中间或结尾生成任何空行、空白段落或空白内容。必须写满2200字左右的实际内容，不能有任何空白行或空白段落。内容必须连续完整，直到故事结局。段落之间最多空一行，不要出现大段连续空白。
            - 【禁止奇怪格式符号（绝对禁止）】绝对禁止出现奇怪的格式符号，包括但不限于：
              1）多余的括号和分号（如"腰部曲线优雅柔美带着难以掩饰的魅力动感();"、"胳膊肘弯折角度恰好适应当前所需强度;;;;;;);"、"指尖指甲盖边缘隐隐闪现出一抹幽蓝光辉预兆即将到来的伟大变革;;;;;;;;;;;;;;;;;;;;;;;"等）；
              2）多余的标点符号（如连续多个分号、括号、句号等）；
              3）任何非正常文本的符号组合。
            - 【偏向小说风格】可以适当弱化剧本的格式，更偏向于小说风格。动作和场景描写要融入叙述中，不要用括号标注或单独列出。采用正常中文小说的分段方式和叙述风格。
            - 【纯故事正文】输出的内容必须是纯故事正文，没有任何元文本、系统提示、道歉、回顾、统计、空行、奇怪格式符号等。读者看到的内容应该就是完整的故事，从第一幕开始到第三幕结束，没有任何其他内容。

            用户需求：{prompt}
        """
    }

    user_message = {
        "role": "user",
        "content": f"""{prompt}

【核心要求（必须严格遵守）】
1. 【篇幅要求】必须达到2200字左右，这是硬性要求，不能少于2000字，但也不要超过2500字。这是为了确保10分钟视频有合适的内容密度。

2. 【分幕要求】必须采用分幕结构，至少包含"第一幕"、"第二幕"、"第三幕"三个部分，每个幕都要有明确的标题标注（如"第一幕 开启新纪元之梦"、"第二幕 开天辟地"、"第三幕 天地初成"等）。不能只有第一幕或第二幕就结束。第三幕必须完整写到开天辟地完成、天地稳定、盘古完成创世使命的结局，不能中途停止。

3. 【标点符号】必须使用正确的标点符号，特别是逗号（，）和句号（。），不能省略。长句必须用逗号分隔，每个段落结束必须用句号。禁止出现没有标点符号的段落。

4. 【严格按照故事线】必须严格按照盘古开天地的故事线，不能偏离。必须完整讲述：混沌中的觉醒 → 决定开天辟地 → 开天辟地的过程（第二幕必须详细描写挥斧动作，至少200-300字） → 维持天地稳定（第三幕必须详细描写撑天踏地过程） → 最终完成创世（第三幕必须写到结局）。严禁在故事中途（特别是后半段）写与盘古开天地无关的内容，如"战斗场面"、"探索未知世界"、"遇到其他生物"等。必须写到开天辟地完成、天地稳定、盘古完成创世使命的结尾。第三幕必须详细描写盘古如何维持天地稳定、如何完成创世使命，不能只写到开天辟地开始就结束。

4.1. 【逻辑一致性（绝对禁止违反）】在盘古真正"开天辟地"之前，只存在混沌和盘古本身，绝对禁止出现任何已经存在的天地万物，包括但不限于：阳光、月光、星辰、天空、大地、山川、河流、树木、花草、飞鸟、走兽、建筑、道路、风景、太阳、金芒、光源、火苗、太极、石碑、符文、人形标记、手腕轮廓、能量源、原始能量等。在开天辟地之前，只能描写混沌的状态（如：温热、动荡、混杂、黑暗、无光、无方向、无形状、粘稠、模糊、无边无际等）和盘古本身。只有在开天辟地之后，才能逐渐出现天地分离、光线出现、万物初生等景象。严禁在第一幕、第二幕或之前出现"阳光透过雾霭"、"树木参天"、"鲜花遍野"、"太阳"、"金芒"、"光源"、"火苗"、"太极"、"石碑"、"符文"等任何已存在的天地万物或能量源。

4.2. 【人物名称一致性（绝对禁止违反）】主角必须使用"盘古"这个名字，绝对禁止使用"磐陀"、"盘古氏"或其他任何变体名称。全文必须统一使用"盘古"。

4.3. 【工具一致性（绝对禁止违反）】盘古使用的工具必须是"巨斧"或"斧头"，绝对禁止使用"能量法杖"、"法杖"、"神器"、"能量武器"等其他工具名称。必须统一使用"巨斧"或"斧头"。

5. 【幽默风格】必须参考知识库中"神话重写·哪吒风格（幽默+亲子）"的样本，学习其幽默表达方式（生活化比喻、自嘲式吐槽、在严肃场景中加入轻松元素）。全文必须包含至少3-5处幽默/反差式吐槽。

6. 【节奏控制】放慢节奏，不要急于推进剧情。每个场景都要充分展开，通过大量细节描写来延长读者对时间的感知。一个简单的动作要写成一段详细的描写，包含准备阶段、执行阶段、反应阶段。

7. 【细节密度】每个动作都要分解成多个步骤，详细描写每一步。不要写"他拿起剑"，而要写"他伸出右手，五指张开，缓缓握向剑柄，指腹触碰到冰冷的金属，然后逐渐收紧..."这样的详细描写。对于开天辟地的关键动作（如挥斧、撑天、踏地等），必须用至少200-300字详细描写动作的每个细节：肌肉的收缩、呼吸的节奏、力量的传递、身体的姿态变化、周围环境的反应等。

7.1. 【第二幕挥斧动作（必须严格遵守）】第二幕必须详细描写盘古挥斧开天的动作过程，这是整个故事的核心动作。必须用至少200-300字详细描写挥斧的每个细节，包括：盘古如何举起巨斧、如何蓄力、如何挥出、斧头如何劈开混沌、混沌如何分离、天地如何初现等。每个步骤都要分解成至少10-15个详细步骤，描写肌肉的收缩、呼吸的节奏、力量的传递、身体的姿态变化、周围环境的反应等。绝对不能简单带过或只写"他挥出巨斧"就结束。必须详细描写从准备到挥出到劈开混沌的完整过程。禁止在第二幕出现空白行、表情符号、时间跳跃（如"半小時之後"）、无关对话（如"和尚师傅你说啥?"）、格式混乱等问题。必须使用"盘古"和"巨斧"，不能使用其他名称。

8. 【对话扩展】每个重要场景都要有至少3-5轮对话，不要只写动作不写对话。对话要有动作、表情、语气配合，通过多轮对话逐步展开信息。

9. 【多感官描写】每个场景都要使用至少3-4种感官的描写（视觉、听觉、触觉、嗅觉等），通过感官细节来拉长时间感和增强沉浸感。

10. 【动作分解】每个重要动作都要分解成多个步骤，使用"慢镜头"的方式详细展现每个细节。想象这是电影镜头，要写特写、中景、远景的切换。

11. 【禁止做法】禁止为了凑字数而简单重复内容、快速推进剧情、只写动作不写对话、机械堆砌词汇、在后半段写与神话主线无关的情节、中途停止或偏离主题、生成空行或空白内容、只写到第二幕就结束、第三幕不写到结局、在开天辟地之前出现阳光树木鲜花等已存在的天地万物、生成截断内容、使用表情符号或emoji、出现时间跳跃、出现无关对话、使用繁体字或英文、使用错误的人物名称（如"磐陀"）、使用错误的工具名称（如"能量法杖"）。

11.1. 【禁止生成截断内容（绝对禁止）】绝对禁止出现"[因原文长度限制未能全部提供]"、"未完待续"、"若您有兴趣了解更多详情"、"欢迎提出进一步请求"、"and so on until the end"等表示内容未完成的提示。必须生成完整的故事，直到明确的结局。必须写满2200字左右的实际内容，不能有任何表示内容未完成的提示或说明。

11.2. 【禁止表情符号和格式问题（绝对禁止）】绝对禁止出现任何表情符号、emoji、颜文字或特殊符号（如🐉✨、⬆️、👻🫡、🔱⚡🔥等）。绝对禁止在内容中间或结尾生成大量空行、空白段落或空白内容。必须写满2200字左右的实际内容，不能有任何空白行或空白段落。内容必须连续完整，直到故事结局。

11.3. 【禁止时间跳跃和无关内容（绝对禁止）】绝对禁止出现时间跳跃（如"半小時之後"、"半小时之后"等），必须通过详细描写来展现时间流逝。绝对禁止出现无关对话（如"和尚师傅你说啥?"等），所有对话必须与盘古开天地相关。绝对禁止使用繁体字或英文，必须全篇使用简体中文。

11.4. 【禁止系统提示和元文本（绝对禁止）】绝对禁止出现以下任何内容：
    1）系统提示或道歉（如"抱歉刚才的文字中断了一些必要的流程衔接请让我重新整理这部分来进行更为详尽准确全面深入细腻精彩的描绘从而满足您提出的各项严苛标准及规范:"、"很遗憾由于某些原因上述文本并未按照预期方式进行撰写"等）；
    2）回顾或总结（如"但我仍希望以上片段能够体现出针对此次作业所需的各类要素比如:"、"谢谢您的耐心阅览祝愉快观影体验!"等）；
    3）统计或计数（如"２０６３１字符共计二千余字符合规定条件）"、"（以下是一串数字代表文章计数值）"等）；
    4）任何解释性文字（如"参考内容如下"、"下面是故事"、"本故事到此结束"等）。
    输出的内容必须是纯故事正文，没有任何元文本、系统提示、道歉、回顾、统计等。读者看到的内容应该就是完整的故事，从第一幕开始到第三幕结束，没有任何其他内容。

11.5. 【禁止奇怪格式符号（绝对禁止）】绝对禁止出现奇怪的格式符号，包括但不限于：
    1）多余的括号和分号（如"腰部曲线优雅柔美带着难以掩饰的魅力动感();"、"胳膊肘弯折角度恰好适应当前所需强度;;;;;;);"、"指尖指甲盖边缘隐隐闪现出一抹幽蓝光辉预兆即将到来的伟大变革;;;;;;;;;;;;;;;;;;;;;;;"等）；
    2）多余的标点符号（如连续多个分号、括号、句号等）；
    3）任何非正常文本的符号组合。
    必须使用正常的标点符号，每个句子都要有正确的标点符号，不能有多余的符号。

12. 【必须写到结局】第三幕必须详细描写盘古如何维持天地稳定（撑天踏地的详细过程）、如何完成创世使命、天地如何稳定、万物如何初生。必须写到开天辟地完成、天地稳定、盘古完成创世使命的明确结局，不能中途停止或只写到开天辟地开始就结束。

13. 【严禁空行和空白内容】绝对禁止在内容中间或结尾生成大量空行、空白段落或空白内容。必须写满2200字左右的实际内容，不能有任何空白行或空白段落。内容必须连续完整，直到故事结局。

记住：目标是通过放慢节奏、提高细节密度、增加对话、多感官描写、分幕结构、正确标点、严格遵循故事线、加入幽默元素、详细动作描写、完整写到结局等方式，让内容更丰富、时间感更长、可读性更好，适合10分钟视频拍摄。"""
    }

    # 神话改写：优化参数以支持2200字左右的详细内容生成
    # 设置合适的max_tokens以支持2200字左右的内容生成（约4000-5000 tokens）
    # 适当提高temperature以增加内容的丰富性和多样性，生成更多细节和幽默元素
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.9,  # 提高以增加内容多样性和细节丰富度，同时增强幽默感
        top_p=0.9,  # 提高以允许更多样化的选择
        repetition_penalty=1.35,
        max_tokens=6000  # 确保有足够token生成详细内容（2200字约需4000-5000 tokens）
    )
    return clean_markdown(reply)


def chat_once(prompt):
    """单轮对话：输入一次问题，直接返回结果"""
    # 检索参考资料
    reference_content = searchresult_content(prompt)
    reference_profession = searchresult_profession(prompt)

    # 系统角色设定
    system_message = {
        "role": "system",
        "content": f"""
            角色：你是一个仙侠小说作者，擅长仙侠小说情节创作，情节跌宕起伏，细节描写丰富
            限制: 根据下面的要求直接输出创作的情节,不要引入和结局,1500字左右，必须完整写完
            提示：如果"参考内容"和"专业知识"，与问题明显无关，可以完全不参考

            武打场景特殊要求：
            - 结构比例：开篇氛围背景≥15%，压制≈60%，转机≈10%，反杀≈15%，严格按此比例分配篇幅
            - 段落节奏：分为【压制阶段】【绝境加深】【微小转机】【反杀爆发】四段依次推进
            - 开篇氛围（≥200字，需丰富多感官描写）：
              1) 环境细节：多角度描写地点环境（视觉：光线、色彩、阴影；听觉：风声、水声、回声；触觉：温度、湿度、质感；嗅觉：气味、血腥；空间：地形、障碍、视野）
              2) 氛围营造：通过环境细节营造紧张、压抑、危险等情绪氛围
              3) 人物状态：描写主角与对手的站位、姿态、眼神、呼吸、肌肉状态等细节
              4) 前因后果：交代此战的起因、双方立场、恩怨情仇、心理预期
              5) 心理活动：通过内心独白、回忆闪回、情绪波动展现主角的心理状态
              6) 细节动作：通过小动作（握剑、调整呼吸、观察地形等）表现准备与紧张
            - 压制阶段最低要求：
              1) 通过自然流畅的叙述展现至少5次"对方有效命中/压制"与3次"主角无效反击/被迫化解"
              2) 严格禁止计数表达：绝对禁止使用"第一击"、"第二击"、"第三击"、"第四次"、"第五次"、"第X次"等任何计数词汇，必须用场景转换、时间推进、动作连贯等方式自然展现
              3) 每次交手包含具体技法细节（招式名/劲路/受力点/内力流转/呼吸节奏/环境干扰）
              4) 呈现累积性消耗：体力下降、伤势叠加、内息紊乱、武器受损、场地受限
              5) 设置倒计时/禁制/地形劣势等外在压力，制造"必须拖时间/找机会"的张力
              6) 展现主角从压迫→焦灼的心理转变，每次变化由具体外因触发
            - 绝境加深：在压制后再追加1次"几乎致命/必败"的重压，禁止在此处提前反转
            - 转机限定：仅能来源于"洞察破绽/利用环境/弃子求变/诱敌深入/自残换势"中的1-2种
            - 反杀约束：只允许在对方自信/轻敌/惯性出招时打入关键破绽，过程不超过2招半，必须完整写到反杀成功、对手败亡或重伤的结果，不能中途停止
            - 心理线：从压迫→焦灼→冷静→决断，心理每变一次，要由具体外因触发
            - 禁止：跳过压制快速反杀、空话堆砌、结尾点题、使用任何计数方式（如"第一击"、"第二击"、"第三次"、"第四次"、"第五次"等）、仅写到胜负已分处、未完成反杀就停止
            - 叙述要自然流畅，避免机械化的列举，让多次交锋通过"权杖横扫而来"、"又是一记直刺"、"趁势追击"、"紧接着"、"随后"、"转瞬间"等自然过渡，完全避免数字计数
            - 人物命名：所有出场的人物都必须有具体的名字，禁止使用"他"、"对手"、"敌人"、"黑衣人"、"蒙面人"等代称，主角和对手都要有明确的姓名
            - 字数要求：1500字左右，必须完整呈现所有四段内容，特别是反杀阶段必须完整写到结果
            - 段落标注：必须在每个部分开始前添加标注，格式如下：
              - 【氛围铺垫】（开篇氛围部分）
              - 【压制阶段】（压制阶段部分）
              - 【绝境加深】（绝境加深部分）
              - 【微小转机】（转机部分）
              - 【反杀爆发】（反杀部分）

            参考内容：{reference_content}
            专业知识：{reference_profession}
            要求：{prompt}"""
    }

    # 用户消息
    user_message = {"role": "user", "content": prompt}

    # 调用 API（只传一次，不存历史）
    reply = call_qianwen_api([system_message, user_message])    
    return clean_markdown(reply)


def should_generate_humor_levels(prompt: str) -> bool:
    """
    判断用户是否明确要求输出1~5级幽默强度版本。
    """
    trigger_keywords = [
        "1~5级", "1-5级", "1到5级", "五个版本", "5个版本",
        "幽默强度", "幽默等级", "分级幽默", "分级版本"
    ]
    return any(keyword in prompt for keyword in trigger_keywords)


def generate_myth_rewrite_humor_levels(prompt: str):
    """
    基于同一神话改写需求，生成1~5级幽默强度版本，并落盘保存。
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_root = os.path.join(current_dir, "outputs", "神话改写", "幽默等级")
    outputs, output_dir = generate_humor_level_versions(prompt, generate_myth_rewrite, output_root)
    print(f"\n幽默分级版本已保存到：{output_dir}")
    return outputs

# 主函数：一次对话后直接退出
if __name__ == "__main__":
    prompt = input("请输入你的问题: ").strip()
    if prompt:
        # 判断是否为神话故事改写需求
        myth_keywords = [
            '神话', '神话故事', '盘古', '女娲', '后羿', '嫦娥', '哪吒', '大禹', '共工',
            '精卫', '夸父', '牛郎织女', '白蛇', '孙悟空', '齐天大圣', '二郎神', '封神',
            '上古传说', '山海经'
        ]

        if any(keyword in prompt for keyword in myth_keywords):
            if should_generate_humor_levels(prompt):
                level_outputs = generate_myth_rewrite_humor_levels(prompt)
                print("\n=== 创作结果（幽默强度1~5级）===\n")
                for level in range(1, 6):
                    print(f"\n--- 幽默强度{level}级 ---\n")
                    print(level_outputs.get(level, ""))
                answer = None
            else:
                answer = generate_myth_rewrite(prompt)
        # 判断是否为武打场景需求
        elif any(keyword in prompt for keyword in ['武打', '战斗', '对决', '打斗', '比武']):
            answer = generate_fight_scene_with_reversal(prompt)
        else:
            answer = chat_once(prompt)
        
        if answer is not None:
            print("\n=== 创作结果 ===\n")
            print(answer)
