"""把已人工认可的二十篇神话正文定点扩充到约一万字。

本脚本以逐篇重制版 texts 为唯一母稿，按连续区块扩写，保留经典事件、
人物归属和阿满串线设定。过程稿写入 work，只有完整篇幅与本地硬门槛
通过后才写入新目录的 texts。Qwen 调用失败或额度耗尽时可自动回退 Groq。
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE_DIR = BASE_DIR / "outputs" / "20个神话故事（逐篇重制版）" / "texts"
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs" / "20个神话故事扩充最终版"
DEFAULT_CORE_PATH = BASE_DIR / "knowledgeBase" / "myth_core_constraints_revised.json"
DEFAULT_THREAD_PATH = BASE_DIR / "knowledgeBase" / "myth_thread_protagonist_constraints.json"

TARGET_TOTAL = 10600
GENERATION_TOTAL = 10600
MIN_TOTAL = 10300
MAX_TOTAL = None
DEFAULT_BLOCKS = 4

META_TERMS = (
    "根据要求", "根据指令", "本段任务", "扩写说明", "字数要求", "目标字数",
    "前文末尾", "后文开头", "作为AI", "以下正文", "修改稿",
)

TECHNICAL_OR_MODERN_TERMS = (
    "科学", "热胀冷缩", "受热膨胀", "冷敷法", "技术", "原理", "数据", "系统",
    "流程", "项目", "任务指标", "精确", "角度", "材料清单", "身体机理",
    "血管", "骨骼", "缺氧", "概率", "效率", "公里", "分钟", "小时",
)

CURATED_REVERT_BLOCKS = {
    "嫦娥奔月": {2},
    "精卫填海": {3},
    "梁山伯与祝英台": {4},
}

CURATED_TEXT_REPLACEMENTS = {
    "‘硬核’小子": "有担当的硬骨头",
    "当海王": "当浪头将军",
    "部落里最爱搬弄是非的少年": "不受凡间年代限制的瑶池见闻小史官",
    "超级探测器": "一双能看穿柜门的眼睛",
    "王者的镇定": "沉着镇定",
    "小尺子": "布尺",
    "细细测量": "细细比量",
    "测量": "比量",
    "无声的测试": "无声的试探",
    "记录本": "青竹简",
    "纸面上": "简面上",
    "纸面": "简面",
    "纸页": "简页",
    "纸上": "简上",
    "一张纸": "一片简",
    "掏出一张青竹简": "取出一片青竹简",
    "给自己加油": "给自己鼓劲",
    "在给太阳加油": "在给太阳添柴",
    "激昂的交响": "激昂的合鸣",
}


def count_chars(text: str) -> int:
    """Count Chinese characters only, excluding punctuation, Latin text and whitespace."""
    return len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text or ""))


def safe_name(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", title).strip() or "untitled"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_reply(reply: str) -> str:
    text = re.sub(r"<think>[\s\S]*?</think>", "", reply or "", flags=re.I).strip()
    text = re.sub(r"^```(?:text|markdown)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()
    text = re.sub(r"^（?扩写(?:后)?(?:正文|稿)?）?[：:]?\s*", "", text)
    return text.strip()


def split_into_blocks(text: str, block_count: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) < block_count:
        raise ValueError(f"正文只有{len(paragraphs)}个自然段，无法拆成{block_count}个连续区块")
    total = sum(count_chars(part) for part in paragraphs)
    targets = [total * index / block_count for index in range(1, block_count)]
    blocks: list[list[str]] = [[]]
    running = 0
    target_index = 0
    for paragraph in paragraphs:
        length = count_chars(paragraph)
        if (
            target_index < len(targets)
            and running >= targets[target_index]
            and len(blocks[-1]) >= 2
        ):
            blocks.append([])
            target_index += 1
        blocks[-1].append(paragraph)
        running += length
    while len(blocks) < block_count:
        largest = max(range(len(blocks)), key=lambda index: len(blocks[index]))
        group = blocks.pop(largest)
        middle = len(group) // 2
        blocks[largest:largest] = [group[:middle], group[middle:]]
    return ["\n\n".join(group).strip() for group in blocks]


def find_story(data: dict, title: str) -> dict:
    for item in data.get("stories", []):
        if item.get("title") == title or title in item.get("aliases", []):
            return item
    raise KeyError(f"约束文件中没有《{title}》")


def compact_constraints(core: dict, thread: dict) -> dict:
    return {
        "核心事件链": core.get("event_chain", []),
        "必须保留": core.get("must_include", []),
        "不得改变": core.get("must_not_change", []),
        "禁止元素": core.get("forbidden_elements", []),
        "扩写方向": core.get("expansion_guidance", ""),
        "阿满定位": thread.get("role_in_story", thread.get("role", "")),
        "阿满必须": thread.get("must_include", []),
        "阿满禁区": thread.get("forbidden_actions", thread.get("must_not", [])),
        "幽默方向": thread.get("humor_guidance", thread.get("humor", "")),
    }


def is_qwen_error(reply: str) -> bool:
    lowered = (reply or "").lower()
    markers = (
        "调用通义千问 api", "通义千问 api http", "invalid format", "error code",
        "quota", "rate limit", "insufficient", "allocation", "余额", "额度",
        "限流", "无效格式",
    )
    return not reply or any(marker in lowered for marker in markers)


def call_groq(messages: list[dict], *, temperature: float, max_tokens: int) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Qwen不可用，且环境变量 GROQ_API_KEY 未设置")
    model = os.getenv("GROQ_GENERATION_MODEL", "qwen/qwen3.6-27b").strip()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.82,
        "max_completion_tokens": max_tokens,
    }
    if model.startswith("openai/gpt-oss"):
        payload.update({"reasoning_effort": "low", "include_reasoning": False})
    elif model.startswith("qwen/"):
        payload.update({"reasoning_effort": "none", "include_reasoning": False})
    timeout = max(30, int(os.getenv("GROQ_API_TIMEOUT_SECONDS", "180")))
    proxy = os.getenv("GROQ_HTTPS_PROXY", "").strip()
    if not proxy:
        try:
            with socket.create_connection(("127.0.0.1", 7897), timeout=0.35):
                proxy = "http://127.0.0.1:7897"
        except OSError:
            proxy = ""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".json") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            temp_path = handle.name
        curl_args = [
                "curl.exe", "-sS", "--connect-timeout", "15", "--max-time", str(timeout),
                "-X", "POST", "https://api.groq.com/openai/v1/chat/completions",
                "-H", "Authorization: Bearer " + api_key,
                "-H", "Content-Type: application/json",
                "-H", "User-Agent: Mozilla/5.0",
                "--data-binary", "@" + temp_path,
                "-w", "\n__HTTP_STATUS__:%{http_code}",
        ]
        if proxy:
            curl_args[1:1] = ["--proxy", proxy]
        for api_attempt in range(1, 7):
            completed = subprocess.run(
                curl_args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout + 5,
            )
            stdout = completed.stdout or ""
            body, _, status = stdout.rpartition("\n__HTTP_STATUS__:")
            if completed.returncode != 0:
                raise RuntimeError(f"Groq curl退出码{completed.returncode}: {(completed.stderr or '')[:500]}")
            try:
                data = json.loads(body)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Groq返回非JSON（HTTP {status or 'unknown'}）: {body[:500]}") from exc
            if status == "429" and api_attempt < 6:
                message = str((data.get("error") or {}).get("message", ""))
                match = re.search(r"try again in (?:(\d+)m)?([0-9.]+)s", message, flags=re.I)
                if match:
                    requested_wait = int(match.group(1) or 0) * 60 + int(float(match.group(2))) + 2
                    wait = min(60, max(3, requested_wait))
                else:
                    wait = 60 if "tokens per day" in message.lower() else 30
                print(f"    Groq触发令牌限额，等待{wait}秒后自动续跑...")
                time.sleep(wait)
                continue
            if status and not status.startswith("2"):
                detail = json.dumps(data, ensure_ascii=False)[:500]
                raise RuntimeError(f"Groq HTTP {status}: {detail}")
            return data["choices"][0]["message"]["content"]
        raise RuntimeError("Groq连续限流，重试次数已用尽")
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def call_model(messages: list[dict], *, temperature: float, max_tokens: int) -> tuple[str, str]:
    if os.getenv("DISABLE_QWEN", "").lower() not in {"1", "true", "yes"}:
        import main as project
        qwen_reply = project.call_qianwen_api(
            messages,
            temperature=temperature,
            top_p=0.80,
            repetition_penalty=1.16,
            max_retries=2,
            max_tokens=max_tokens,
        )
        if not is_qwen_error(qwen_reply or ""):
            return qwen_reply, f"qwen:{project.qwen_generation_model()}"
        print("    Qwen不可用或疑似额度受限，切换Groq备用模型。")
    return call_groq(messages, temperature=temperature, max_tokens=max_tokens), (
        "groq:" + os.getenv("GROQ_GENERATION_MODEL", "qwen/qwen3.6-27b")
    )


def build_prompt(
    title: str,
    source_block: str,
    before_tail: str,
    after_head: str,
    constraints: dict,
    block_number: int,
    block_count: int,
    target_chars: int,
    revision_issues: list[str] | None = None,
) -> list[dict]:
    system = (
        "你是擅长儿童向中国神话长篇改写的小说家兼影视场景编剧。"
        "你只写一段插入现有正文的桥接微场景，绝不重写母稿，绝不改换经典人物的功劳、事件次序和结局。"
        "文字要能直接表演：人物有目标、动作、阻碍、临场反应、对白和可见后果。"
        "幽默来自性格、误会、道具小麻烦、一本正经的答非所问和动作反差；"
        "不使用网络梗、厕所笑话、低俗身体笑话。死亡、牺牲、离别和担责现场停止搞笑。"
    )
    user = f"""
请为《{title}》第{block_number}/{block_count}个情节边界写一段约{target_chars}个纯汉字（不计标点）的新增桥接微场景。

全文硬约束：
{json.dumps(constraints, ensure_ascii=False)}

本区块已有正文末尾（新段必须发生在它之后，不得复述）：
<前文>{source_block[-1000:]}</前文>

后一区块开头（仅供衔接，禁止提前重演）：
<后文>{after_head or '这是全文结尾'}</后文>

上一次退回问题：{'；'.join(revision_issues or []) or '无'}

新增要求：
1. 只补一个发生在前文之后、后文之前的现场，不复述任何已有段落，不提前完成后文事件。
2. 增加2—4个与主线动作紧密相连的儿童向喜剧节拍，并至少包含一处自然对白笑点和一处可拍摄的动作反差；笑完立刻继续办正事。
3. 写可表演的场面调度、道具状态、人物尝试、失败后的调整、配角反应和直接后果，使情节更饱满，不写空泛景物堆砌或总结凑字。
4. 阿满只能记录、护青竹简、写错字、嘴硬或短促吐槽，不能出主意、施法、递关键道具、替主角完成行动；不要为了搞笑增加阿满出场次数。
5. 不新增神仙、神兽、法宝或支线；不写血肉伤口和身体机理；不重复前后区块。
6. 开头直接承接前文，结尾自然交给后文。只输出新增的插入段，不要重复前文或后文，不要标题、章节名、说明、字数或任何元文本。
7. 这是“横向加厚”而不是继续推进：新增段结束时，太阳数量、战斗轮次、人物位置、道具归属、人物生死和主线结果必须与前文末尾完全相同。不得抢先执行后文第一个动作。
8. 允许儿童能懂的现代口语和轻度现代笑梗，但不能把神话写成技术说明书，也不能让现代知识替主角解决难题。
9. 不新增任何动物、药草、治疗法、发明或能够影响主角判断/行动的提示。阿满和旁观者的动作不得帮助核心行动成功；不得写“他不知道以后将……”等预告。
10. 笑点要短，每个笑点最多两三句；不要把整段都写成阿满独角戏。新增段至少一半篇幅交给当前神话主角、百姓或既有配角的具体行动与反应。
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def semantic_audit_insertion(
    title: str,
    candidate: str,
    before: str,
    after: str,
    constraints: dict,
    original: str = "",
) -> tuple[bool, list[str]]:
    prompt = f"""
你是儿童神话小说的严格连续性编辑。判断下面新增插段能否放在《{title}》的前文与后文之间。

硬约束：{json.dumps(constraints, ensure_ascii=False)}
<前文>{before[-900:]}</前文>
<被替换原段>{original}</被替换原段>
<替换段>{candidate}</替换段>
<后文>{after[:900] if after else '全文结束'}</后文>

替换段允许并且必须保留“被替换原段”里已有的人物、阿满、青竹简、道具和动作，不能把这些误判为新增。
以下任一情况必须退回：复述前后文；提前执行后文动作或再次执行原段之前已经完成的核心动作；
改变太阳数量、战斗轮次、人物位置、生死、道具归属或主线结果；新增命名人物、动物、神仙、
药草、法宝或支线；阿满出主意、帮主角定位、递关键物或影响核心行动；用技术说明代替剧情、
低俗笑话；重大牺牲处继续逗笑；结尾预告未来；整段由阿满抢戏；断句或衔接不通。

只输出JSON：{{"pass":true,"issues":[]}}。若退回，issues写2—5条具体问题。
""".strip()
    reply = call_groq(
        [
            {"role": "system", "content": "只做严格审稿，只返回合法JSON，不续写正文。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.05,
        max_tokens=500,
    )
    raw = re.sub(r"<think>[\s\S]*?</think>", "", reply or "", flags=re.I).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        return False, ["语义审稿未返回合法JSON"]
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return False, ["语义审稿JSON损坏"]
    issues = [str(item) for item in data.get("issues", []) if str(item).strip()]
    return bool(data.get("pass")) and not issues, issues


def select_expansion_paragraphs(paragraphs: list[str], count: int) -> list[int]:
    solemn = (
        "死", "牺牲", "诀别", "尸", "葬", "哭倒", "自刎", "化蝶", "遇难", "魂",
        "射落", "中箭", "坠落", "化为", "填海", "补天", "决战", "大战", "斩",
        "洪水", "溺", "诀", "离世", "舍身", "化作", "断裂", "流血", "伤口",
    )
    candidates = []
    total = len(paragraphs)
    for index, paragraph in enumerate(paragraphs):
        length = count_chars(paragraph)
        if index < max(2, total // 12) or index >= total - max(3, total // 10):
            continue
        if not 50 <= length <= 1000 or any(term in paragraph for term in solemn):
            continue
        score = 0
        score += 5 if "阿满" in paragraph else 0
        score += 3 if "“" in paragraph else 0
        score += 3 if any(term in paragraph for term in ("笑", "嘀咕", "嘴硬", "打趣")) else 0
        score += min(4, paragraph.count("。"))
        score -= abs(index - total * 0.5) / max(1, total)
        candidates.append((score, index))
    chosen = []
    min_gap = max(3, total // (count + 2))
    for _, index in sorted(candidates, reverse=True):
        if all(abs(index - old) >= min_gap for old in chosen):
            chosen.append(index)
            if len(chosen) == count:
                break
    if len(chosen) < count:
        for _, index in sorted(candidates, reverse=True):
            if index not in chosen:
                chosen.append(index)
                if len(chosen) == count:
                    break
    if len(chosen) < count:
        raise RuntimeError(f"只找到{len(chosen)}个安全扩写段落，目标为{count}个")
    return sorted(chosen)


def build_paragraph_prompt(
    title: str,
    original: str,
    before: str,
    after: str,
    constraints: dict,
    number: int,
    total: int,
    target_chars: int,
    revision_issues: list[str] | None = None,
) -> list[dict]:
    system = (
        "你是儿童向中国神话小说家。你要把一个已有段落原位扩成可拍摄的完整微场景，"
        "保留原段全部事实、人物选择和结果，不推进下一事件，不改变经典神话归功。"
    )
    user = f"""
把《{title}》第{number}/{total}个指定段落原位扩写到约{target_chars}个纯汉字（不计标点）。
硬约束：{json.dumps(constraints, ensure_ascii=False)}
<前一段>{before[-700:] if before else '全文开头'}</前一段>
<原段>{original}</原段>
<后一段>{after[:700] if after else '全文结尾'}</后一段>
上次退回：{'；'.join(revision_issues or []) or '无'}

必须保留原段里已经发生的每个动作、对白信息和直接结果，顺序不变；只把其中过快的动作、
现实阻碍、一次失败调整、人物反应演得更具体。增加2—3个短促儿童笑点：至少一处自然对白
和一处可见动作反差，笑点服务当前行动，不能另开支线。

段落开头状态必须等于原段开头，结尾状态必须等于原段结尾。不得再次执行原段之前已完成的
核心动作，不得抢先执行后一段动作。不得新增命名人物、动物、神仙、药草、法宝或治疗法。
阿满只能记录、护简、写错字或短促嘴硬，不能提示办法、定位目标、递关键物或影响主角。
允许儿童能懂的现代口语和轻度现代笑梗，但禁用说明书写法、低俗身体笑话和未来预告。死亡、牺牲、离别处不搞笑。
只输出扩写后的替换段落正文，不要标题、说明、字数或元文本。
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_block(candidate: str, target_chars: int) -> list[str]:
    length = count_chars(candidate)
    reasons = []
    if length < int(target_chars * 0.50):
        reasons.append(f"偏短:{length}<{int(target_chars * 0.50)}")
    if length > int(target_chars * 2.0):
        reasons.append(f"偏长:{length}>{int(target_chars * 2.0)}")
    hits = [term for term in META_TERMS if term in candidate]
    if hits:
        reasons.append("元文本:" + "、".join(hits))
    if candidate.count("“") != candidate.count("”"):
        reasons.append("中文引号不配对")
    return reasons


def local_story_report(title: str, source: str, text: str, block_meta: list[dict]) -> dict:
    length = count_chars(text)
    meta_hits = [term for term in META_TERMS if term in text]
    humor_signals = sum(text.count(term) for term in ("笑", "逗", "嘀咕", "嘴硬", "打趣", "忍不住"))
    report = {
        "title": title,
        "source_chars": count_chars(source),
        "final_chars": length,
        "added_chars": length - count_chars(source),
        "target_range": [MIN_TOTAL, MAX_TOTAL],
        "block_generation": block_meta,
        "dialogue_open_quotes": text.count("“"),
        "dialogue_close_quotes": text.count("”"),
        "humor_signal_count": humor_signals,
        "meta_hits": meta_hits,
        "passed": True,
        "failures": [],
    }
    if length < MIN_TOTAL:
        report["failures"].append(f"全文纯汉字数不足{MIN_TOTAL}:{length}")
    if report["dialogue_open_quotes"] != report["dialogue_close_quotes"]:
        report["failures"].append("中文引号不配对")
    if meta_hits:
        report["failures"].append("含元文本:" + "、".join(meta_hits))
    if humor_signals < 8:
        report["failures"].append(f"幽默信号不足:{humor_signals}<8")
    report["passed"] = not report["failures"]
    return report


def curated_sanitize_outputs(source_dir: Path, output_dir: Path) -> dict:
    text_dir = output_dir / "texts"
    results = []
    for final_path in sorted(text_dir.glob("*.txt")):
        if final_path.name == "00_总序.txt":
            continue
        title = final_path.stem
        text = final_path.read_text(encoding="utf-8")
        reverted = []
        source_path = source_dir / final_path.name
        source_paragraphs = (
            [part.strip() for part in re.split(r"\n\s*\n", source_path.read_text(encoding="utf-8")) if part.strip()]
            if source_path.exists() else []
        )
        for number in sorted(CURATED_REVERT_BLOCKS.get(title, set())):
            block_path = output_dir / "work" / safe_name(title) / f"block_{number:02d}.txt"
            meta_path = output_dir / "work" / safe_name(title) / f"block_{number:02d}.json"
            if not block_path.exists() or not meta_path.exists():
                continue
            metadata = load_json(meta_path)
            paragraph_index = int(metadata.get("paragraph_index", -1))
            candidate = block_path.read_text(encoding="utf-8").strip()
            if 0 <= paragraph_index < len(source_paragraphs) and candidate in text:
                text = text.replace(candidate, source_paragraphs[paragraph_index], 1)
                reverted.append(number)

        replacement_hits = []
        for old, new in CURATED_TEXT_REPLACEMENTS.items():
            count = text.count(old)
            if count:
                text = text.replace(old, new)
                replacement_hits.append({"old": old, "new": new, "count": count})

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        deduplicated = []
        removed_duplicates = 0
        for paragraph in paragraphs:
            if deduplicated and paragraph == deduplicated[-1]:
                removed_duplicates += 1
                continue
            deduplicated.append(paragraph)
        text = "\n\n".join(deduplicated).strip()
        final_path.write_text(text, encoding="utf-8")
        results.append(
            {
                "title": title,
                "chars": count_chars(text),
                "curated_reverted_blocks": reverted,
                "replacement_hits": replacement_hits,
                "removed_adjacent_duplicate_paragraphs": removed_duplicates,
                "quote_balanced": text.count("“") == text.count("”"),
            }
        )
    report = {
        "mode": "curated_sanitize_after_generation",
        "stories": len(results),
        "min_chars": min((item["chars"] for item in results), default=0),
        "max_chars": max((item["chars"] for item in results), default=0),
        "all_quotes_balanced": all(item["quote_balanced"] for item in results),
        "results": results,
    }
    write_json(output_dir / "final_quality_summary.json", report)
    return report


def audit_selective_outputs(source_dir: Path, output_dir: Path, threshold: int = 8800) -> dict:
    """Verify manual/selective expansion without changing any story text."""
    source_files = {
        path.name: path for path in source_dir.glob("*.txt") if not path.name.startswith("00_")
    }
    final_dir = output_dir / "texts"
    final_files = {
        path.name: path for path in final_dir.glob("*.txt") if not path.name.startswith("00_")
    }
    global_failures = []
    if set(source_files) != set(final_files):
        missing = sorted(set(source_files) - set(final_files))
        extra = sorted(set(final_files) - set(source_files))
        global_failures.append(f"正文文件集合不一致：missing={missing}, extra={extra}")

    results = []
    for name in sorted(set(source_files) & set(final_files)):
        title = Path(name).stem
        source = source_files[name].read_text(encoding="utf-8")
        final = final_files[name].read_text(encoding="utf-8")
        source_hanzi = count_chars(source)
        final_hanzi = count_chars(final)
        targeted = source_hanzi < threshold
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        final_hash = hashlib.sha256(final.encode("utf-8")).hexdigest()
        source_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", source) if p.strip()]
        final_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", final) if p.strip()]

        cursor = 0
        preserved_in_order = True
        for paragraph in source_paragraphs:
            try:
                cursor = final_paragraphs.index(paragraph, cursor) + 1
            except ValueError:
                preserved_in_order = False
                break
        source_counts = Counter(source_paragraphs)
        final_counts = Counter(final_paragraphs)
        added_paragraphs = []
        remaining = source_counts.copy()
        for paragraph in final_paragraphs:
            if remaining[paragraph] > 0:
                remaining[paragraph] -= 1
            else:
                added_paragraphs.append(paragraph)

        added_text = "\n\n".join(added_paragraphs)
        repeated_source = sum(max(0, count - 1) for count in source_counts.values())
        repeated_final = sum(max(0, count - 1) for count in final_counts.values())
        failures = []
        if targeted and final_hanzi < MIN_TOTAL:
            failures.append(f"定点扩写后不足{MIN_TOTAL}个纯汉字:{final_hanzi}")
        if targeted and not preserved_in_order:
            failures.append("母稿段落未全部按原顺序保留")
        if targeted and not added_paragraphs:
            failures.append("定点篇目没有新增自然段")
        if not targeted and source_hash != final_hash:
            failures.append("无需修改篇目未保持逐字节一致")
        if final.count("“") != final.count("”"):
            failures.append("中文引号不配对")
        if repeated_final > repeated_source:
            failures.append("新增了完全重复的自然段")

        results.append({
            "title": title,
            "targeted_below_threshold": targeted,
            "source_hanzi": source_hanzi,
            "final_hanzi": final_hanzi,
            "added_hanzi": final_hanzi - source_hanzi,
            "non_whitespace_chars": len(re.sub(r"\s+", "", final)),
            "source_paragraphs_preserved_in_order": preserved_in_order,
            "added_paragraph_count": len(added_paragraphs),
            "added_dialogue_pairs": min(added_text.count("“"), added_text.count("”")),
            "added_action_signals": sum(added_text.count(term) for term in (
                "走", "跑", "抬", "推", "拉", "转", "落", "接", "挡", "搬", "伸", "退", "试", "检查",
            )),
            "copied_byte_identical": source_hash == final_hash,
            "quote_balanced": final.count("“") == final.count("”"),
            "repeated_paragraphs_before": repeated_source,
            "repeated_paragraphs_after": repeated_final,
            "failures": failures,
            "passed": not failures,
        })

    targeted_results = [item for item in results if item["targeted_below_threshold"]]
    copied_results = [item for item in results if not item["targeted_below_threshold"]]
    report = {
        "mode": "manual_selective_expansion_audit",
        "counting_rule": "纯汉字（U+3400—U+4DBF、U+4E00—U+9FFF），不计标点与空白",
        "selection_threshold": threshold,
        "expanded_minimum_hanzi": MIN_TOTAL,
        "upper_limit": None,
        "story_count": len(results),
        "targeted_count": len(targeted_results),
        "copied_unchanged_count": len(copied_results),
        "targeted_min_hanzi": min((item["final_hanzi"] for item in targeted_results), default=0),
        "targeted_max_hanzi": max((item["final_hanzi"] for item in targeted_results), default=0),
        "all_copied_byte_identical": all(item["copied_byte_identical"] for item in copied_results),
        "all_quotes_balanced": all(item["quote_balanced"] for item in results),
        "global_failures": global_failures,
        "failed_titles": [item["title"] for item in results if not item["passed"]],
        "passed": not global_failures and all(item["passed"] for item in results),
        "results": results,
    }
    write_json(output_dir / "final_quality_summary.json", report)
    return report


def expand_story(
    title: str,
    source_path: Path,
    output_dir: Path,
    constraints: dict,
    block_count: int,
    resume: bool,
) -> dict:
    source = source_path.read_text(encoding="utf-8").strip()
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", source) if part.strip()]
    selected = select_expansion_paragraphs(paragraphs, block_count)
    work_dir = output_dir / "work" / safe_name(title)
    work_dir.mkdir(parents=True, exist_ok=True)
    # Generate toward the requested safe baseline. The assembled story has a
    # strict lower bound, but deliberately no upper bound: quality and story
    # continuity matter more than trimming useful scenes to a fixed ceiling.
    needed = max(0, GENERATION_TOTAL - count_chars(source))
    additions = [needed // block_count] * block_count
    additions[-1] += needed - sum(additions)
    block_meta = []
    replacements: dict[int, str] = {}
    for number, (paragraph_index, addition) in enumerate(zip(selected, additions), 1):
        original = paragraphs[paragraph_index]
        target = count_chars(original) + addition
        text_path = work_dir / f"block_{number:02d}.txt"
        meta_path = work_dir / f"block_{number:02d}.json"
        paragraph_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
        if resume and text_path.exists() and meta_path.exists():
            cached = load_json(meta_path)
            candidate = text_path.read_text(encoding="utf-8").strip()
            if cached.get("source_hash") == paragraph_hash and not validate_block(candidate, target):
                print(f"  复用原位扩写{number}/{block_count}：{count_chars(candidate)}字")
                replacements[paragraph_index] = candidate
                block_meta.append(cached)
                continue

        before = paragraphs[paragraph_index - 1] if paragraph_index else ""
        after = paragraphs[paragraph_index + 1] if paragraph_index + 1 < len(paragraphs) else ""
        best = ""
        attempts = []
        revision_issues: list[str] = []
        for attempt, temperature in enumerate((0.55, 0.42, 0.30, 0.22), 1):
            print(f"  原位扩写{number}/{block_count}，第{attempt}次，目标约{target}字...")
            reply, provider = call_model(
                build_paragraph_prompt(
                    title, original, before, after, constraints, number, block_count, target,
                    revision_issues=revision_issues,
                ),
                temperature=temperature,
                max_tokens=max(1000, min(2600, int(target * 1.55))),
            )
            candidate = clean_reply(reply)
            reasons = validate_block(candidate, target)
            if not reasons and os.getenv("SKIP_SEMANTIC_AUDIT", "").lower() not in {"1", "true", "yes"}:
                semantic_passed, semantic_issues = semantic_audit_insertion(
                    title, candidate, before, after, constraints, original=original
                )
                if not semantic_passed:
                    reasons.extend("语义审稿:" + issue for issue in semantic_issues)
            attempts.append({"attempt": attempt, "provider": provider, "chars": count_chars(candidate), "reasons": reasons})
            if not best or abs(count_chars(candidate) - target) < abs(count_chars(best) - target):
                best = candidate
            if not reasons:
                best = candidate
                break
            revision_issues = reasons
            print("    区块退回：" + "；".join(reasons))
        if not best:
            raise RuntimeError(f"《{title}》原位扩写{number}没有生成有效正文")
        metadata = {
            "title": title,
            "block": number,
            "paragraph_index": paragraph_index,
            "mode": "in_place_paragraph_expansion",
            "source_hash": paragraph_hash,
            "source_chars": count_chars(original),
            "target_chars": target,
            "final_chars": count_chars(best),
            "attempts": attempts,
        }
        text_path.write_text(best, encoding="utf-8")
        write_json(meta_path, metadata)
        replacements[paragraph_index] = best
        block_meta.append(metadata)

    final_paragraphs = [replacements.get(index, paragraph) for index, paragraph in enumerate(paragraphs)]
    final_text = "\n\n".join(final_paragraphs).strip()
    report = local_story_report(title, source, final_text, block_meta)
    report["source_sha256"] = source_hash
    write_json(output_dir / "reports" / f"{safe_name(title)}.json", report)
    candidate_path = work_dir / "assembled_candidate.txt"
    candidate_path.write_text(final_text, encoding="utf-8")
    if report["passed"]:
        final_path = output_dir / "texts" / f"{safe_name(title)}.txt"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_text(final_text, encoding="utf-8")
        print(f"《{title}》完成：{report['source_chars']}→{report['final_chars']}字")
    else:
        print(f"《{title}》未通过本地门槛，仅保留候选：{'；'.join(report['failures'])}")
    return report


def expand_story_with_insertions(
    title: str,
    source_path: Path,
    output_dir: Path,
    constraints: dict,
    block_count: int,
    resume: bool,
) -> dict:
    """Expand without rewriting approved prose: insert audited scenes at plot seams."""
    source = source_path.read_text(encoding="utf-8").strip()
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", source) if part.strip()]
    selected = select_expansion_paragraphs(paragraphs, block_count)
    work_dir = output_dir / "work" / safe_name(title)
    work_dir.mkdir(parents=True, exist_ok=True)
    needed = max(0, GENERATION_TOTAL - count_chars(source))
    additions = [needed // block_count] * block_count
    additions[-1] += needed - sum(additions)
    block_meta = []
    insertions: dict[int, str] = {}

    for number, (paragraph_index, target) in enumerate(zip(selected, additions), 1):
        before = paragraphs[paragraph_index]
        after = paragraphs[paragraph_index + 1] if paragraph_index + 1 < len(paragraphs) else ""
        text_path = work_dir / f"insert_{number:02d}.txt"
        meta_path = work_dir / f"insert_{number:02d}.json"
        seam_hash = hashlib.sha256((before + "\n\0\n" + after).encode("utf-8")).hexdigest()
        if resume and text_path.exists() and meta_path.exists():
            cached = load_json(meta_path)
            candidate = text_path.read_text(encoding="utf-8").strip()
            if cached.get("source_hash") == seam_hash and not validate_block(candidate, target):
                print(f"  复用情节缝隙插段{number}/{block_count}：{count_chars(candidate)}字")
                insertions[paragraph_index] = candidate
                block_meta.append(cached)
                continue

        accepted = ""
        attempts = []
        revision_issues: list[str] = []
        for attempt, temperature in enumerate((0.48, 0.38, 0.28, 0.20), 1):
            print(f"  情节缝隙插段{number}/{block_count}，第{attempt}次，目标约{target}字...")
            reply, provider = call_model(
                build_prompt(
                    title, before, before, after, constraints, number, block_count, target,
                    revision_issues=revision_issues,
                ),
                temperature=temperature,
                max_tokens=max(1200, min(3000, int(target * 2.0))),
            )
            candidate = clean_reply(reply)
            reasons = validate_block(candidate, target)
            if not reasons and os.getenv("SKIP_SEMANTIC_AUDIT", "").lower() not in {"1", "true", "yes"}:
                semantic_passed, semantic_issues = semantic_audit_insertion(
                    title, candidate, before, after, constraints, original=""
                )
                if not semantic_passed:
                    reasons.extend("语义审稿:" + issue for issue in semantic_issues)
            attempts.append(
                {"attempt": attempt, "provider": provider, "chars": count_chars(candidate), "reasons": reasons}
            )
            if not reasons:
                accepted = candidate
                break
            revision_issues = reasons
            print("    插段退回：" + "；".join(reasons))
        if not accepted:
            raise RuntimeError(f"《{title}》情节缝隙插段{number}连续四次未通过，不采用低质候选")

        metadata = {
            "title": title,
            "block": number,
            "paragraph_index": paragraph_index,
            "mode": "audited_plot_seam_insertion",
            "source_hash": seam_hash,
            "target_chars": target,
            "final_chars": count_chars(accepted),
            "attempts": attempts,
        }
        text_path.write_text(accepted, encoding="utf-8")
        write_json(meta_path, metadata)
        insertions[paragraph_index] = accepted
        block_meta.append(metadata)

    final_paragraphs = []
    for index, paragraph in enumerate(paragraphs):
        final_paragraphs.append(paragraph)
        if index in insertions:
            final_paragraphs.append(insertions[index])
    final_text = "\n\n".join(final_paragraphs).strip()
    report = local_story_report(title, source, final_text, block_meta)
    report["source_sha256"] = source_hash
    write_json(output_dir / "reports" / f"{safe_name(title)}.json", report)
    (work_dir / "assembled_candidate.txt").write_text(final_text, encoding="utf-8")
    if report["passed"]:
        final_path = output_dir / "texts" / f"{safe_name(title)}.txt"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_text(final_text, encoding="utf-8")
        print(f"《{title}》完成：{report['source_chars']}→{report['final_chars']}个纯汉字")
    else:
        print(f"《{title}》未通过本地门槛，仅保留候选：{'；'.join(report['failures'])}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将20篇神话母稿扩充到每篇约一万字")
    parser.add_argument("--stories", nargs="*", help="只处理指定篇目；默认处理母稿目录全部20篇")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--blocks", type=int, default=DEFAULT_BLOCKS)
    parser.add_argument("--resume", action="store_true", help="复用源区块哈希一致且通过门槛的过程稿")
    parser.add_argument("--model", default="", help="覆盖Qwen生成模型")
    parser.add_argument("--groq-model", default="", help="覆盖Groq备用模型")
    parser.add_argument("--api-timeout", type=int, default=180)
    parser.add_argument(
        "--insertion-mode",
        action="store_true",
        help="保留母稿全部段落，在安全情节缝隙插入经语义审稿的微场景",
    )
    parser.add_argument(
        "--selective-threshold",
        type=int,
        default=0,
        help="只扩写纯汉字数低于该值的故事；其余正文原样复制到新目录",
    )
    parser.add_argument(
        "--curated-sanitize",
        action="store_true",
        help="对已生成texts执行人工确认的回退、古风词清洗和相邻重复段删除，不调用API",
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="只核验选择性扩写结果并生成final_quality_summary.json，不修改正文",
    )
    return parser.parse_args()


def main_cli() -> int:
    args = parse_args()
    if args.audit_only:
        report = audit_selective_outputs(
            args.source_dir.resolve(), args.output_dir.resolve(), args.selective_threshold or 8800
        )
        print(
            f"核验完成：20篇={report['story_count']}，定点扩写={report['targeted_count']}，"
            f"原样复制={report['copied_unchanged_count']}，通过={report['passed']}"
        )
        return 0 if report["passed"] else 1
    if args.curated_sanitize:
        report = curated_sanitize_outputs(args.source_dir.resolve(), args.output_dir.resolve())
        print(
            f"定点清洗完成：{report['stories']}篇，"
            f"长度范围{report['min_chars']}—{report['max_chars']}，"
            f"引号全部配对={report['all_quotes_balanced']}"
        )
        return 0
    if args.model:
        os.environ["QWEN_GENERATION_MODEL"] = args.model
    if args.groq_model:
        os.environ["GROQ_GENERATION_MODEL"] = args.groq_model
    os.environ["QWEN_API_TRANSPORT"] = os.getenv("QWEN_API_TRANSPORT", "curl")
    os.environ["QWEN_API_TIMEOUT_SECONDS"] = str(args.api_timeout)
    os.environ["GROQ_API_TIMEOUT_SECONDS"] = str(args.api_timeout)

    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    core_data = load_json(DEFAULT_CORE_PATH)
    thread_data = load_json(DEFAULT_THREAD_PATH)
    available = sorted(path.stem for path in source_dir.glob("*.txt") if path.name != "00_总序.txt")
    titles = args.stories or available
    if not titles:
        raise RuntimeError(f"母稿目录没有故事正文：{source_dir}")

    copied_titles = []
    if args.selective_threshold > 0:
        text_dir = output_dir / "texts"
        text_dir.mkdir(parents=True, exist_ok=True)
        selected_titles = []
        for title in titles:
            source_path = source_dir / f"{title}.txt"
            if count_chars(source_path.read_text(encoding="utf-8")) < args.selective_threshold:
                selected_titles.append(title)
            else:
                shutil.copy2(source_path, text_dir / source_path.name)
                copied_titles.append(title)
        titles = selected_titles
        print(
            f"选择性扩写：{len(titles)}篇低于{args.selective_threshold}个纯汉字；"
            f"其余{len(copied_titles)}篇原样复制。"
        )

    reports = []
    for number, title in enumerate(titles, 1):
        print(f"\n[{number}/{len(titles)}] 开始扩写《{title}》")
        try:
            core = find_story(core_data, title)
            thread = find_story(thread_data, title)
            reports.append(
                (expand_story_with_insertions if args.insertion_mode else expand_story)(
                    title,
                    source_dir / f"{title}.txt",
                    output_dir,
                    compact_constraints(core, thread),
                    max(2, args.blocks),
                    args.resume,
                )
            )
        except Exception as exc:
            print(f"《{title}》扩写异常：{type(exc).__name__}: {exc}", file=sys.stderr)
            reports.append({"title": title, "passed": False, "error": str(exc)})
        write_json(
            output_dir / "summary.json",
            {
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "target_chars": TARGET_TOTAL,
                "generation_target_chars": GENERATION_TOTAL,
                "accepted_range": [MIN_TOTAL, MAX_TOTAL],
                "total": len(titles),
                "finished": len(reports),
                "passed": sum(bool(item.get("passed")) for item in reports),
                "failed_titles": [item.get("title") for item in reports if not item.get("passed")],
                "copied_unchanged_titles": copied_titles,
                "reports": reports,
            },
        )

    intro = source_dir / "00_总序.txt"
    if intro.exists():
        (output_dir / "texts").mkdir(parents=True, exist_ok=True)
        (output_dir / "texts" / intro.name).write_text(intro.read_text(encoding="utf-8"), encoding="utf-8")
    return 0 if len(reports) == len(titles) and all(item.get("passed") for item in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
