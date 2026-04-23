import os
import sys
import dashscope


def _prepare_import_path():
    """
    允许从项目根目录直接运行本脚本。
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    detail_dir = os.path.dirname(current_dir)
    if detail_dir not in sys.path:
        sys.path.insert(0, detail_dir)
    return current_dir


def _call_qwen(messages, api_key, max_retries=3):
    dashscope.api_key = api_key
    last_error = None
    for _ in range(max_retries):
        try:
            response = dashscope.Generation.call(
                model=dashscope.Generation.Models.qwen_turbo,
                messages=messages,
                temperature=0.85,
                top_p=0.9,
                repetition_penalty=1.15,
                result_format="message",
                max_tokens=1200,
            )
            if "output" in response and "choices" in response["output"]:
                return response["output"]["choices"][0]["message"]["content"].strip()
            last_error = f"返回格式异常: {response}"
        except Exception as e:
            last_error = str(e)
    return f"生成失败：{last_error}"


def _build_level_prompt(user_scene_prompt: str, level: int) -> str:
    level_rules = {
        1: "轻微幽默：基本稳重，仅有零星轻吐槽。",
        2: "偏轻幽默：有少量自然调侃，整体仍克制。",
        3: "中等幽默：幽默和剧情平衡，能明显感到好笑。",
        4: "偏强幽默：对白互怼和反差笑点明显增多。",
        5: "最强幽默：笑点密集，互怼拆台明显，但不破坏神话逻辑。"
    }
    return f"""
请基于下面这个“神话改写片段需求”，只写一个【单段场景示例】（不是完整故事）：
{user_scene_prompt}

幽默等级要求：{level}级
等级说明：{level_rules[level]}

硬性要求：
1. 只写这一个片段，长度约350~650字。
2. 保留神话语境，不要写成现代职场段子。
3. 从1级到5级要有明显梯度：级别越高，吐槽/互怼/反差笑点越多。
4. 只输出正文，不要解释。
""".strip()


def _save_outputs(outputs: dict, user_scene_prompt: str, current_dir: str):
    safe_name = user_scene_prompt.strip()[:30] if user_scene_prompt.strip() else "神话片段"
    for ch in '\\/:*?"<>|':
        safe_name = safe_name.replace(ch, "_")
    if not safe_name:
        safe_name = "神话片段"

    output_root = os.path.join(current_dir, "output")
    target_dir = os.path.join(output_root, safe_name)
    os.makedirs(target_dir, exist_ok=True)
    for level, text in outputs.items():
        path = os.path.join(target_dir, f"幽默强度{level}级_片段示例.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text or "")
    return target_dir


def main():
    current_dir = _prepare_import_path()
    from config import API_Key_QW

    user_scene_prompt = input("请输入要改写的神话情节片段提示词：").strip()
    if not user_scene_prompt:
        print("输入为空，已取消。")
        return

    outputs = {}
    for level in range(1, 6):
        print(f"正在生成幽默强度{level}级片段示例...")
        messages = [
            {"role": "system", "content": "你是神话改写作者，擅长同一情节的多等级幽默改写。"},
            {"role": "user", "content": _build_level_prompt(user_scene_prompt, level)},
        ]
        outputs[level] = _call_qwen(messages, API_Key_QW)

    output_dir = _save_outputs(outputs, user_scene_prompt, current_dir)
    print("\n=== 片段示例生成完成 ===")
    print(f"输出目录：{output_dir}")

    for level in range(1, 6):
        print(f"\n--- 幽默强度{level}级（片段示例）---\n")
        print(outputs[level])


if __name__ == "__main__":
    main()
