import json
import shutil
from datetime import datetime
from pathlib import Path

from batch_myth_quality_audit import STORY_TITLES, load_main_quietly, static_audit


CURRENT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = CURRENT_DIR / "outputs"
FINAL_DIR = OUTPUT_ROOT / "myth_final_18_houyi_quality_20260712"

SOURCE_DIRS = {
    "八仙过海": "myth_final_group_A_retry_20260711",
    "北冥鲲鹏": "myth_final_deepfix7_beiming_controlled_20260712",
    "仓颉造字": "myth_final_group_A_retry2_20260711",
    "嫦娥奔月": "myth_final_group_A_retry4_20260712",
    "伏羲画卦": "myth_final_group_B_retry2_20260711",
    "后羿射日": "myth_final_group_B_retry_20260711",
    "精卫填海": "myth_final_deepfix_jingwei_controlled_20260712",
    "夸父追日": "myth_quality_v25_tenpart_kuafu_20260711",
    "雷泽华胥": "myth_final_deepfix_leize_20260712",
    "梁山伯与祝英台": "myth_final_group_C_retry_20260711",
    "孟姜女哭长城": "myth_final_group_C_retry_20260711",
    "牛郎织女": "myth_final_group_C_retry_20260711",
    "女娲补天": "myth_final_group_C_retry_20260711",
    "女娲造人": "myth_final_group_C_retry_20260711",
    "神农尝百草": "myth_final_group_D_retry2_20260711",
    "吴刚伐桂": "myth_final_group_D_retry2_20260711",
    "西王母": "myth_final_deepfix_xiwangmu_20260712",
    "愚公移山": "myth_final_group_D_retry2_20260711",
}


def main() -> int:
    main_module = load_main_quietly()
    for child in ("texts", "logs", "reports"):
        (FINAL_DIR / child).mkdir(parents=True, exist_ok=True)

    reports = []
    missing = []
    for title in STORY_TITLES:
        source_name = SOURCE_DIRS[title]
        source = OUTPUT_ROOT / source_name
        text_source = source / "texts" / f"{title}.txt"
        log_source = source / "logs" / f"{title}.txt"
        if not text_source.exists() or not log_source.exists():
            missing.append(title)
            continue

        text_target = FINAL_DIR / "texts" / f"{title}.txt"
        log_target = FINAL_DIR / "logs" / f"{title}.txt"
        shutil.copy2(log_source, log_target)
        myth_core = main_module.find_myth_core(f"改写神话故事{title}，要求有幽默")
        text = main_module.clean_story_postprocess(
            text_source.read_text(encoding="utf-8"), myth_core
        )
        text_target.write_text(text, encoding="utf-8")
        audit = static_audit(main_module, title, text)
        report = {
            "title": title,
            "source_dir": source_name,
            "text_path": str(text_target.relative_to(CURRENT_DIR.parent)),
            "log_path": str(log_target.relative_to(CURRENT_DIR.parent)),
            "audit": audit,
        }
        reports.append(report)
        (FINAL_DIR / "reports" / f"{title}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "total_expected": len(STORY_TITLES),
        "total_copied": len(reports),
        "passed": sum(1 for report in reports if report["audit"]["pass_static"]),
        "missing": missing,
        "failed_titles": [
            report["title"] for report in reports if not report["audit"]["pass_static"]
        ],
        "reports": reports,
    }
    (FINAL_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: summary[key] for key in ("total_copied", "passed", "missing", "failed_titles")}, ensure_ascii=False))
    return 0 if not missing and summary["passed"] == len(STORY_TITLES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
