import argparse
import json
import os
import sys
from pathlib import Path

import main as project
import rebuild_myths_chaptered as rebuild


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DRAFT_DIR = BASE_DIR / "outputs" / "20个神话故事（逐篇重制版）" / "plan_drafts"


def compact_core(core: dict) -> dict:
    keep = (
        "title",
        "aliases",
        "core_summary",
        "event_chain",
        "must_include",
        "must_not_change",
        "forbidden_elements",
        "required_character_actions",
        "character_constraints",
        "prop_constraints",
        "setting_constraints",
        "expansion_guidance",
        "required_terms",
    )
    return {key: core.get(key) for key in keep if core.get(key)}


def compact_thread(core: dict) -> dict:
    thread = core.get("_thread_protagonist") or {}
    keep = (
        "required_phrases",
        "min_required_phrase_hits",
        "role",
        "must_do",
        "callback_options",
        "forbidden",
    )
    return {key: thread.get(key) for key in keep if thread.get(key)}


def plan_prompt(title: str, core: dict) -> tuple[str, str]:
    system = """
你是中文神话长篇改写的结构编辑。你的任务不是写正文，而是把一条经典神话事件链锁成八章事件表。
事件表必须让八章各自发生不同的新事件；已经在前章现场发生的经典节点，后章不得重新演一遍。
每章都要有目标、具体阻碍、行动调整和不可逆的章末状态。扩写只能来自原主线的准备、试错、
选择、代价、关系变化和余波，不得凭空添加无后续作用的神仙、法宝、怪物、预言或路人支线。
阿满只是带青竹简、旧笔和小布袋的见闻小史官，不能解决危机。严肃、死亡、牺牲和分离章节
必须设置aman_mode为none。全篇只在二到四章安排阿满，且每次都是短促旁观或幽默，不得代替
经典人物总结主题。只输出一个JSON对象，不要Markdown。
""".strip()
    schema = {
        "title": title,
        "strategy": "说明本篇属于何种递进策略以及八章如何避免重复",
        "opening_state": "故事开篇前的明确状态",
        "story_specific_forbidden": ["本篇特别容易出现的错写或支线"],
        "chapters": [
            {
                "chapter": 1,
                "function": "本章在全篇中的唯一功能",
                "goal": "人物本章要完成的具体目标",
                "obstacle": "现场可见的具体阻碍",
                "adjustment": "人物受阻后采取的不同做法",
                "result": "章末新状态，下一章必须从这里承接",
                "core_nodes": ["只放本章现场发生的经典节点"],
                "required_terms": ["正文必须逐字出现的少量称谓或道具"],
                "forbidden_terms": ["尚未发生的后续事件和本章常见错写"],
                "aman_mode": "none或light或moderate",
                "aman_max_mentions": 0,
                "target_min": 950,
                "target_max": 1100,
                "min_chars": 880,
                "max_chars": 1250,
            }
        ],
    }
    user = f"""
请为《{title}》制作可直接用于生成正文的八章事件表。

经典约束：
{json.dumps(compact_core(core), ensure_ascii=False, indent=2)}

串线人物约束：
{json.dumps(compact_thread(core), ensure_ascii=False, indent=2)}

硬性验收：
1. chapters必须恰好八项，chapter依次为1到8。
2. event_chain中的每个经典节点只能分配给最合适的一章现场演出；不得把同一经典动作换词后分给多章。
3. 第一章可以建立人物选择，第八章可以写直接余波，但不能把前七章仅概述过的关键节点拖到结尾补演。
4. 每章的goal、obstacle、adjustment、result都必须是本篇专属内容，不得写“面对困难、继续努力”之类空话。
5. 死亡、分离、牺牲、灾难正面发生的章节不出现阿满、不安排笑点。其余章节也只轻用阿满。
6. 每章目标约950到1100个中文字符，全篇目标约7800到8300字符；篇幅来自因果过程，不来自景物清单、
   身体机理、伤口细节、精确计量、重复开场、排比总结或现代技术说明。
7. story_specific_forbidden必须吸收经典约束中的禁区，并补充本篇最容易出现的时代错位和支线污染。
8. 只输出下面结构的一个JSON对象，不得输出解释：
{json.dumps(schema, ensure_ascii=False, indent=2)}
""".strip()
    return system, user


def validate_plan(plan: dict, expected_title: str, core: dict) -> list[str]:
    reasons = []
    if plan.get("title") != expected_title:
        reasons.append("标题不匹配")
    chapters = plan.get("chapters")
    if not isinstance(chapters, list) or len(chapters) != 8:
        return reasons + ["章节数不是8"]
    if [item.get("chapter") for item in chapters] != list(range(1, 9)):
        reasons.append("章节编号不是1到8")
    required_fields = (
        "function",
        "goal",
        "obstacle",
        "adjustment",
        "result",
        "core_nodes",
        "required_terms",
        "forbidden_terms",
        "aman_mode",
    )
    for index, chapter in enumerate(chapters, 1):
        for field in required_fields:
            if field not in chapter:
                reasons.append(f"第{index}章缺少{field}")
        mode = chapter.get("aman_mode")
        if mode not in {"none", "light", "moderate"}:
            reasons.append(f"第{index}章aman_mode无效")
        chapter["target_min"] = int(chapter.get("target_min", 950))
        chapter["target_max"] = int(chapter.get("target_max", 1100))
        chapter["min_chars"] = int(chapter.get("min_chars", 880))
        chapter["max_chars"] = int(chapter.get("max_chars", 1250))
        chapter["aman_max_mentions"] = int(
            chapter.get("aman_max_mentions", 0 if mode == "none" else (3 if mode == "light" else 5))
        )
        chapter_text = json.dumps(chapter, ensure_ascii=False)
        if mode == "none" and "阿满" in chapter_text:
            reasons.append(f"第{index}章禁止阿满却仍写入阿满")
    used_nodes = {}
    for chapter in chapters:
        for node in chapter.get("core_nodes") or []:
            if node in used_nodes:
                reasons.append(
                    f"经典节点重复分配：{node}（第{used_nodes[node]}章与第{chapter['chapter']}章）"
                )
            used_nodes[node] = chapter["chapter"]
    aman_chapters = [item["chapter"] for item in chapters if item.get("aman_mode") != "none"]
    if not 2 <= len(aman_chapters) <= 4:
        reasons.append(f"阿满出场章节应为2到4章，实际为{aman_chapters}")
    plan_text = json.dumps(plan, ensure_ascii=False)
    for required in core.get("must_include") or []:
        if required not in plan_text:
            reasons.append(f"计划遗漏经典必需项：{required}")
    for character, action in (core.get("required_character_actions") or {}).items():
        if character not in plan_text:
            reasons.append(f"计划遗漏人物：{character}")
        action_terms = [term for term in ("葫芦", "铁拐", "芭蕉扇", "纸驴", "渔鼓", "宝剑", "御剑", "荷花", "花篮", "玉箫", "玉板") if term in action]
        if action_terms and not any(term in plan_text for term in action_terms):
            reasons.append(f"计划未锁定{character}的代表动作：{action}")
    hard_hits = rebuild.hard_term_hits(plan_text)
    for category, terms in hard_hits.items():
        if terms:
            reasons.append(f"计划含{category}禁写词：{'、'.join(terms[:5])}")
    return list(dict.fromkeys(reasons))


def draft_one(title: str, output_dir: Path) -> dict:
    core = rebuild.find_core(title)
    system, user = plan_prompt(title, core)
    raw = project.call_qianwen_api(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.18,
        top_p=0.68,
        repetition_penalty=1.18,
        max_retries=3,
        max_tokens=7000,
    )
    plan = rebuild.parse_json_reply(raw)
    reasons = validate_plan(plan, title, core)
    record = {
        "title": title,
        "model": project.qwen_generation_model(),
        "human_review_required": True,
        "validation_reasons": reasons,
        "plan": plan,
    }
    rebuild.write_json(output_dir / f"{rebuild.safe_name(title)}.json", record)
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为待重制神话生成八章事件表草案；草案必须人工审查后才能并入正式计划")
    parser.add_argument("--stories", nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DRAFT_DIR)
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
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    failed = []
    for title in args.stories:
        try:
            record = draft_one(title, output_dir)
            print(f"《{title}》事件表草案完成：{record['validation_reasons'] or '本地结构校验通过，等待人工审查'}")
            if record["validation_reasons"]:
                failed.append(title)
        except Exception as exc:
            print(f"《{title}》事件表草案失败：{exc}", file=sys.stderr)
            failed.append(title)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
