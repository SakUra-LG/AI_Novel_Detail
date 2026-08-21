import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import main as project


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PLAN_PATH = BASE_DIR / "knowledgeBase" / "myth_chapter_plans_rebuild.json"
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs" / "20个神话故事（逐篇重制版）"
DIRECTLY_ACCEPTED = {"大禹治水", "后羿射日", "哪吒闹海"}

HARD_META_TERMS = (
    "根据指令",
    "根据要求",
    "自动补充",
    "以下是符合",
    "正式修改内容",
    "虚构文学样章",
    "写作要求",
    "本章任务",
    "本章目标",
    "前文状态",
    "后续尚未发生",
    "字数统计",
)

ANACHRONISM_TERMS = (
    "生态环境",
    "自然灾害",
    "专业救援",
    "救援队伍",
    "计算器",
    "输入数据",
    "设备故障",
    "设备",
    "市民",
    "维纳斯",
    "上帝",
    "日历簿",
    "手榴弹",
    "大熊猫",
    "工匠精神",
    "宇宙生成术士",
    "工作报告",
    "项目",
    "系统",
    "直播",
    "网络",
    "分钟",
    "小时",
    "百分比",
    "纸页",
    "纸背",
    "册页",
    "农历",
)

LOWBROW_TERMS = (
    "裤裆",
    "走光",
    "裸露身体",
    "赤裸身体",
    "尿",
    "屎",
    "呕吐物",
    "分泌物",
)

ADMIN_TERMS = (
    "流程",
    "备案",
    "核查",
    "验讫",
    "签字画押",
    "编号登记",
    "合规",
    "本地化",
)

GRAPHIC_OR_TECHNICAL_BODY_TERMS = (
    "横膈",
    "喉管",
    "皮肉翻卷",
    "骨缝间",
    "肩胛两侧肌肉",
    "颈侧皮肤尚存一道裂口",
    "生理反应",
    "分泌物",
    "肩胛骨",
    "耳鼓",
    "耳膜",
    "血珠",
    "血丝",
    "伤口周围",
    "喙部渗出",
    "勒进肉里",
    "钉穿",
    "穿小腿",
    "缺氧",
    "肺腑",
    "瞳孔",
    "伤疤",
    "粉嫩肤",
    "露出底下",
    "腥甜味",
    "紫黑色黏稠",
    "血滴",
    "血痕",
    "流血",
    "脱皮",
    "皮肤",
    "骨头",
    "骨架",
    "关节",
    "肋下",
    "脚蹼",
    "鼻腔",
    "舌根",
    "锁骨",
    "膝盖",
    "额角",
    "脚踝",
    "胸脯",
    "躯干",
    "五指",
    "伤口",
)

TECHNICAL_NARRATION_TERMS = (
    "玄武岩",
    "页岩",
    "铁矿渣",
    "四十五度",
    "风暴眼",
    "投点",
    "基座",
    "储备物资",
    "海际线",
    "主风口",
    "热气托举",
    "珊瑚骸骨",
    "天然漏斗",
    "纤维",
    "结晶体",
    "精确角度",
    "微型堰坝",
    "校准刻度",
    "精确角度",
    "涡流",
    "暗流",
    "流势",
    "重心",
    "惯性",
    "海域",
    "喉囊",
    "嗉囊",
    "唾液",
    "定点",
    "截面",
    "盐晶",
    "材料清单",
    "砂岩",
    "赭红岩",
    "臂展",
    "第一寸",
)

TRADITIONAL_POLLUTION_CHARS = set(
    "衛為與後時個們說這來體畫計紙裡邊發風雲萬專業實寧眾會書樂東"
)
TRADITIONAL_TO_SIMPLIFIED = str.maketrans(
    {
        "衛": "卫", "為": "为", "與": "与", "後": "后", "時": "时",
        "個": "个", "們": "们", "說": "说", "這": "这", "來": "来",
        "體": "体", "畫": "画", "計": "计", "紙": "纸", "裡": "里",
        "邊": "边", "發": "发", "風": "风", "雲": "云", "萬": "万",
        "專": "专", "業": "业", "實": "实", "寧": "宁", "眾": "众",
        "會": "会", "書": "书", "樂": "乐", "東": "东",
    }
)

STYLE_BASELINE = """
村口老人把饼翻了个面，背面黑得很有主见。他叹气说：“它若再熟一点，
就该自己下地走了。”旁人笑了一声，手里的活却没停。笑只是让人在难处里
喘一口气，不把事情说轻。

真正到了要紧处，众人都安静下来。主角低头检查手里的东西，一处一处摸过，
不说漂亮话。阿满也把笑收住，只在青竹简上写清谁做了什么、付出了什么。
事情过去后，灶火重新点起，破桶重新箍好，孩子重新敢在路边追跑。
""".strip()


def count_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def normalize_known_traditional(text: str) -> str:
    return (text or "").translate(TRADITIONAL_TO_SIMPLIFIED)


def safe_name(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", title).strip() or "untitled"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_json_reply(reply: str) -> dict:
    raw = (reply or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型审稿未返回JSON对象")
    return json.loads(raw[start:end + 1])


def find_story_plan(plan_data: dict, title: str) -> dict:
    for story in plan_data.get("stories", []):
        if story.get("title") == title:
            return story
    raise KeyError(f"章节事件表中没有《{title}》")


def find_core(title: str) -> dict:
    data = project.load_myth_core_constraints()
    core = dict(data.get("by_title", {}).get(title) or {})
    if not core:
        raise KeyError(f"核心约束中没有《{title}》")
    thread = project.find_thread_protagonist_constraint(title)
    if thread:
        core["_thread_protagonist"] = thread
    return core


def normalize_for_similarity(text: str) -> str:
    text = re.sub(r"\s+", "", text or "")
    text = re.sub(r"[，。！？；：“”‘’、…—,.!?;:'\"()\[\]{}《》〈〉]", "", text)
    return text


def paragraph_similarity_issues(chapters: list[str]) -> list[dict]:
    paragraphs = []
    for chapter_index, chapter in enumerate(chapters, 1):
        for paragraph_index, paragraph in enumerate(re.split(r"\n+", chapter), 1):
            normalized = normalize_for_similarity(paragraph)
            if len(normalized) >= 80:
                paragraphs.append((chapter_index, paragraph_index, normalized))
    issues = []
    for index, left in enumerate(paragraphs):
        for right in paragraphs[index + 1:]:
            if left[0] == right[0]:
                continue
            ratio = difflib.SequenceMatcher(None, left[2], right[2], autojunk=False).ratio()
            if ratio >= 0.72:
                issues.append(
                    {
                        "left_chapter": left[0],
                        "left_paragraph": left[1],
                        "right_chapter": right[0],
                        "right_paragraph": right[1],
                        "ratio": round(ratio, 3),
                    }
                )
    return issues


def repeated_sentence_issues(chapters: list[str]) -> list[dict]:
    locations = defaultdict(list)
    for chapter_index, chapter in enumerate(chapters, 1):
        for sentence in re.split(r"(?<=[。！？])", chapter):
            normalized = normalize_for_similarity(sentence)
            if len(normalized) >= 24:
                locations[normalized].append(chapter_index)
    return [
        {"chapters": sorted(set(chapter_indexes)), "sentence": sentence[:80]}
        for sentence, chapter_indexes in locations.items()
        if len(set(chapter_indexes)) > 1
    ]


def opening_similarity_issues(chapters: list[str]) -> list[dict]:
    openings = [normalize_for_similarity(chapter)[:220] for chapter in chapters]
    issues = []
    for left_index, left in enumerate(openings):
        for right_index in range(left_index + 1, len(openings)):
            right = openings[right_index]
            if min(len(left), len(right)) < 100:
                continue
            ratio = difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()
            if ratio >= 0.48:
                issues.append(
                    {
                        "left_chapter": left_index + 1,
                        "right_chapter": right_index + 1,
                        "ratio": round(ratio, 3),
                    }
                )
    return issues


def hard_term_hits(text: str) -> dict:
    return {
        "prompt_leakage": [term for term in HARD_META_TERMS if term in text],
        "anachronisms": [term for term in ANACHRONISM_TERMS if term in text],
        "lowbrow": [term for term in LOWBROW_TERMS if term in text],
        "administrative": [term for term in ADMIN_TERMS if term in text],
        "graphic_or_technical_body": [
            term for term in GRAPHIC_OR_TECHNICAL_BODY_TERMS if term in text
        ],
        "technical_narration": [term for term in TECHNICAL_NARRATION_TERMS if term in text],
    }


def local_chapter_reasons(
    raw: str,
    candidate: str,
    chapter_plan: dict,
    previous_chapters: list[str],
    minimum_paragraphs: int = 4,
) -> list[str]:
    reasons = []
    length = count_chars(candidate)
    minimum = int(chapter_plan.get("min_chars", 900))
    configured_maximum = int(chapter_plan.get("max_chars", 1250))
    maximum = configured_maximum if minimum_paragraphs < 4 else max(configured_maximum, 1350)
    if length < minimum:
        reasons.append(f"篇幅不足{length}/{minimum}")
    if length > maximum:
        reasons.append(f"篇幅过长{length}/{maximum}")
    hits = hard_term_hits(raw)
    for category, terms in hits.items():
        if terms:
            reasons.append(f"{category}[{','.join(terms[:4])}]")
    if re.search(r"[A-Za-z]{2,}", raw):
        reasons.append("英文污染")
    if project.has_hard_meta_residue(raw):
        reasons.append("元文本残留")
    if re.search(r"[\U0001F300-\U0001FAFF\u0370-\u03FF\u0400-\u052F]", raw):
        reasons.append("异常字符")
    traditional_hits = sorted({char for char in raw if char in TRADITIONAL_POLLUTION_CHARS})
    if traditional_hits:
        reasons.append(f"繁体字污染[{''.join(traditional_hits[:6])}]")
    precise_hits = re.findall(
        r"(?:[二三四五六七八九十百千\d]+)(?:尺|丈|里|步|度|刻|颗|枚|段|簇|处|趟|轮|日|年)",
        raw,
    )
    clock_hits = re.findall(
        r"寅初|卯初|卯时|辰初|辰时|巳正|午前|申牌|酉时|戌末|朔日|三刻|二刻",
        raw,
    )
    date_hits = re.findall(
        r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]年|"
        r"[正一二三四五六七八九十冬腊]月(?:初|廿)?[一二三四五六七八九十]|农历",
        raw,
    )
    precise_limit = 3 if minimum_paragraphs < 4 else 4
    if len(precise_hits) >= precise_limit:
        reasons.append(f"精确计数堆砌{len(precise_hits)}")
    if len(clock_hits) >= 2:
        reasons.append(f"时刻表式叙事{len(clock_hits)}")
    if date_hits:
        reasons.append(f"纪年日期式叙事[{date_hits[0]}]")
    if "→" in raw:
        reasons.append("步骤表残留")
    paragraphs = [item.strip() for item in re.split(r"\n+", candidate) if item.strip()]
    if len(paragraphs) < minimum_paragraphs:
        reasons.append(f"分段不足{len(paragraphs)}/{minimum_paragraphs}")
    if any(count_chars(paragraph) > 520 for paragraph in paragraphs):
        reasons.append("单段过长，疑似动作清单或无停顿灌写")
    if re.search(r"^\s*(?:第[一二三四五六七八]+章|章节|标题)[：:\s]", raw):
        reasons.append("输出章节标题或格式标签")
    if not re.search(r"[。！？！”]$", candidate.strip()):
        reasons.append("结尾句未完成")
    if candidate.count("阿满") > int(chapter_plan.get("aman_max_mentions", 5)):
        reasons.append("阿满出现过量")
    if chapter_plan.get("aman_mode") == "none" and "阿满" in candidate:
        reasons.append("本章不应出现阿满")
    for required in chapter_plan.get("required_terms", []):
        if required and required not in candidate:
            reasons.append(f"缺少本章必要事实[{required}]")
    for forbidden in chapter_plan.get("forbidden_terms", []):
        if forbidden and forbidden in candidate:
            reasons.append(f"提前或错误写入[{forbidden}]")
    if previous_chapters:
        cross_paragraph = paragraph_similarity_issues(previous_chapters + [candidate])
        if any(issue["right_chapter"] == len(previous_chapters) + 1 for issue in cross_paragraph):
            reasons.append("与前章存在高度相似段落")
        cross_sentences = repeated_sentence_issues(previous_chapters + [candidate])
        if any((len(previous_chapters) + 1) in issue["chapters"] for issue in cross_sentences):
            reasons.append("与前章复用完整句子")
    return list(dict.fromkeys(reasons))


def story_state_before(story_plan: dict, chapter_number: int) -> str:
    completed = story_plan.get("chapters", [])[: chapter_number - 1]
    if not completed:
        return story_plan.get("opening_state", "故事尚未开始。")
    return "；".join(
        f"第{item['chapter']}章结束时：{item['result']}"
        for item in completed
    )


def already_completed(story_plan: dict, chapter_number: int) -> list[str]:
    result = []
    for item in story_plan.get("chapters", [])[: chapter_number - 1]:
        result.extend(item.get("core_nodes", []))
        result.append(item.get("goal", ""))
    return [item for item in result if item]


def future_tasks(story_plan: dict, chapter_number: int) -> list[str]:
    return [
        item.get("goal", "")
        for item in story_plan.get("chapters", [])[chapter_number:]
        if item.get("goal")
    ]


def chapter_system_prompt(title: str, story_plan: dict, core: dict) -> str:
    event_chain = "；".join(core.get("event_chain", []))
    forbidden = "、".join(
        list(core.get("forbidden_elements", []) or [])
        + list(story_plan.get("story_specific_forbidden", []) or [])
        + list(HARD_META_TERMS)
        + list(ANACHRONISM_TERMS)
        + list(LOWBROW_TERMS)
        + list(GRAPHIC_OR_TECHNICAL_BODY_TERMS)
        + list(TECHNICAL_NARRATION_TERMS)
    )
    return f"""
你是中文民间神话长篇改写作者。你正在按已经锁定的八章事件表写《{title}》。

原神话不可修改的主线依次为：{event_chain}
本篇长篇动力：{story_plan.get('strategy', '')}

硬规则：
1. 每一章只能完成事件表分配给本章的新任务，已经完成的事件只能以一句必要后果承接，严禁重新演一遍。
2. 每章必须具备“目标—具体阻碍—行动调整—不可逆状态变化”，不能只写议论、景色、路人反应或概括。
3. 经典节点必须在现场动作中真实发生，不能留到末章由阿满总结补齐。
4. 只增加服务主线的准备、试错、选择、代价、关系和余波；不得增加无后续作用的路人、法宝、仙人、怪物、预言或支线。
5. 阿满是男性见闻小史官，只带青竹简、旧笔、小布袋。他只能观察、记录、短促吐槽和提供普通人视角，不能解决危机，不能每章都摔倒、掉笔或护简。
6. 幽默来自人物性格、误会、行动反差和自然对白；严肃、死亡、牺牲、分离章节停止玩笑，不拿受难者和身体作笑料。
7. 古代神话语境稳定，语言朴素清楚。严禁出现：{forbidden}
8. 禁止用时刻表、步骤表、精确尺寸、角度、材料配比、岩石分类、身体结构和
   伤口细节扩字。每章最多偶尔出现一个与情节必要的数目，不得列清单。
   人物遇难只写“被浪卷走、没有再浮上来、岸上等待”等外部结果；禁止血、皮、骨、
   伤口、生理反应。精卫只能以白喙衔木石飞行后投下，不写用爪搬运、吞咽材料、
   脚走入水或身体机理。
9. 每章写成六到十个自然段，单段不要过长。过程要靠选择、动作受阻、人物
   反应和直接后果变长，不靠技术说明与华丽长句。
10. 只输出本章正文，不得输出标题、章名、提纲、说明、字数、审稿意见或Markdown。

文风基准（只学朴素短句、动作和苦中带笑，不复制事件）：
{STYLE_BASELINE}
""".strip()


def chapter_user_prompt(
    title: str,
    story_plan: dict,
    chapter_plan: dict,
    prior_chapters: list[str],
    rewrite_source: str = "",
    revision_issues: list[str] | None = None,
    desired_min: int | None = None,
) -> str:
    chapter_number = int(chapter_plan["chapter"])
    completed = already_completed(story_plan, chapter_number)
    future = future_tasks(story_plan, chapter_number)
    previous_tail = prior_chapters[-1][-500:] if prior_chapters else "无，这是全文开篇。"
    humor_mode = {
        "none": "本章不出现阿满，不安排喜剧；保持庄重或专注。",
        "light": "阿满可出现一次，最多形成一组短促笑点，随后退回旁观位置。",
        "moderate": "阿满可出现一到两次，最多两组不同类型的短促笑点；至少一组笑点应由核心人物或情境承担。",
    }.get(chapter_plan.get("aman_mode", "light"), "阿满只作轻度旁观。")
    rewrite_block = ""
    if rewrite_source:
        rewrite_block = f"""
这是本章上一版正文，只允许重写本章，不得修改其他章：
<旧章>
{rewrite_source}
</旧章>
必须解决的问题：{'；'.join(revision_issues or [])}
保留本章原定结果，不新增下一章事件。
"""
    minimum = desired_min or int(chapter_plan.get("target_min", 950))
    maximum = int(chapter_plan.get("target_max", 1100))
    # Qwen 的“字数”自报与本地中文字符计数长期存在明显偏差：提示 1000 字时，
    # 实际常只返回约 500 个中文字符。这里校准的是模型侧目标，不降低本地验收门槛。
    model_minimum = max(1300, minimum + 350)
    model_maximum = max(model_minimum + 200, maximum + 400)
    return f"""
《{title}》第{chapter_number}/8章。为抵消平台字数统计偏差，请一次写足
{model_minimum}—{model_maximum}个汉字；本地仍会按完整章节严格验收，不能用复述、
排比、总结或新支线凑长。

开章前的确定状态：{story_state_before(story_plan, chapter_number)}
前章最后一小段：{previous_tail}
已经现场演完、严禁重演：{'；'.join(completed) if completed else '无'}

本章叙事功能：{chapter_plan.get('function', '')}
本章明确目标：{chapter_plan.get('goal', '')}
具体阻碍：{chapter_plan.get('obstacle', '')}
行动调整：{chapter_plan.get('adjustment', '')}
本章必须在现场写出的经典节点：{'；'.join(chapter_plan.get('core_nodes', [])) or '本章只做主线准备'}
本章正文必须逐字出现这些必要称谓或事实词：{'、'.join(chapter_plan.get('required_terms', [])) or '无额外词项'}
章末必须形成的新状态：{chapter_plan.get('result', '')}
阿满与幽默限额：{humor_mode}

后续尚未发生、绝对不得提前：{'；'.join(future) if future else '无；本章完成结局与具体余波'}
本章禁写：{'；'.join(chapter_plan.get('forbidden_terms', [])) or '不得重启故事、不得总结未演事件'}
{rewrite_block}
直接写连续小说正文。开头必须承接当前状态，不得重新介绍世界、人物或故事起因；结尾要用动作或处境变化落地，不写作文式总结。
""".strip()


def scene_user_prompt(
    title: str,
    story_plan: dict,
    chapter_plan: dict,
    prior_chapters: list[str],
    scene_texts: list[str],
    scene_number: int,
) -> str:
    chapter_number = int(chapter_plan["chapter"])
    previous_tail = (
        scene_texts[-1][-420:]
        if scene_texts
        else (prior_chapters[-1][-420:] if prior_chapters else "无，这是全文开篇。")
    )
    completed = already_completed(story_plan, chapter_number)
    future = future_tasks(story_plan, chapter_number)
    if scene_number == 1:
        scene_task = (
            f"只写本章目标如何变得迫切，以及人物面对的具体阻碍："
            f"{chapter_plan.get('goal', '')}；{chapter_plan.get('obstacle', '')}。"
            "场末让人物作出下一步选择，但不要执行完调整，也不要写本章最终结果。"
        )
        aman_rule = (
            "若本章允许阿满，他只能在本场出现一次，形成一组短促笑点后退到背景。"
            if chapter_plan.get("aman_mode") != "none"
            else "本场不出现阿满，不安排喜剧。"
        )
    else:
        scene_task = (
            f"承接上一场，只写人物如何调整行动并亲手得到本章结果："
            f"{chapter_plan.get('adjustment', '')}；{chapter_plan.get('result', '')}。"
            f"必须在现场演出的经典节点：{'；'.join(chapter_plan.get('core_nodes', [])) or '无额外经典节点'}。"
        )
        aman_rule = (
            "除非章末记录是本章结果不可缺少，否则本场不再增加阿满笑点。"
            if chapter_plan.get("aman_mode") != "none"
            else "本场不出现阿满，不安排喜剧。"
        )
    return f"""
《{title}》第{chapter_number}/8章的第{scene_number}/2个连续场景。
请写900—1100个汉字；接口实际输出会偏短，但不得用排比、复述、技术说明或新支线凑长。

开场前确定状态：{story_state_before(story_plan, chapter_number)}
紧接前文：{previous_tail}
已经演完、严禁重演：{'；'.join(completed) if completed else '无'}

本场唯一任务：{scene_task}
阿满限额：{aman_rule}
本章必要称谓：{'、'.join(chapter_plan.get('required_terms', [])) or '无'}
后续尚未发生：{'；'.join(future) if future else '无'}
禁写：{'；'.join(chapter_plan.get('forbidden_terms', [])) or '不得重启故事或总结未演事件'}

只输出两到四个自然段的小说正文。用朴素动作、自然对白、选择和直接后果推进；
不用尺寸、角度、时辰表、材料清单、岩石分类、身体机理、伤口细节或作文式议论。
若本场涉及遇难，只写浪卷走、没有再浮上来与岸上等待，绝不写血、皮、骨、伤口或生理反应。
若本场涉及精卫搬运，只写它用白喙衔起木石、飞向海面、松喙投下；绝不写爪搬、
吞咽、脚走入水、身体承压或任何类似操作说明的过程。
""".strip()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_chapter(
    title: str,
    story_plan: dict,
    core: dict,
    chapter_plan: dict,
    prior_chapters: list[str],
    work_dir: Path,
    resume: bool,
) -> tuple[str, dict]:
    chapter_number = int(chapter_plan["chapter"])
    plan_hash = hashlib.sha256(
        json.dumps(chapter_plan, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    chapter_path = work_dir / "chapters" / f"{chapter_number:02d}.txt"
    metadata_path = work_dir / "chapters" / f"{chapter_number:02d}.json"
    if resume and chapter_path.exists() and metadata_path.exists():
        metadata = load_json(metadata_path)
        candidate = chapter_path.read_text(encoding="utf-8").strip()
        same_generation_context = (
            metadata.get("manual_revision") is True
            or (
                metadata.get("plan_hash") == plan_hash
                and metadata.get("model") == project.qwen_generation_model()
            )
        )
        if same_generation_context:
            reasons = local_chapter_reasons(candidate, candidate, chapter_plan, prior_chapters)
            if not reasons:
                print(f"  复用第{chapter_number}章：{count_chars(candidate)}字")
                return candidate, metadata

    system_prompt = chapter_system_prompt(title, story_plan, core)
    attempts = []
    scene_texts = []
    rejected_dir = work_dir / "rejected_attempts"
    rejected_dir.mkdir(parents=True, exist_ok=True)
    for scene_number in (1, 2):
        accepted_scene = ""
        for attempt, temperature in enumerate((0.48, 0.36, 0.26, 0.18), 1):
            print(f"  生成第{chapter_number}/8章场景{scene_number}/2，第{attempt}次...")
            user_prompt = scene_user_prompt(
                title,
                story_plan,
                chapter_plan,
                prior_chapters,
                scene_texts,
                scene_number,
            )
            raw = project.call_qianwen_api(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                top_p=0.76,
                repetition_penalty=1.24,
                max_retries=3,
                max_tokens=1700,
            )
            normalized_raw = normalize_known_traditional(raw or "")
            candidate = project.clean_markdown(normalized_raw).strip()
            candidate = project.split_long_paragraphs(
                candidate, max_paragraph_len=330, soft_paragraph_len=220
            )
            scene_plan = dict(chapter_plan)
            scene_plan["required_terms"] = []
            scene_plan["min_chars"] = 430
            scene_plan["max_chars"] = 720
            scene_plan["aman_max_mentions"] = 3
            if scene_number == 2 and chapter_plan.get("aman_mode") != "none":
                scene_plan["aman_mode"] = "light"
            context = prior_chapters + scene_texts
            reasons = local_chapter_reasons(
                normalized_raw,
                candidate,
                scene_plan,
                context,
                minimum_paragraphs=2,
            )
            (rejected_dir / f"{chapter_number:02d}_s{scene_number}_{attempt:02d}_raw.txt").write_text(
                raw or "", encoding="utf-8"
            )
            (rejected_dir / f"{chapter_number:02d}_s{scene_number}_{attempt:02d}_clean.txt").write_text(
                candidate, encoding="utf-8"
            )
            attempt_record = {
                "scene": scene_number,
                "attempt": attempt,
                "temperature": temperature,
                "length": count_chars(candidate),
                "reasons": reasons,
            }
            attempts.append(attempt_record)
            if reasons:
                print(f"    场景退回：{'；'.join(reasons)}")
                continue
            accepted_scene = candidate
            break
        if not accepted_scene:
            raise RuntimeError(f"《{title}》第{chapter_number}章场景{scene_number}连续生成失败")
        scene_texts.append(accepted_scene)

    candidate = "\n\n".join(scene_texts).strip()
    reasons = local_chapter_reasons(
        candidate, candidate, chapter_plan, prior_chapters, minimum_paragraphs=4
    )
    if reasons:
        raise RuntimeError(
            f"《{title}》第{chapter_number}章两场合并未通过：{'；'.join(reasons)}"
        )
    metadata = {
        "title": title,
        "chapter": chapter_number,
        "plan_hash": plan_hash,
        "model": project.qwen_generation_model(),
        "generation_mode": "two_causal_scenes",
        "length": count_chars(candidate),
        "attempts": attempts,
    }
    chapter_path.parent.mkdir(parents=True, exist_ok=True)
    chapter_path.write_text(candidate, encoding="utf-8")
    write_json(metadata_path, metadata)
    return candidate, metadata


def rewrite_chapter(
    title: str,
    story_plan: dict,
    core: dict,
    chapter_plan: dict,
    chapters: list[str],
    chapter_index: int,
    issues: list[str],
    desired_min: int | None = None,
) -> tuple[str, dict]:
    prior = chapters[:chapter_index]
    original = chapters[chapter_index]
    system_prompt = chapter_system_prompt(title, story_plan, core)
    attempts = []
    for attempt, temperature in enumerate((0.38, 0.26, 0.18), 1):
        print(f"  定向重写第{chapter_index + 1}章，第{attempt}次：{'；'.join(issues)}")
        user_prompt = chapter_user_prompt(
            title,
            story_plan,
            chapter_plan,
            prior,
            rewrite_source=original,
            revision_issues=issues,
            desired_min=desired_min,
        )
        raw = project.call_qianwen_api(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            top_p=0.72,
            repetition_penalty=1.25,
            max_retries=3,
            max_tokens=2800,
        )
        normalized_raw = normalize_known_traditional(raw or "")
        candidate = project.clean_markdown(normalized_raw).strip()
        candidate = project.split_long_paragraphs(
            candidate, max_paragraph_len=420, soft_paragraph_len=260
        )
        local_plan = dict(chapter_plan)
        if desired_min:
            local_plan["min_chars"] = desired_min
            local_plan["max_chars"] = max(int(local_plan.get("max_chars", 1250)), desired_min + 220)
        reasons = local_chapter_reasons(normalized_raw, candidate, local_plan, prior)
        attempts.append({"attempt": attempt, "length": count_chars(candidate), "reasons": reasons})
        if not reasons:
            return candidate, {"attempts": attempts, "issues": issues}
        print(f"    重写仍退回：{'；'.join(reasons)}")
    return original, {"attempts": attempts, "issues": issues, "kept_original": True}


def local_story_audit(title: str, chapters: list[str], story_plan: dict, core: dict) -> dict:
    text = "\n\n".join(chapters).strip()
    hits = hard_term_hits(text)
    report = {
        "title": title,
        "chapter_lengths": [count_chars(chapter) for chapter in chapters],
        "length": count_chars(text),
        "chapter_count": len(chapters),
        "prompt_leakage": hits["prompt_leakage"],
        "anachronisms": hits["anachronisms"],
        "lowbrow": hits["lowbrow"],
        "administrative": hits["administrative"],
        "graphic_or_technical_body": hits["graphic_or_technical_body"],
        "technical_narration": hits["technical_narration"],
        "latin_fragments": re.findall(r"[A-Za-z]{2,}", text),
        "quote_balance": {"open": text.count("“"), "close": text.count("”")},
        "near_duplicate_paragraphs": paragraph_similarity_issues(chapters),
        "repeated_sentences": repeated_sentence_issues(chapters),
        "similar_openings": opening_similarity_issues(chapters),
        "aman_mentions": text.count("阿满"),
        "core_sequence_met": project.myth_core_required_sequence_met(text, core),
        "core_required_met": project.myth_core_requirement_met(text, core, final=True),
        "thread_role_violation": project.contains_thread_protagonist_violation(text, core),
    }
    report["hard_failures"] = []
    if not 7500 <= report["length"] <= 8850:
        report["hard_failures"].append(f"总字数不在7500—8850：{report['length']}")
    if len(chapters) != 8:
        report["hard_failures"].append("不是完整八章")
    for key in (
        "prompt_leakage",
        "anachronisms",
        "lowbrow",
        "administrative",
        "graphic_or_technical_body",
        "technical_narration",
        "latin_fragments",
    ):
        if report[key]:
            report["hard_failures"].append(f"{key}:{report[key][:5]}")
    if report["quote_balance"]["open"] != report["quote_balance"]["close"]:
        report["hard_failures"].append("中文引号不配对")
    if report["near_duplicate_paragraphs"]:
        report["hard_failures"].append("跨章高度相似段落")
    if report["repeated_sentences"]:
        report["hard_failures"].append("跨章重复完整句子")
    if report["similar_openings"]:
        report["hard_failures"].append("章节开头结构高度相似")
    # 旧校验器依赖逐字关键词，例如正文写“衔着木石”会因没有连续出现
    # “衔木石”而误判。保留结果供对照，但是否真实演出节点交给下方全文
    # 结构化审稿，以免再次把“结尾堆关键词”当成合格。
    if report["thread_role_violation"]:
        report["hard_failures"].append("阿满越权或设定违规")
    return report


def qwen_structural_audit(title: str, text: str, story_plan: dict, core: dict) -> dict:
    classic_nodes = core.get("event_chain", [])
    chapter_contracts = [
        {
            "chapter": item["chapter"],
            "goal": item["goal"],
            "result": item["result"],
            "core_nodes": item.get("core_nodes", []),
        }
        for item in story_plan.get("chapters", [])
    ]
    prompt = f"""
你是严格的神话长篇退稿编辑。审查《{title}》全文。不要因为字数够、关键词出现或文笔流畅就放行。

不可修改的经典节点：
{json.dumps(classic_nodes, ensure_ascii=False)}

八章推进合同：
{json.dumps(chapter_contracts, ensure_ascii=False)}

必须逐项检查：
1. 每个经典节点是否在正文现场完整演出。只在结尾总结中提到，状态必须是summary_only，不能算present。
2. 八章是否各自产生新的目标、阻碍、行动调整和结果；是否有任何一章重新开场或重演前章。
3. 是否有同一事件换措辞重复、草稿拼接、提示词、现代词、低俗笑点、异常人物或设定漂移。
   任何骨骼肌肉、流血伤口、身体被穿透、缺氧过程等细写，都列入
   graphic_injury_or_body_detail。任何尺寸、时辰、角度、地质分类、材料清单、
   身体机理或操作步骤式扩写，都列入technical_or_precision_padding。
4. 阿满是否只轻度旁观，是否反复摔倒、掉笔、护简、嘴硬，是否盖过神话人物。
5. 结尾是否现场完成经典结局并写具体余波，而非作文式总结补题。

只输出一个JSON对象，严格使用：
{{
  "classic_nodes": [{{"node":"", "status":"present|summary_only|missing", "evidence":"", "chapter":1}}],
  "chapter_progress": [{{"chapter":1, "goal_new":true, "obstacle_concrete":true, "adjustment_present":true, "state_changed":true, "issue":""}}],
  "repeated_events": [{{"event":"", "chapters":[1,2], "explanation":""}}],
  "prompt_leakage": [],
  "anachronisms": [],
  "graphic_injury_or_body_detail": [],
  "technical_or_precision_padding": [],
  "lowbrow_humor": [],
  "setting_or_character_drift": [],
  "aman_violations": [],
  "unfinished_or_spliced_sentences": [],
  "ending_completed_in_scene": true,
  "scores": {{
    "classic_nodes": 25,
    "causal_coherence": 20,
    "eight_chapter_progress": 15,
    "character_arc": 10,
    "no_repeated_splicing": 10,
    "clean_period_language": 10,
    "sentence_quality": 5,
    "length": 5,
    "total": 100
  }},
  "chapter_issues": [{{"chapter":1, "issues":[""]}}],
  "decision": "pass|reject"
}}

硬标准：任一经典节点summary_only/missing、任一重复事件、提示词、现代违和词、拼接断句、结尾未现场完成，都必须reject。总分低于80必须reject。

全文：
<正文>
{text}
</正文>
""".strip()
    reply = project.call_qianwen_api(
        [
            {
                "role": "system",
                "content": "只做严格结构化审稿，只返回合法JSON；不要续写、润色或替作品找理由。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.05,
        top_p=0.5,
        repetition_penalty=1.05,
        max_retries=3,
        max_tokens=4200,
    )
    try:
        result = parse_json_reply(reply or "")
    except (ValueError, json.JSONDecodeError) as first_error:
        # Qwen occasionally returns a semantically complete audit with one missing
        # comma or an unescaped quote inside evidence. Do not discard the audit or
        # regenerate the story: ask a separate, zero-creativity pass to repair JSON
        # syntax only. The repaired object is still subjected to every hard gate
        # below, so this cannot turn a rejection into a pass by itself.
        repair_error = first_error
        result = None
        for repair_attempt in range(1, 3):
            print(f"  审稿JSON语法损坏，进行第{repair_attempt}/2次纯语法修复...")
            repaired_reply = project.call_qianwen_api(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是JSON语法修复器。只修复下面对象的逗号、引号、括号和转义，"
                            "不得删改、概括、重评或新增任何审稿内容。只返回合法JSON对象。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "请仅修复以下审稿JSON的语法：\n<待修复>\n"
                            f"{reply or ''}\n</待修复>"
                        ),
                    },
                ],
                temperature=0.0,
                top_p=0.2,
                repetition_penalty=1.0,
                max_retries=2,
                max_tokens=5000,
            )
            try:
                result = parse_json_reply(repaired_reply or "")
                break
            except (ValueError, json.JSONDecodeError) as exc:
                repair_error = exc
        if result is None:
            raise ValueError(f"模型审稿JSON连续修复失败：{repair_error}") from first_error
    hard = []
    for node in result.get("classic_nodes", []):
        if node.get("status") != "present":
            hard.append(f"经典节点未现场完成:{node.get('node')}[{node.get('status')}]")
    for key in (
        "repeated_events",
        "prompt_leakage",
        "anachronisms",
        "graphic_injury_or_body_detail",
        "technical_or_precision_padding",
        "lowbrow_humor",
        "setting_or_character_drift",
        "unfinished_or_spliced_sentences",
    ):
        if result.get(key):
            hard.append(f"{key}:{result.get(key)}")
    if not result.get("ending_completed_in_scene", False):
        hard.append("结尾未在现场完成")
    total = int((result.get("scores") or {}).get("total", 0) or 0)
    if total < 80:
        hard.append(f"总分不足80:{total}")
    if result.get("decision") != "pass":
        hard.append("审稿决定为reject")
    result["hard_failures"] = hard
    result["pass"] = not hard
    return result


def collect_revision_issues(audit: dict, story_plan: dict) -> dict[int, list[str]]:
    grouped = defaultdict(list)
    for item in audit.get("chapter_issues", []):
        try:
            chapter = int(item.get("chapter"))
        except (TypeError, ValueError):
            continue
        issues = [str(issue) for issue in item.get("issues", []) if str(issue).strip()]
        if 1 <= chapter <= 8 and issues:
            grouped[chapter].extend(issues)
    for node in audit.get("classic_nodes", []):
        if node.get("status") == "present":
            continue
        try:
            chapter = int(node.get("chapter"))
        except (TypeError, ValueError):
            chapter = 0
        if not 1 <= chapter <= 8:
            for chapter_plan in story_plan.get("chapters", []):
                if node.get("node") in chapter_plan.get("core_nodes", []):
                    chapter = int(chapter_plan["chapter"])
                    break
        if 1 <= chapter <= 8:
            grouped[chapter].append(f"必须把经典节点“{node.get('node')}”在现场完整演出，不能只概括")
    for repeated in audit.get("repeated_events", []):
        chapters = repeated.get("chapters", [])
        for chapter in chapters[1:]:
            try:
                chapter = int(chapter)
            except (TypeError, ValueError):
                continue
            if 1 <= chapter <= 8:
                grouped[chapter].append(f"删除对已发生事件“{repeated.get('event')}”的重演，只写本章新任务")
    return {chapter: list(dict.fromkeys(issues)) for chapter, issues in grouped.items()}


def ensure_target_length(
    title: str,
    story_plan: dict,
    core: dict,
    chapters: list[str],
    revision_log: list[dict],
) -> list[str]:
    total = count_chars("\n\n".join(chapters))
    attempts = 0
    while total < 7500 and attempts < 4:
        attempts += 1
        candidates = [
            (count_chars(chapter), index)
            for index, chapter in enumerate(chapters)
            if count_chars(chapter) < 1180
            and story_plan["chapters"][index].get("expandable", True)
        ]
        if not candidates:
            break
        _, index = min(candidates)
        need = min(180, 7500 - total + 40)
        desired = min(1180, count_chars(chapters[index]) + need)
        issues = [
            "篇幅不足，不能在结尾追加总结；请在本章内部扩充与主线直接相关的动作准备、阻碍升级、人物选择及直接后果",
            f"本章重写后至少{desired}字，原定章末状态保持不变",
        ]
        rewritten, log = rewrite_chapter(
            title,
            story_plan,
            core,
            story_plan["chapters"][index],
            chapters,
            index,
            issues,
            desired_min=desired,
        )
        chapters[index] = rewritten
        revision_log.append({"kind": "length", "chapter": index + 1, **log})
        total = count_chars("\n\n".join(chapters))
    return chapters


def rebuild_story(
    title: str,
    plan_data: dict,
    output_dir: Path,
    resume: bool,
    max_revision_rounds: int,
    promote: bool,
    reuse_passed_audit: bool,
) -> dict:
    story_plan = find_story_plan(plan_data, title)
    core = find_core(title)
    work_dir = output_dir / "work" / safe_name(title)
    work_dir.mkdir(parents=True, exist_ok=True)
    write_json(work_dir / "outline.json", story_plan)
    chapters = []
    chapter_logs = []
    for chapter_plan in story_plan.get("chapters", []):
        chapter, metadata = generate_chapter(
            title,
            story_plan,
            core,
            chapter_plan,
            chapters,
            work_dir,
            resume,
        )
        chapters.append(chapter)
        chapter_logs.append(metadata)

    revision_log = []
    chapters = ensure_target_length(title, story_plan, core, chapters, revision_log)
    local = local_story_audit(title, chapters, story_plan, core)
    qwen = {}
    report_path = output_dir / "reports" / f"{safe_name(title)}.json"
    initial_text = "\n\n".join(chapters).strip()
    initial_content_sha256 = hashlib.sha256(initial_text.encode("utf-8")).hexdigest()
    for round_index in range(max_revision_rounds + 1):
        text = "\n\n".join(chapters).strip()
        local = local_story_audit(title, chapters, story_plan, core)
        if reuse_passed_audit and round_index == 0 and report_path.exists():
            cached_report = load_json(report_path)
            cached_qwen = cached_report.get("qwen_audit") or {}
            same_content = cached_report.get("content_sha256") == initial_content_sha256
            cached_local_clean = not (
                (cached_report.get("local_audit") or {}).get("hard_failures")
            )
            reusable_for_promotion = bool(promote and cached_qwen and cached_local_clean)
            if same_content and (
                cached_qwen.get("pass") is True or reusable_for_promotion
            ):
                qwen = cached_qwen
                print(
                    f"  复用同一正文的既有Qwen结构审稿："
                    f"pass={bool(qwen.get('pass'))} "
                    f"score={(qwen.get('scores') or {}).get('total', 0)}"
                )
                break
        if local["hard_failures"]:
            print(f"  本地整篇审计未通过：{'；'.join(local['hard_failures'])}")
        qwen = qwen_structural_audit(title, text, story_plan, core)
        print(
            f"  Qwen结构审稿：pass={qwen['pass']} "
            f"score={(qwen.get('scores') or {}).get('total', 0)} "
            f"hard={qwen.get('hard_failures', [])}"
        )
        if not local["hard_failures"] and qwen["pass"]:
            break
        if round_index >= max_revision_rounds:
            break
        grouped = collect_revision_issues(qwen, story_plan)
        if local["similar_openings"]:
            for issue in local["similar_openings"]:
                grouped.setdefault(issue["right_chapter"], []).append(
                    "本章开头与前章结构过近，直接从新的动作现场承接，禁止重新介绍人物和背景"
                )
        if local["near_duplicate_paragraphs"] or local["repeated_sentences"]:
            for issue in local["near_duplicate_paragraphs"]:
                grouped.setdefault(issue["right_chapter"], []).append(
                    "删除与前章高度相似的段落，改写为本章独有的阻碍、调整和结果"
                )
            for issue in local["repeated_sentences"]:
                for chapter in issue["chapters"][1:]:
                    grouped.setdefault(chapter, []).append("删除跨章复用的原句")
        if local["thread_role_violation"]:
            external_terms = project.thread_protagonist_external_terms(core)
            for index, chapter_text in enumerate(chapters, 1):
                hits = [term for term in external_terms if term and term in chapter_text]
                if hits:
                    grouped.setdefault(index, []).append(
                        f"删除不属于本篇的跨故事比较或点名：{'、'.join(hits)}；当前章只写《{title}》现场"
                    )
        if not grouped:
            break
        for chapter_number in sorted(grouped):
            index = chapter_number - 1
            rewritten, log = rewrite_chapter(
                title,
                story_plan,
                core,
                story_plan["chapters"][index],
                chapters,
                index,
                list(dict.fromkeys(grouped[chapter_number])),
            )
            chapters[index] = rewritten
            revision_log.append(
                {"kind": "quality", "round": round_index + 1, "chapter": chapter_number, **log}
            )
        chapters = ensure_target_length(title, story_plan, core, chapters, revision_log)

    text = "\n\n".join(chapters).strip()
    local = local_story_audit(title, chapters, story_plan, core)
    local_passed = not local["hard_failures"]
    qwen_passed = bool(qwen.get("pass"))
    automated_passed = local_passed and qwen_passed
    human_override = bool(promote and local_passed and not qwen_passed)
    accepted = automated_passed or human_override
    status = (
        "promoted_after_human_review"
        if accepted and promote
        else ("awaiting_human_review" if automated_passed else "rejected_by_automated_gates")
    )
    report = {
        "title": title,
        "passed": accepted,
        "automated_passed": automated_passed,
        "human_override_of_qwen_advisory": human_override,
        "promoted": bool(accepted and promote),
        "status": status,
        "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "plan_version": plan_data.get("version"),
        "model": project.qwen_generation_model(),
        "local_audit": local,
        "qwen_audit": qwen,
        "chapter_generation": chapter_logs,
        "revision_log": revision_log,
    }
    write_json(report_path, report)
    for index, chapter in enumerate(chapters, 1):
        chapter_path = work_dir / "chapters" / f"{index:02d}.txt"
        chapter_path.parent.mkdir(parents=True, exist_ok=True)
        chapter_path.write_text(chapter, encoding="utf-8")
    if accepted:
        candidate_path = work_dir / "automated_gate_candidate.txt"
        candidate_path.write_text(text, encoding="utf-8")
        if promote:
            text_path = output_dir / "texts" / f"{safe_name(title)}.txt"
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(text, encoding="utf-8")
            print(f"《{title}》经人工确认后写入成稿：{local['length']}字")
        else:
            print(
                f"《{title}》通过自动门槛，候选保留在work目录；"
                "人工通读确认后才可使用--promote进入成稿目录。"
            )
    else:
        candidate_path = work_dir / "rejected_candidate.txt"
        candidate_path.write_text(text, encoding="utf-8")
        print(f"《{title}》未通过，候选仅保留在work目录，不进入成稿目录。")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按八章事件表逐篇重制不合格神话")
    parser.add_argument("--stories", nargs="+", required=True, help="本次逐篇重制的故事名")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--resume", action="store_true", help="复用计划哈希一致且仍通过本地门槛的章节")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="仅在人工通读当前候选后使用；把通过自动门槛的全文写入成稿目录",
    )
    parser.add_argument(
        "--reuse-passed-audit",
        action="store_true",
        help=(
            "正文哈希未变化时复用既有审稿；自动流程只复用通过稿，"
            "人工--promote时也可复用本地硬审干净的完整退稿意见"
        ),
    )
    parser.add_argument("--max-revision-rounds", type=int, default=2)
    parser.add_argument("--api-transport", choices=("auto", "sdk", "curl"), default="curl")
    parser.add_argument("--curl-interface", default="")
    parser.add_argument("--curl-resolve-ip", default="")
    parser.add_argument("--api-timeout", type=int, default=120)
    parser.add_argument("--api-retries", type=int, default=3)
    parser.add_argument("--model", default="", help="覆盖Qwen模型，例如qwen3-max")
    return parser.parse_args()


def main_cli() -> int:
    args = parse_args()
    os.environ["QWEN_API_TRANSPORT"] = args.api_transport
    os.environ["QWEN_API_TIMEOUT_SECONDS"] = str(args.api_timeout)
    os.environ["QWEN_API_MAX_RETRIES"] = str(args.api_retries)
    if args.curl_interface:
        os.environ["QWEN_CURL_INTERFACE"] = args.curl_interface
    if args.curl_resolve_ip:
        os.environ["QWEN_CURL_RESOLVE_IP"] = args.curl_resolve_ip
    if args.model:
        os.environ["QWEN_GENERATION_MODEL"] = args.model
    plan_data = load_json(args.plan)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for title in args.stories:
        if title in DIRECTLY_ACCEPTED:
            print(f"跳过《{title}》：该篇属于人工审查直接保留稿。")
            continue
        print(f"\n开始逐篇重制《{title}》")
        try:
            reports.append(
                rebuild_story(
                    title,
                    plan_data,
                    output_dir,
                    args.resume,
                    max(0, args.max_revision_rounds),
                    args.promote,
                    args.reuse_passed_audit,
                )
            )
        except Exception as exc:
            print(f"《{title}》重制异常：{exc}", file=sys.stderr)
            reports.append({"title": title, "passed": False, "error": str(exc)})
    batch_summary = {
        "total": len(reports),
        "passed": sum(1 for report in reports if report.get("passed")),
        "failed_titles": [report.get("title") for report in reports if not report.get("passed")],
        "reports": reports,
    }
    write_json(output_dir / "rebuild_batch_summary.json", batch_summary)
    return 0 if reports and batch_summary["passed"] == len(reports) else 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
