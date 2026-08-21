"""Translate the accepted Chinese myth collection into lively English.

The translator is deliberately paragraph-aligned and resumable.  Each API result is
cached only after it passes structural checks; a finished story is assembled only
when every source paragraph has one non-empty English counterpart.  Qwen is tried
first and Groq is used as a fallback when Qwen is unavailable or out of quota.

Secrets are read from environment variables (QWEN_API_KEY / GROQ_API_KEY) and are
never written to the output folder, cache, manifest, or logs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE_DIR = BASE_DIR / "outputs" / "20个神话故事扩充最终版（2）" / "texts"
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs" / "20个神话故事扩充最终版（2）" / "英文版"

TITLE_MAP = {
    "00_总序": "00_Preface",
    "八仙过海": "Eight_Immortals_Cross_the_Sea",
    "北冥鲲鹏": "Kunpeng_of_the_Northern_Sea",
    "仓颉造字": "Cangjie_Creates_Chinese_Characters",
    "嫦娥奔月": "Change_Flies_to_the_Moon",
    "大禹治水": "Yu_the_Great_Tames_the_Flood",
    "伏羲画卦": "Fuxi_Creates_the_Eight_Trigrams",
    "后羿射日": "Hou_Yi_Shoots_the_Suns",
    "精卫填海": "Jingwei_Fills_the_Sea",
    "夸父追日": "Kuafu_Chases_the_Sun",
    "雷泽华胥": "Huaxu_at_Thunder_Marsh",
    "梁山伯与祝英台": "The_Butterfly_Lovers",
    "孟姜女哭长城": "Meng_Jiangnu_Weeps_at_the_Great_Wall",
    "哪吒闹海": "Nezha_Stirs_Up_the_Eastern_Sea",
    "牛郎织女": "The_Cowherd_and_the_Weaver_Girl",
    "女娲补天": "Nuwa_Mends_the_Sky",
    "女娲造人": "Nuwa_Creates_Humankind",
    "神农尝百草": "Shennong_Tastes_the_Hundred_Herbs",
    "吴刚伐桂": "Wu_Gang_Chops_the_Moon_Osmanthus",
    "西王母": "The_Queen_Mother_of_the_West",
    "愚公移山": "The_Foolish_Old_Man_Moves_the_Mountains",
}

GLOSSARY = """Use these spellings consistently:
阿满=Aman; 后羿=Hou Yi; 嫦娥=Chang'e; 女娲=Nüwa; 伏羲=Fuxi;
神农=Shennong; 大禹=Yu the Great; 哪吒=Nezha; 精卫=Jingwei;
夸父=Kuafu; 仓颉=Cangjie; 西王母=the Queen Mother of the West;
吴刚=Wu Gang; 梁山伯=Liang Shanbo; 祝英台=Zhu Yingtai;
孟姜女=Meng Jiangnü; 牛郎=the Cowherd; 织女=the Weaver Girl;
青竹简=green bamboo slips; 山海二十简=The Twenty Bamboo Slips of Mountains and Seas.
Keep culturally specific objects understandable from context. Do not add academic
footnotes, pinyin explanations, lectures, or translator's notes."""

SYSTEM_PROMPT = f"""You are an expert English adapter for funny, family-friendly
animated myth videos. Translate Chinese narrative prose into fluent, vivid English.

The result is entertainment for children and families and may later become a
roughly ten-minute short video. It must sound warm, quick, visual, and performable,
not academic, ceremonial, textbook-like, or stiff. Modern conversational wording
and light modern jokes are welcome when they fit the Chinese. Adapt wordplay so the
joke lands naturally in English; do not explain the joke. Keep danger clear without
making it gruesome. Preserve emotional scenes and do not force jokes into grief.

Fidelity rules: translate every paragraph completely, in order. Do not summarize,
cut, merge, pad, invent new events, change who performs an action, or alter the
ending. Preserve dialogue, visible action, cause and effect, and paragraph breaks.
Write natural English rather than tracing Chinese syntax. Use curly or straight
English quotation marks consistently. Never output Chinese characters.

{GLOSSARY}

The input paragraphs are numbered [P0001], [P0002], and so on. Return only the
English paragraphs with the same markers, in the same order. Put each marker at the
start of its own line, followed by that paragraph's complete English translation.
Do not repeat the Chinese. Do not use JSON or Markdown fences. Example:
[P0001] Complete English paragraph one.
[P0002] Complete English paragraph two."""

HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
META_MARKERS = (
    "as an ai", "translation note", "translator's note", "here is the translation",
    "the following translation",
)
GROQ_MODEL_CURSOR = 0
GROQ_LAST_CALL: dict[str, float] = {}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\r?\n\s*\r?\n", text) if part.strip()]


def normalize_english_paragraph(text: str) -> str:
    """Keep one source item as exactly one physical output paragraph."""
    return re.sub(r"\s*\r?\n\s*", " ", text or "").strip()


def apply_story_specific_fixes(title: str, text: str) -> str:
    """Resolve high-confidence myth terms that generic models can mistranslate."""
    fixed = normalize_english_paragraph(text)
    if title == "后羿射日":
        # In this story 日 refers to a solar body, not a calendar day. These
        # forms were observed in otherwise valid cached translations.
        fixed = re.sub(
            r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|last) days?\b",
            lambda match: match.group(1) + " sun",
            fixed,
            flags=re.I,
        )
        fixed = re.sub(r"\bfirst three days\b", "first three suns", fixed, flags=re.I)
        fixed = re.sub(r"\bremaining four days\b", "remaining four suns", fixed, flags=re.I)
        fixed = re.sub(r"\blast two days\b", "last two suns", fixed, flags=re.I)
        fixed = re.sub(r"\bten days of heat\b", "ten suns' heat", fixed, flags=re.I)
        fixed = re.sub(r"\bafter the fifth sunset\b", "after the fifth sun fell", fixed, flags=re.I)
        fixed = re.sub(r"\bafter the sixth sunset\b", "after the sixth sun fell", fixed, flags=re.I)
    elif title == "八仙过海":
        fixed = fixed.replace(
            "The fish's tails splashed out a fine rhythm,",
            "The fishes' tails splashed out a fine, jaunty rhythm.",
        )
    elif title == "伏羲画卦":
        fixed = fixed.replace(
            "he gave a slight nod, signaling him to…",
            "he gave a slight nod, signaling him to continue the demonstration.",
        )
        fixed = fixed.replace("…continue. The crowd laughed.", "The crowd laughed.")
    elif title == "雷泽华胥":
        fixed = re.sub(r"\bHua Xue\b", "Huaxu", fixed, flags=re.I)
        fixed = fixed.replace(
            "Within her womb, the one about to be born was the legendary Fuxi –",
            "Within her womb was the child who would one day be known as Fuxi.",
        )
    elif title == "夸父追日" and fixed == "Finally,":
        fixed = "At last, something changed on the horizon."
    return fixed


def make_chunks(paragraphs: list[str], target_chars: int) -> list[list[tuple[int, str]]]:
    chunks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    current_chars = 0
    for index, paragraph in enumerate(paragraphs):
        size = len(paragraph)
        if current and current_chars + size > target_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append((index, paragraph))
        current_chars += size
    if current:
        chunks.append(current)
    return chunks


def clean_json_reply(reply: str) -> dict:
    text = re.sub(r"<think>[\s\S]*?</think>", "", reply or "", flags=re.I).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model response contains no JSON object")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model response JSON is not an object")
    return data


def parse_translation_reply(reply: str, expected_count: int) -> list[str]:
    """Parse marker protocol, retaining backward compatibility with JSON replies."""
    text = re.sub(r"<think>[\s\S]*?</think>", "", reply or "", flags=re.I).strip()
    text = re.sub(r"^```(?:text|markdown|json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()
    marker = re.compile(r"(?m)^\s*(?:\[P(\d{1,4})\]|<<<P(\d{1,4})>>>)\s*")
    matches = list(marker.finditer(text))
    if matches:
        found: dict[int, str] = {}
        for pos, match in enumerate(matches):
            number = int(match.group(1) or match.group(2))
            end = matches[pos + 1].start() if pos + 1 < len(matches) else len(text)
            found[number] = text[match.end() : end].strip()
        expected = list(range(1, expected_count + 1))
        if sorted(found) != expected:
            raise ValueError(f"paragraph markers mismatch: expected 1..{expected_count}, got {sorted(found)}")
        return [found[number] for number in expected]
    # Old cached/test prompts and especially compliant models may still return JSON.
    data = clean_json_reply(text)
    translations = data.get("translations")
    if not isinstance(translations, list):
        raise ValueError("response contains neither paragraph markers nor a translations array")
    return translations


def validate_translations(source: list[str], translated: object) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not isinstance(translated, list):
        return False, ["translations is not an array"]
    if len(translated) != len(source):
        return False, [f"paragraph count mismatch: expected {len(source)}, got {len(translated)}"]
    for idx, (cn, en) in enumerate(zip(source, translated), 1):
        if not isinstance(en, str) or not en.strip():
            issues.append(f"paragraph {idx} is empty")
            continue
        en = en.strip()
        han = len(HAN_RE.findall(en))
        if han:
            issues.append(f"paragraph {idx} retains {han} Chinese character(s)")
        lowered = en.lower()
        if any(marker in lowered for marker in META_MARKERS):
            issues.append(f"paragraph {idx} contains translator/meta language")
        # Very low ratios reliably signal omissions. Short dialogue such as
        # “为何是口？” legitimately becomes “Why a mouth?”, so it must not be
        # forced through the minimum used for full narrative paragraphs.
        minimum_length = max(5, len(cn) * 0.30) if len(cn) <= 20 else max(20, len(cn) * 0.38)
        if len(en) < minimum_length:
            issues.append(f"paragraph {idx} appears substantially shortened")
    return not issues, issues


def detect_proxy() -> str:
    configured = os.getenv("GROQ_HTTPS_PROXY", "").strip()
    if configured:
        return configured
    try:
        with socket.create_connection(("127.0.0.1", 7897), timeout=0.35):
            return "http://127.0.0.1:7897"
    except OSError:
        return ""


def curl_json(url: str, headers: list[str], payload: dict, timeout: int, proxy: str = "") -> tuple[int, dict]:
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".json") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            temp_path = handle.name
        cmd = ["curl.exe", "-sS", "--connect-timeout", "15", "--max-time", str(timeout)]
        if proxy:
            cmd += ["--proxy", proxy]
        cmd += ["-X", "POST", url]
        for header in headers:
            cmd += ["-H", header]
        cmd += ["--data-binary", "@" + temp_path, "-w", "\n__HTTP_STATUS__:%{http_code}"]
        done = None
        for network_attempt in range(1, 4):
            done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout + 10)
            if not done.returncode:
                break
            if network_attempt < 3:
                time.sleep(2)
        if done is None or done.returncode:
            raise RuntimeError(f"curl exited {getattr(done, 'returncode', 'unknown')}: {(getattr(done, 'stderr', '') or '')[:300]}")
        body, marker, status = (done.stdout or "").rpartition("\n__HTTP_STATUS__:")
        if not marker:
            raise RuntimeError("HTTP response did not contain a status marker")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"HTTP {status}, non-JSON response: {body[:300]}") from exc
        return int(status), data
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def qwen_key() -> str:
    key = os.getenv("QWEN_API_KEY", "").strip() or os.getenv("DASHSCOPE_API_KEY", "").strip()
    if key:
        return key
    try:
        from config import API_Key_QW  # local project configuration, never serialized
        return str(API_Key_QW).strip()
    except Exception:
        return ""


def call_qwen(messages: list[dict], max_tokens: int, timeout: int, model: str) -> str:
    key = qwen_key()
    if not key:
        raise RuntimeError("Qwen API key is not configured")
    payload = {
        "model": model,
        "input": {"messages": messages},
        "parameters": {
            "temperature": 0.45,
            "top_p": 0.82,
            "repetition_penalty": 1.05,
            "result_format": "message",
            "max_tokens": max_tokens,
        },
    }
    status, data = curl_json(
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
        ["Authorization: Bearer " + key, "Content-Type: application/json"],
        payload,
        timeout,
    )
    if status < 200 or status >= 300:
        message = data.get("message") or data.get("code") or json.dumps(data, ensure_ascii=False)[:300]
        raise RuntimeError(f"Qwen HTTP {status}: {message}")
    choices = data.get("output", {}).get("choices", [])
    if not choices:
        raise RuntimeError("Qwen returned no completion choice")
    return choices[0].get("message", {}).get("content", "")


def call_groq(messages: list[dict], max_tokens: int, timeout: int, model: str) -> str:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    # Groq applies TPM independently per model.  Keeping a small per-model gap
    # prevents a successful long translation from making the next call fail.
    min_interval = max(0.0, float(os.getenv("GROQ_MIN_MODEL_INTERVAL", "45")))
    last_call = GROQ_LAST_CALL.get(model, 0.0)
    remaining = min_interval - (time.monotonic() - last_call)
    if remaining > 0:
        print(f"    waiting {remaining:.1f}s for {model} TPM window...")
        time.sleep(remaining)
    GROQ_LAST_CALL[model] = time.monotonic()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.45,
        "top_p": 0.82,
        "max_completion_tokens": max_tokens,
    }
    if model.startswith("qwen/"):
        payload.update({"reasoning_effort": "none", "include_reasoning": False})
    elif model.startswith("openai/gpt-oss"):
        payload.update({"reasoning_effort": "low", "include_reasoning": False})
    status, data = curl_json(
        "https://api.groq.com/openai/v1/chat/completions",
        ["Authorization: Bearer " + key, "Content-Type: application/json", "User-Agent: Mozilla/5.0"],
        payload,
        timeout,
        proxy=detect_proxy(),
    )
    if status < 200 or status >= 300:
        error = data.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(f"Groq HTTP {status}: {message or json.dumps(data)[:300]}")
    return data["choices"][0]["message"]["content"]


def translate_chunk(
    paragraphs: list[str], *, max_tokens: int, timeout: int, qwen_model: str,
    groq_model: str, retries: int,
) -> tuple[list[str], str]:
    user_payload = "\n\n".join(f"[P{index:04d}] {paragraph}" for index, paragraph in enumerate(paragraphs, 1))
    base_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Translate every numbered paragraph below:\n\n" + user_payload},
    ]
    errors: list[str] = []
    global GROQ_MODEL_CURSOR
    providers = []
    if os.getenv("DISABLE_QWEN", "").strip().lower() not in {"1", "true", "yes"}:
        providers.append(("qwen:" + qwen_model, lambda msgs: call_qwen(msgs, max_tokens, timeout, qwen_model)))
    groq_models = [item.strip() for item in groq_model.split(",") if item.strip()]
    if groq_models:
        offset = GROQ_MODEL_CURSOR % len(groq_models)
        groq_models = groq_models[offset:] + groq_models[:offset]
        GROQ_MODEL_CURSOR += 1
    for current_model in groq_models:
        providers.append((
            "groq:" + current_model,
            lambda msgs, selected=current_model: call_groq(msgs, max_tokens, timeout, selected),
        ))
    for provider_name, caller in providers:
        if provider_name.startswith("groq:") and not os.getenv("GROQ_API_KEY", "").strip():
            continue
        messages = list(base_messages)
        for attempt in range(1, retries + 1):
            try:
                reply = caller(messages)
                translations = parse_translation_reply(reply, len(paragraphs))
                valid, issues = validate_translations(paragraphs, translations)
                if valid:
                    return [normalize_english_paragraph(item) for item in translations], provider_name
                raise ValueError("; ".join(issues[:8]))
            except Exception as exc:
                safe_error = re.sub(r"(?:sk|gsk)_[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]+", "[REDACTED]", str(exc))
                errors.append(f"{provider_name} attempt {attempt}: {safe_error}")
                if attempt < retries:
                    match = re.search(r"try again in (?:(\d+)m)?([0-9.]+)s", safe_error, flags=re.I)
                    if match:
                        delay = int(match.group(1) or 0) * 60 + float(match.group(2)) + 1
                    else:
                        delay = min(8, 2 ** attempt)
                    # A TPD reset can be tens of minutes away. Sleeping inside one
                    # story makes a resumable batch look hung and prevents another
                    # provider from taking over. Only short TPM waits are retried;
                    # long waits immediately advance to the next configured model.
                    if delay > 60:
                        print(f"    {provider_name} reset is {delay:.0f}s away; switching model now.")
                        break
                    time.sleep(delay)
        print(f"    {provider_name} unavailable for this chunk; trying fallback.")
    raise RuntimeError(" | ".join(errors[-4:]))


def translate_story(
    source_path: Path, output_dir: Path, work_dir: Path, *, chunk_chars: int,
    max_tokens: int, timeout: int, qwen_model: str, groq_model: str, retries: int,
) -> dict:
    source_text = source_path.read_text(encoding="utf-8-sig").strip()
    paragraphs = split_paragraphs(source_text)
    chunks = make_chunks(paragraphs, chunk_chars)
    stem_en = TITLE_MAP.get(source_path.stem)
    if not stem_en:
        raise KeyError(f"No English filename mapping for {source_path.stem}")
    story_work = work_dir / stem_en
    story_work.mkdir(parents=True, exist_ok=True)
    translated: list[str | None] = [None] * len(paragraphs)
    providers: list[str] = []

    for chunk_number, chunk in enumerate(chunks, 1):
        indexes = [item[0] for item in chunk]
        source_parts = [item[1] for item in chunk]
        digest = sha256_text("\n\n".join(source_parts))
        cache_path = story_work / f"chunk_{chunk_number:03d}.json"
        cached = None
        if cache_path.exists():
            try:
                candidate = json.loads(cache_path.read_text(encoding="utf-8"))
                valid, _ = validate_translations(source_parts, candidate.get("translations"))
                if candidate.get("source_sha256") == digest and valid:
                    cached = candidate
            except Exception:
                cached = None
        if cached:
            result = [normalize_english_paragraph(item) for item in cached["translations"]]
            provider = cached.get("provider", "cached")
            print(f"  [{chunk_number}/{len(chunks)}] cache hit")
        else:
            print(f"  [{chunk_number}/{len(chunks)}] translating {len(source_parts)} paragraph(s)...")
            result, provider = translate_chunk(
                source_parts, max_tokens=max_tokens, timeout=timeout,
                qwen_model=qwen_model, groq_model=groq_model, retries=retries,
            )
            cache_data = {
                "source_sha256": digest,
                "source_paragraph_indexes": indexes,
                "provider": provider,
                "translations": result,
            }
            cache_path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")
        providers.append(provider)
        for index, English in zip(indexes, result):
            translated[index] = apply_story_specific_fixes(source_path.stem, English)

    if any(item is None for item in translated):
        raise RuntimeError(f"{source_path.stem}: incomplete paragraph assembly")
    final_paragraphs = [str(item) for item in translated]
    valid, issues = validate_translations(paragraphs, final_paragraphs)
    if not valid:
        raise RuntimeError(f"{source_path.stem}: final validation failed: {'; '.join(issues[:12])}")
    final_text = "\n\n".join(final_paragraphs).strip() + "\n"
    output_path = output_dir / (stem_en + ".txt")
    output_path.write_text(final_text, encoding="utf-8")
    return {
        "source_file": source_path.name,
        "english_file": output_path.name,
        "source_sha256": sha256_text(source_text),
        "english_sha256": sha256_text(final_text.strip()),
        "source_paragraphs": len(paragraphs),
        "english_paragraphs": len(final_paragraphs),
        "source_characters": len(source_text),
        "english_words": len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", final_text)),
        "remaining_chinese_characters": len(HAN_RE.findall(final_text)),
        "chunks": len(chunks),
        "providers": dict((name, providers.count(name)) for name in sorted(set(providers))),
        "passed": True,
    }


def audit_existing(source_dir: Path, output_dir: Path) -> dict:
    records = []
    for source_path in sorted(source_dir.glob("*.txt"), key=lambda p: p.name):
        stem_en = TITLE_MAP.get(source_path.stem, "")
        output_path = output_dir / (stem_en + ".txt")
        source_paragraphs = split_paragraphs(source_path.read_text(encoding="utf-8-sig"))
        if not output_path.exists():
            records.append({"source_file": source_path.name, "english_file": output_path.name, "passed": False, "issues": ["missing output"]})
            continue
        text = output_path.read_text(encoding="utf-8-sig")
        english_paragraphs = split_paragraphs(text)
        issues = []
        if len(source_paragraphs) != len(english_paragraphs):
            issues.append("paragraph count mismatch")
        else:
            structurally_valid, paragraph_issues = validate_translations(source_paragraphs, english_paragraphs)
            if not structurally_valid:
                issues.extend(paragraph_issues[:20])
        han_count = len(HAN_RE.findall(text))
        if han_count:
            issues.append(f"contains {han_count} Chinese character(s)")
        marker_count = len(re.findall(r"\[P\d{1,4}\]|<<<P\d{1,4}>>>", text))
        if marker_count:
            issues.append(f"contains {marker_count} internal paragraph marker(s)")
        lowered = text.lower()
        meta_hits = sorted(marker for marker in META_MARKERS if marker in lowered)
        if meta_hits:
            issues.append("contains translator/meta language: " + ", ".join(meta_hits))
        if len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", text)) < 100:
            issues.append("English output is unexpectedly short")
        normalized_paragraphs = [re.sub(r"\s+", " ", part).strip().lower() for part in english_paragraphs]
        repeated = len(normalized_paragraphs) - len(set(normalized_paragraphs))
        normalized_source = [re.sub(r"\s+", " ", part).strip() for part in source_paragraphs]
        source_repeated = len(normalized_source) - len(set(normalized_source))
        added_repeated = max(0, repeated - source_repeated)
        if added_repeated:
            issues.append(f"contains {added_repeated} repeated paragraph(s) not present in source")
        records.append({
            "source_file": source_path.name,
            "english_file": output_path.name,
            "source_sha256": sha256_text(source_path.read_text(encoding="utf-8-sig").strip()),
            "english_sha256": sha256_text(text.strip()),
            "source_paragraphs": len(source_paragraphs),
            "english_paragraphs": len(english_paragraphs),
            "english_words": len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", text)),
            "remaining_chinese_characters": han_count,
            "internal_marker_count": marker_count,
            "source_repeated_paragraphs": source_repeated,
            "repeated_paragraphs": repeated,
            "added_repeated_paragraphs": added_repeated,
            "passed": not issues,
            "issues": issues,
        })
    story_records = [record for record in records if record["source_file"] != "00_总序.txt"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_directory": str(source_dir.resolve()),
        "output_directory": str(output_dir.resolve()),
        "source_txt_count": len(records),
        "story_count": len(story_records),
        "passed_story_count": sum(bool(r["passed"]) for r in story_records),
        "preface_passed": next((bool(r["passed"]) for r in records if r["source_file"] == "00_总序.txt"), False),
        "total_english_words": sum(int(r.get("english_words", 0)) for r in story_records),
        "passed": len(story_records) == 20 and all(r["passed"] for r in records),
        "files": records,
    }


def write_readme(output_dir: Path, manifest: dict) -> None:
    text = f"""# 英文版说明

本目录由 `Detail/translate_myths_to_english.py` 从已验收的中文“20个神话故事扩充最终版（2）/texts”逐段翻译生成。

- 故事数量：{manifest['story_count']} 篇（另含英文总序）
- 通过核验：{manifest['passed_story_count']} 篇
- 英文总词数：{manifest['total_english_words']:,}
- 翻译定位：轻松、幽默、儿童及家庭友好、适合短视频改编
- 翻译原则：完整保留事件、人物行动、对白、情感和段落顺序；笑点采用自然英文表达，不使用学术论文式语言
- 完整性检查：中英文自然段逐一对应，英文成稿不得残留汉字

`translation_manifest.json` 记录逐篇文件映射、段落数、词数与验收结果；`.translation_cache` 是断点续跑缓存，可保留以便继续或修订。
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Translate the final Chinese myth collection into lively English")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--chunk-chars", type=int, default=1900)
    parser.add_argument("--max-tokens", type=int, default=6500)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--qwen-model", default=os.getenv("QWEN_TRANSLATION_MODEL", "qwen-plus"))
    parser.add_argument(
        "--groq-model",
        default=os.getenv(
            "GROQ_TRANSLATION_MODEL",
            "qwen/qwen3.6-27b,openai/gpt-oss-120b,llama-3.3-70b-versatile",
        ),
        help="One Groq model or a comma-separated rotation list",
    )
    parser.add_argument("--only", action="append", default=[], help="Chinese source stem to translate; repeat as needed")
    parser.add_argument("--audit-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.audit_only:
        manifest = audit_existing(source_dir, output_dir)
        (output_dir / "translation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        write_readme(output_dir, manifest)
        print(json.dumps({k: manifest[k] for k in ("story_count", "passed_story_count", "preface_passed", "total_english_words", "passed")}, ensure_ascii=False))
        return 0 if manifest["passed"] else 1

    files = sorted(source_dir.glob("*.txt"), key=lambda p: p.name)
    if args.only:
        selected = set(args.only)
        files = [path for path in files if path.stem in selected]
    unknown = [path.stem for path in files if path.stem not in TITLE_MAP]
    if unknown:
        raise RuntimeError("Missing English filename mapping: " + ", ".join(unknown))
    work_dir = output_dir / ".translation_cache"
    work_dir.mkdir(parents=True, exist_ok=True)
    run_records = []
    for number, source_path in enumerate(files, 1):
        print(f"[{number}/{len(files)}] {source_path.stem}")
        record = translate_story(
            source_path, output_dir, work_dir,
            chunk_chars=max(500, args.chunk_chars), max_tokens=max(1000, args.max_tokens),
            timeout=max(30, args.timeout), qwen_model=args.qwen_model,
            groq_model=args.groq_model, retries=max(1, args.retries),
        )
        run_records.append(record)
        print(f"  wrote {record['english_file']} ({record['english_words']:,} words)")
    run_path = output_dir / "last_translation_run.json"
    run_path.write_text(json.dumps({"files": run_records}, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = audit_existing(source_dir, output_dir)
    (output_dir / "translation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readme(output_dir, manifest)
    print(json.dumps({k: manifest[k] for k in ("story_count", "passed_story_count", "preface_passed", "total_english_words", "passed")}, ensure_ascii=False))
    return 0 if manifest["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
