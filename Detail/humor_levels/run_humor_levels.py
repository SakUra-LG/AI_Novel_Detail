import os
import sys


def _prepare_import_path():
    """
    允许从 Detail/humor_levels 目录直接运行本脚本。
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    detail_dir = os.path.dirname(current_dir)
    if detail_dir not in sys.path:
        sys.path.insert(0, detail_dir)
    return current_dir, detail_dir


def main():
    current_dir, _ = _prepare_import_path()

    # 延迟导入，确保 sys.path 已准备好
    from main import generate_myth_rewrite
    from humor_levels.humor_level_generator import generate_humor_level_versions

    prompt = input("请输入要改写的神话故事提示词：").strip()
    if not prompt:
        print("输入为空，已取消。")
        return

    output_root = os.path.join(current_dir, "output")
    outputs, output_dir = generate_humor_level_versions(prompt, generate_myth_rewrite, output_root)

    print("\n=== 幽默强度1~5级已生成 ===")
    print(f"输出目录：{output_dir}\n")

    for level in range(1, 6):
        print(f"\n--- 幽默强度{level}级 ---\n")
        print(outputs.get(level, ""))


if __name__ == "__main__":
    main()
