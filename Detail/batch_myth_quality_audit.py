import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
DEFAULT_OUTPUT_DIR = CURRENT_DIR / "outputs" / "myth_batch_audit"

DELIVERED_STORY_TITLES = [
    "八仙过海",
    "北冥鲲鹏",
    "仓颉造字",
    "嫦娥奔月",
    "伏羲画卦",
    "后羿射日",
    "精卫填海",
    "夸父追日",
    "雷泽华胥",
    "梁山伯与祝英台",
    "孟姜女哭长城",
    "牛郎织女",
    "女娲补天",
    "女娲造人",
    "神农尝百草",
    "吴刚伐桂",
    "西王母",
    "愚公移山",
]

ADDITIONAL_STORY_TITLES = [
    "哪吒闹海",
    "大禹治水",
]

STORY_TITLES = DELIVERED_STORY_TITLES + ADDITIONAL_STORY_TITLES

def load_main_quietly():
    sys.path.insert(0, str(CURRENT_DIR))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import main  # noqa: WPS433
    return main


def safe_filename(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", title)


def text_excerpt(text: str, limit: int = 1800) -> str:
    if len(text) <= limit * 2:
        return text
    return text[:limit] + "\n\n……中段省略……\n\n" + text[-limit:]


def find_external_terms(main, text: str, myth_core: dict) -> list:
    terms = []
    for term in main.thread_protagonist_external_terms(myth_core):
        if term and term in text:
            terms.append(term)
    return terms


def static_audit(main, title: str, text: str) -> dict:
    myth_core = main.find_myth_core(f"改写神话故事{title}，要求有幽默")
    thread_constraint = myth_core.get("_thread_protagonist", {}) if myth_core else {}
    humor_marker_count = main.humor_signal_count(text)
    dialogue_turn_count = text.count("“")
    is_additional_story = title in ADDITIONAL_STORY_TITLES
    humor_marker_floor = 24 if is_additional_story else 14
    dialogue_turn_floor = 18 if is_additional_story else 0
    external_terms = find_external_terms(main, text, myth_core) if myth_core else []

    checks = {
        "length_near_8000": main.MYTH_TARGET_TOTAL_MIN <= len(text) <= main.MYTH_TARGET_TOTAL_MAX,
        "length_project_range": main.MYTH_TARGET_TOTAL_MIN <= len(text) <= main.MYTH_TARGET_TOTAL_MAX,
        "no_garbled_text": not main.has_obvious_garbled_text(text, myth_core),
        "no_body_drift": not main.contains_body_drift(text, myth_core),
        "no_myth_consistency_violation": not main.violates_myth_consistency(text, myth_core),
        "myth_core_required": main.myth_core_requirement_met(text, myth_core, final=True),
        "myth_final_phrases": main.myth_core_final_phrases_met(text, myth_core),
        "thread_required": main.thread_protagonist_requirement_met(text, myth_core),
        "thread_system_link": main.thread_protagonist_system_requirement_met(text, myth_core),
        "thread_valid_cross_story_bridge": main.valid_thread_cross_story_bridge_met(text, myth_core),
        "no_thread_protagonist_violation": not main.contains_thread_protagonist_violation(text, myth_core),
        "has_aman": "阿满" in text,
        "has_bamboo_slips": "青竹简" in text,
        "has_shanhai_20": "山海二十简" in text,
        "has_external_myth_link": bool(external_terms),
        "forbidden_humor_clean": not any(marker in text for marker in main.FORBIDDEN_HUMOR_STYLE_MARKERS),
        "humor_requirement": main.humor_requirement_met(text, f"改写神话故事{title}，要求有幽默"),
        "humor_marker_min": humor_marker_count >= humor_marker_floor,
        "strong_humor_dialogue_density": dialogue_turn_count >= dialogue_turn_floor,
        "houyi_quality": main.houyi_story_quality_met(text, myth_core),
        "project_validate_story_quality": main.validate_story_quality(text, f"改写神话故事{title}，要求有幽默", myth_core),
    }

    failed = [name for name, ok in checks.items() if not ok]
    return {
        "title": title,
        "length": len(text),
        "line_count": len([line for line in text.splitlines() if line.strip()]),
        "humor_marker_count": humor_marker_count,
        "humor_marker_floor": humor_marker_floor,
        "dialogue_turn_count": dialogue_turn_count,
        "dialogue_turn_floor": dialogue_turn_floor,
        "external_terms": external_terms,
        "thread_required_hit_count": main.thread_protagonist_required_hit_count(text, myth_core),
        "thread_required_phrases": thread_constraint.get("required_phrases", []),
        "checks": checks,
        "failed": failed,
        "pass_static": not failed,
    }


def qwen_audit(main, title: str, text: str) -> dict:
    is_additional_story = title in ADDITIONAL_STORY_TITLES
    humor_rule = (
        "本篇是新增交付稿，必须达到强烈幽默风趣：笑点密集但贴合人物与动作，不能只靠阿满重复嘴硬。"
        if is_additional_story
        else "幽默应自然、贴合人物与动作。"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是神话改写质量审稿人。只输出 JSON，不要解释。"
                "从故事完整性、幽默强度、阿满同系列串联功能、乱码/污染、字数体感五方面打分。"
                + humor_rule
            ),
        },
        {
            "role": "user",
            "content": f"""请审查《{title}》改写正文，输出如下 JSON：
{{
  "story_complete": 0-10,
  "humor_like_nezha": 0-10,
  "aman_series_link": 0-10,
  "language_clean": 0-10,
  "length_feels_enough": 0-10,
  "main_issues": ["最多5条问题"],
  "actionable_fix": "一句话修改建议"
}}

正文：
{text}
""",
        },
    ]
    reply = main.call_qianwen_api(
        messages,
        temperature=0.2,
        top_p=0.8,
        repetition_penalty=1.05,
        max_retries=2,
        max_tokens=900,
    )
    cleaned = main.clean_markdown(reply or "").strip()
    match = re.search(r'\{[\s\S]*\}', cleaned)
    if not match:
        return {"parse_error": True, "raw": cleaned[:1200]}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"parse_error": True, "raw": cleaned[:1200]}


def qwen_preflight_direct(api_timeout: int, attempts: int = 3) -> dict:
    sys.path.insert(0, str(CURRENT_DIR))
    from config import API_Key_QW  # noqa: WPS433

    payload = {
        "model": "qwen-turbo",
        "input": {"messages": [{"role": "user", "content": "用四个字回答：测试成功"}]},
        "parameters": {"result_format": "message", "max_tokens": 30},
    }
    last_result = {"ok": False, "reply": "not attempted", "returncode": None}
    for attempt in range(1, max(1, attempts) + 1):
        temp_path = None
        try:
            import tempfile

            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".json") as f:
                json.dump(payload, f, ensure_ascii=False)
                temp_path = f.name
            curl_network_args = []
            curl_interface = os.getenv("QWEN_CURL_INTERFACE", "").strip()
            curl_resolve_ip = os.getenv("QWEN_CURL_RESOLVE_IP", "").strip()
            if curl_interface:
                curl_network_args.extend(["--interface", curl_interface])
            if curl_resolve_ip:
                curl_network_args.extend([
                    "--resolve",
                    f"dashscope.aliyuncs.com:443:{curl_resolve_ip}",
                ])
            completed = subprocess.run(
                [
                    "curl.exe",
                    *curl_network_args,
                    "-sS",
                    "--connect-timeout",
                    str(min(15, api_timeout)),
                    "--max-time",
                    str(api_timeout),
                    "-X",
                    "POST",
                    "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                    "-H",
                    "Authorization: Bearer " + API_Key_QW,
                    "-H",
                    "Content-Type: application/json",
                    "--data-binary",
                    "@" + temp_path,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=api_timeout + 5,
            )
            body = completed.stdout or completed.stderr or ""
            data = json.loads(body) if completed.returncode == 0 and body.strip().startswith("{") else {}
            choices = data.get("output", {}).get("choices", [])
            reply = choices[0].get("message", {}).get("content", "") if choices else body
            ok = completed.returncode == 0 and "测试" in reply
            last_result = {"ok": ok, "reply": (reply or "")[:500], "returncode": completed.returncode, "attempt": attempt}
            if ok:
                return last_result
        except Exception as e:
            last_result = {"ok": False, "reply": f"{type(e).__name__} - {e}"[:500], "attempt": attempt}
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
        if attempt < attempts:
            time.sleep(2 * attempt)
    return last_result


def generate_story(title: str, out_path: Path, log_path: Path, api_timeout: int, api_retries: int, api_transport: str, process_timeout: int) -> dict:
    humor_requirement = (
        "要求强烈幽默风趣，笑点密集而自然，以人物互怼、行动反差和阿满记录时的狼狈为主"
        if title in ADDITIONAL_STORY_TITLES
        else "要求有幽默"
    )
    prompt = f"改写神话故事{title}，{humor_requirement}，正文目标8000字"
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(CURRENT_DIR)!r}); "
        "from main import generate_myth_rewrite; "
        "title=sys.argv[1]; out=sys.argv[2]; prompt=sys.argv[3]; "
        "text=generate_myth_rewrite(prompt); "
        "open(out,'w',encoding='utf-8').write(text)"
    )
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["QWEN_API_TIMEOUT_SECONDS"] = str(api_timeout)
    env["QWEN_API_MAX_RETRIES"] = str(api_retries)
    env["QWEN_API_TRANSPORT"] = api_transport
    env["FORCE_MYTH_CONTROLLED_REWRITE"] = "1"
    env.pop("FORCE_MYTH_MANUAL_FALLBACK", None)
    started = datetime.now()
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"[{started.isoformat(timespec='seconds')}] start {title}\n")
        log.write(f"输入需求：{prompt}\n")
        log.flush()
        try:
            completed = subprocess.run(
                [sys.executable, "-X", "utf8", "-c", code, title, str(out_path), prompt],
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=process_timeout,
                check=False,
            )
            return {
                "generated": (
                    completed.returncode == 0
                    and out_path.exists()
                    and out_path.stat().st_size > 0
                ),
                "returncode": completed.returncode,
                "timed_out": False,
                "started_at": started.isoformat(timespec="seconds"),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
        except subprocess.TimeoutExpired:
            log.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] PROCESS TIMEOUT after {process_timeout}s\n")
            return {
                "generated": False,
                "returncode": None,
                "timed_out": True,
                "started_at": started.isoformat(timespec="seconds"),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }


def main_cli():
    parser = argparse.ArgumentParser(description="批量生成并审计20篇神话改写质量。")
    parser.add_argument("--stories", nargs="*", default=None, help="只跑指定故事名；默认跑20篇。")
    parser.add_argument("--limit", type=int, default=None, help="只跑前N篇，便于冒烟测试。")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--api-timeout", type=int, default=60)
    parser.add_argument("--api-retries", type=int, default=2)
    parser.add_argument("--api-transport", choices=["auto", "sdk", "curl"], default="curl")
    parser.add_argument("--curl-interface", default=None, help="仅对Qwen curl调用绑定本机网卡地址。")
    parser.add_argument("--curl-resolve-ip", default=None, help="仅对Qwen域名临时使用指定直连IP。")
    parser.add_argument("--process-timeout", type=int, default=900)
    parser.add_argument("--skip-generate", action="store_true", help="只审计已有正文。")
    parser.add_argument("--llm-audit", action="store_true", help="额外调用Qwen做主观质量审稿。")
    parser.add_argument("--no-preflight", action="store_true", help="生成前不做Qwen短调用预检。")
    args = parser.parse_args()

    if args.curl_interface:
        os.environ["QWEN_CURL_INTERFACE"] = args.curl_interface
    if args.curl_resolve_ip:
        os.environ["QWEN_CURL_RESOLVE_IP"] = args.curl_resolve_ip
    os.environ["QWEN_API_TRANSPORT"] = args.api_transport
    os.environ["QWEN_API_TIMEOUT_SECONDS"] = str(args.api_timeout)
    os.environ["QWEN_API_MAX_RETRIES"] = str(args.api_retries)

    titles = args.stories or STORY_TITLES
    if args.limit is not None:
        titles = titles[: args.limit]

    output_dir = Path(args.output_dir)
    text_dir = output_dir / "texts"
    log_dir = output_dir / "logs"
    report_dir = output_dir / "reports"
    for directory in (text_dir, log_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)

    preflight = {"ok": True, "skipped": True}
    if not args.skip_generate and not args.no_preflight:
        preflight = qwen_preflight_direct(args.api_timeout)
        print(f"Qwen preflight ok={preflight['ok']}")

    generation_items = []
    for index, title in enumerate(titles, 1):
        filename = safe_filename(title)
        text_path = text_dir / f"{filename}.txt"
        log_path = log_dir / f"{filename}.txt"
        print(f"[generate {index}/{len(titles)}] {title}")

        generation = {"generated": text_path.exists(), "skipped": True, "preflight": preflight}
        if not args.skip_generate:
            if not preflight.get("ok"):
                generation = {
                    "generated": False,
                    "skipped": True,
                    "preflight": preflight,
                    "reason": "api_preflight_failed",
                }
            else:
                generation = generate_story(title, text_path, log_path, args.api_timeout, args.api_retries, args.api_transport, args.process_timeout)
                generation["preflight"] = preflight

        generation_items.append({
            "title": title,
            "filename": filename,
            "text_path": text_path,
            "log_path": log_path,
            "generation": generation,
        })
        print(f"  generated={generation.get('generated')} returncode={generation.get('returncode')} timed_out={generation.get('timed_out')}")

    project_main = load_main_quietly()
    reports = []
    for index, item in enumerate(generation_items, 1):
        title = item["title"]
        filename = item["filename"]
        text_path = item["text_path"]
        log_path = item["log_path"]
        generation = item["generation"]
        print(f"[audit {index}/{len(generation_items)}] {title}")

        if text_path.exists():
            text = text_path.read_text(encoding="utf-8")
            audit = static_audit(project_main, title, text)
            if args.llm_audit:
                audit["qwen_audit"] = qwen_audit(project_main, title, text)
        else:
            audit = {
                "title": title,
                "length": 0,
                "checks": {},
                "failed": ["generation_failed"],
                "pass_static": False,
            }

        report = {
            "title": title,
            "text_path": str(text_path),
            "log_path": str(log_path),
            "generation": generation,
            "audit": audit,
        }
        reports.append(report)
        (report_dir / f"{filename}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  pass={audit.get('pass_static')} length={audit.get('length')} failed={audit.get('failed')}")

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(reports),
        "passed": sum(1 for item in reports if item["audit"].get("pass_static")),
        "failed_titles": [item["title"] for item in reports if not item["audit"].get("pass_static")],
        "reports": reports,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary: {summary_path}")


if __name__ == "__main__":
    main_cli()
