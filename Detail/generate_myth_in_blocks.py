import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import main as project
import rebuild_myths_chaptered as rebuild


def chapter_plan_hash(chapter_plan: dict) -> str:
    return hashlib.sha256(
        json.dumps(chapter_plan, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def parse_chapter_blocks(raw: str) -> dict[int, str]:
    normalized = rebuild.normalize_known_traditional(raw or "")
    matches = list(
        re.finditer(
            r"<chapter\s+n=[\"']?([1-8])[\"']?\s*>(.*?)</chapter>",
            normalized,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )
    result = {}
    for match in matches:
        number = int(match.group(1))
        text = project.clean_markdown(match.group(2)).strip()
        text = project.split_long_paragraphs(
            text, max_paragraph_len=360, soft_paragraph_len=230
        )
        result[number] = text
    return result


def block_prompt(
    title: str,
    story_plan: dict,
    block_plans: list[dict],
    prior_chapters: list[str],
    previous_issues: list[str],
) -> str:
    start = block_plans[0]["chapter"]
    end = block_plans[-1]["chapter"]
    previous_state = rebuild.story_state_before(story_plan, start)
    previous_tail = prior_chapters[-1][-900:] if prior_chapters else "无，这是全文开篇。"
    compact_plans = [
        {
            "chapter": item["chapter"],
            "function": item["function"],
            "goal": item["goal"],
            "obstacle": item["obstacle"],
            "adjustment": item["adjustment"],
            "result": item["result"],
            "core_nodes": item.get("core_nodes", []),
            "required_terms": item.get("required_terms", []),
            "forbidden_terms": item.get("forbidden_terms", []),
            "aman_mode": item.get("aman_mode", "none"),
            "aman_max_mentions": item.get("aman_max_mentions", 0),
        }
        for item in block_plans
    ]
    issue_block = (
        "上一候选被退回，必须逐条修正：\n" + "\n".join(f"- {item}" for item in previous_issues)
        if previous_issues
        else "这是本区块第一版。"
    )
    return f"""
写《{title}》第{start}至第{end}章正文。四章必须一次连续写出，以便保持全局因果；每章只完成事件表中
分配给自己的新任务，上一章已经发生的动作只能用一句后果承接，绝不重新演出。

区块开始前的确定状态：{previous_state}
前文最后一段：
{previous_tail}

四章锁定事件表：
{json.dumps(compact_plans, ensure_ascii=False, indent=2)}

{issue_block}

写作硬规则：
1. 每章写900至1100个中文字符、八到十四个自然段；长度来自“目标变迫切—具体阻碍—人物选择—
   行动调整—直接后果”，不用重复景色、动作清单、身体反应或结尾议论扩写。
2. 八仙等群像必须按事件表点名和行动，不能用“其余人也各展本领”带过；也不能让未轮到的人
   抢先完成后章动作。
3. 幽默来自人物性格、误会和短对话，不写摔倒、伤口、排泄、低俗身体笑料，不用现代词。
4. 阿满只在aman_mode允许的章节短暂旁观，带青竹简、旧笔、小布袋；不能施法、指挥或总结主题。
5. 禁止精确距离、尺寸、时刻、计数、角度、材料分类、身体机理、血肉细节、海洋技术说明。
6. 不输出章名、提纲、说明、字数或Markdown。严格使用以下标签，标签外不得有文字：
<chapter n="{start}">
第{start}章正文
</chapter>
……
<chapter n="{end}">
第{end}章正文
</chapter>
""".strip()


def validate_block(
    raw: str,
    parsed: dict[int, str],
    block_plans: list[dict],
    prior_chapters: list[str],
) -> list[str]:
    reasons = []
    expected = [item["chapter"] for item in block_plans]
    if sorted(parsed) != expected:
        reasons.append(f"章节标签不完整：得到{sorted(parsed)}，需要{expected}")
        return reasons
    context = list(prior_chapters)
    for chapter_plan in block_plans:
        number = chapter_plan["chapter"]
        text = parsed[number]
        chapter_reasons = rebuild.local_chapter_reasons(
            text, text, chapter_plan, context, minimum_paragraphs=4
        )
        if chapter_reasons:
            reasons.append(f"第{number}章：" + "；".join(chapter_reasons))
        context.append(text)
    return reasons


def save_accepted_block(
    title: str,
    story_plan: dict,
    parsed: dict[int, str],
    work_dir: Path,
) -> None:
    chapter_dir = work_dir / "chapters"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    by_number = {item["chapter"]: item for item in story_plan["chapters"]}
    for number, text in parsed.items():
        plan = by_number[number]
        (chapter_dir / f"{number:02d}.txt").write_text(text, encoding="utf-8")
        rebuild.write_json(
            chapter_dir / f"{number:02d}.json",
            {
                "title": title,
                "chapter": number,
                "plan_hash": chapter_plan_hash(plan),
                "model": project.qwen_generation_model(),
                "generation_mode": "four_chapter_block",
                "length": rebuild.count_chars(text),
                "human_review_required": True,
            },
        )


def generate_block(
    title: str,
    story_plan: dict,
    core: dict,
    block_plans: list[dict],
    prior_chapters: list[str],
    work_dir: Path,
) -> dict[int, str]:
    block_name = f"{block_plans[0]['chapter']}-{block_plans[-1]['chapter']}"
    candidate_dir = work_dir / "block_candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    previous_issues = []
    system = rebuild.chapter_system_prompt(title, story_plan, core)
    for attempt, temperature in enumerate((0.34, 0.24, 0.16), 1):
        print(f"  生成第{block_name}章区块，第{attempt}次...")
        user = block_prompt(title, story_plan, block_plans, prior_chapters, previous_issues)
        raw = project.call_qianwen_api(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            top_p=0.72,
            repetition_penalty=1.24,
            max_retries=3,
            max_tokens=9500,
        )
        parsed = parse_chapter_blocks(raw)
        reasons = validate_block(raw, parsed, block_plans, prior_chapters)
        (candidate_dir / f"block_{block_name}_{attempt:02d}_raw.txt").write_text(
            raw or "", encoding="utf-8"
        )
        rebuild.write_json(
            candidate_dir / f"block_{block_name}_{attempt:02d}_audit.json",
            {
                "attempt": attempt,
                "chapters": {
                    str(number): {"length": rebuild.count_chars(text)}
                    for number, text in parsed.items()
                },
                "reasons": reasons,
            },
        )
        if not reasons:
            return parsed
        print("    区块退回：" + " | ".join(reasons))
        previous_issues = reasons
    raise RuntimeError(f"第{block_name}章区块连续生成失败")


def rebuild_title(title: str, plan_data: dict, output_dir: Path) -> int:
    story_plan = rebuild.find_story_plan(plan_data, title)
    core = rebuild.find_core(title)
    work_dir = output_dir / "work" / rebuild.safe_name(title)
    work_dir.mkdir(parents=True, exist_ok=True)
    rebuild.write_json(work_dir / "outline.json", story_plan)
    chapters = []
    for start in (0, 4):
        plans = story_plan["chapters"][start : start + 4]
        parsed = generate_block(title, story_plan, core, plans, chapters, work_dir)
        save_accepted_block(title, story_plan, parsed, work_dir)
        chapters.extend(parsed[number] for number in range(start + 1, start + 5))
    local = rebuild.local_story_audit(title, chapters, story_plan, core)
    text = "\n\n".join(chapters).strip()
    (work_dir / "block_assembled_candidate.txt").write_text(text, encoding="utf-8")
    rebuild.write_json(
        work_dir / "block_generation_audit.json",
        {
            "title": title,
            "model": project.qwen_generation_model(),
            "human_review_required": True,
            "local_audit": local,
        },
    )
    print(
        f"《{title}》区块候选完成：{local['length']}字；"
        f"本地硬错误={local['hard_failures'] or '无'}；等待人工逐章审查。"
    )
    return 1 if local["hard_failures"] else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按四章连续区块生成已锁定事件表的神话候选")
    parser.add_argument("--stories", nargs="+", required=True)
    parser.add_argument(
        "--plan",
        type=Path,
        default=rebuild.DEFAULT_PLAN_PATH,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=rebuild.DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument("--model", default="qwen-plus")
    parser.add_argument("--api-transport", choices=("auto", "sdk", "curl"), default="curl")
    parser.add_argument("--curl-interface", default="")
    parser.add_argument("--curl-resolve-ip", default="")
    parser.add_argument("--api-timeout", type=int, default=120)
    parser.add_argument("--api-retries", type=int, default=3)
    return parser.parse_args()


def main_cli() -> int:
    args = parse_args()
    os.environ["QWEN_GENERATION_MODEL"] = args.model
    os.environ["QWEN_API_TRANSPORT"] = args.api_transport
    os.environ["QWEN_API_TIMEOUT_SECONDS"] = str(args.api_timeout)
    os.environ["QWEN_API_MAX_RETRIES"] = str(args.api_retries)
    if args.curl_interface:
        os.environ["QWEN_CURL_INTERFACE"] = args.curl_interface
    if args.curl_resolve_ip:
        os.environ["QWEN_CURL_RESOLVE_IP"] = args.curl_resolve_ip
    plan_data = rebuild.load_json(args.plan)
    output_dir = args.output_dir.resolve()
    failed = []
    for title in args.stories:
        try:
            if rebuild_title(title, plan_data, output_dir):
                failed.append(title)
        except Exception as exc:
            print(f"《{title}》区块生成失败：{exc}", file=sys.stderr)
            failed.append(title)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
