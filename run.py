"""项目统一命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成幽默神话改写或带反转的武打细节场景"
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    for mode, help_text in (
        ("myth", "生成单篇幽默神话改写"),
        ("humor-levels", "生成同一神话的 1~5 级幽默版本"),
        ("fight", "生成包含压制、绝境、转机和反杀的武打场景"),
    ):
        command = subparsers.add_parser(mode, help=help_text)
        command.add_argument("--prompt", required=True, help="具体创作要求")
        command.add_argument(
            "--output",
            type=Path,
            help="可选：把正文写入指定 UTF-8 文本文件",
        )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from main import (
        generate_fight_scene_with_reversal,
        generate_myth_rewrite,
        generate_myth_rewrite_humor_levels,
    )

    if args.mode == "myth":
        result = generate_myth_rewrite(args.prompt)
    elif args.mode == "fight":
        result = generate_fight_scene_with_reversal(args.prompt)
    else:
        versions = generate_myth_rewrite_humor_levels(args.prompt)
        result = "\n\n".join(
            f"--- 幽默强度{level}级 ---\n{versions.get(level, '')}"
            for level in range(1, 6)
        )

    print("\n=== 创作结果 ===\n")
    print(result)

    if args.output:
        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
        print(f"\n已保存到：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
