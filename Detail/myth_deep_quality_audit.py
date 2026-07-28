import json
import os
import re
import argparse
from pathlib import Path

from batch_myth_quality_audit import STORY_TITLES, load_main_quietly


CURRENT_DIR = Path(__file__).resolve().parent
FINAL_DIR = CURRENT_DIR / "outputs" / "myth_final_18_houyi_quality_20260712"


def parse_json_reply(reply: str) -> dict:
    match = re.search(r"\{[\s\S]*\}", reply or "")
    if not match:
        return {"parse_error": True, "raw": (reply or "")[:1200]}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"parse_error": True, "raw": match.group(0)[:1200]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stories", nargs="*", default=[])
    parser.add_argument("--input-dir", default=str(FINAL_DIR), help="包含 texts 子目录的待审计产出目录。")
    parser.add_argument("--output-dir", default=None, help="深度审计报告目录；默认写入输入目录/deep_audit。")
    args = parser.parse_args()
    story_titles = args.stories or STORY_TITLES
    input_dir = Path(args.input_dir)
    audit_dir = Path(args.output_dir) if args.output_dir else input_dir / "deep_audit"
    main_module = load_main_quietly()
    audit_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, title in enumerate(story_titles, 1):
        text_path = input_dir / "texts" / f"{title}.txt"
        text = text_path.read_text(encoding="utf-8")
        myth_core = main_module.find_myth_core(f"改写神话故事{title}，要求有幽默")
        core_block = main_module.format_myth_core_block(myth_core)
        thread_block = main_module.format_thread_protagonist_block(myth_core.get("_thread_protagonist", {}))
        messages = [
            {
                "role": "system",
                "content": (
                    "你是严格的中国神话小说终审编辑。完整阅读正文后只输出JSON。"
                    "不能因为字数够或含关键词就判好；重点抓擅自新增神异设定、别篇串入现场、"
                    "事件重复、机械填充、现代/元文本、低俗笑点、伤痛过细、阿满抢主线。"
                    "跨篇只允许阿满在结尾用一两句回忆，不允许别篇人物实体出现。"
                ),
            },
            {
                "role": "user",
                "content": f"""审查《{title}》全文。

核心约束：
{core_block}

阿满约束：
{thread_block}

请输出：
{{
  "canonical_complete": 0到10,
  "humor_quality": 0到10,
  "aman_series_function": 0到10,
  "prose_like_houyi_baseline": 0到10,
  "unsupported_magic_or_plot": ["最多8条，每条引用正文中不超过20字的原句并说明"],
  "repetition_or_filler": ["最多8条"],
  "format_or_language_pollution": ["最多8条"],
  "aman_violations": ["最多8条"],
  "fatal_issues": ["必须修改才能交付的问题"],
  "verdict": "PASS或REVISE"
}}

只有故事完整、幽默自然且较多、阿满串联有效、无严重新增设定/填充/格式污染时才能PASS。

正文：
{text}
""",
            },
        ]
        print(f"[deep audit {index}/{len(story_titles)}] {title}")
        reply = main_module.call_qianwen_api(
            messages,
            temperature=0.1,
            top_p=0.7,
            repetition_penalty=1.05,
            max_retries=2,
            max_tokens=1800,
        )
        result = parse_json_reply(reply)
        result["title"] = title
        results.append(result)
        (audit_dir / f"{title}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    summary = {
        "model": os.getenv("QWEN_GENERATION_MODEL", "qwen-plus"),
        "total": len(results),
        "passed": sum(1 for item in results if item.get("verdict") == "PASS"),
        "revise_titles": [item["title"] for item in results if item.get("verdict") != "PASS"],
        "results": results,
    }
    summary_name = "summary.json" if not args.stories else "partial_summary.json"
    (audit_dir / summary_name).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"passed": summary["passed"], "revise_titles": summary["revise_titles"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
