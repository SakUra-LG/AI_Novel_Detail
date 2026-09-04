"""运行配置。

密钥只从环境变量读取，避免凭证再次进入 Git 历史。
"""

import os


API_Key_QW = (
    os.getenv("DASHSCOPE_API_KEY", "").strip()
    or os.getenv("QWEN_API_KEY", "").strip()
)
MAX_TOKENS = 8192


def require_api_key() -> str:
    """返回 DashScope 密钥；未配置时给出可操作的错误信息。"""
    if not API_Key_QW:
        raise RuntimeError(
            "未配置通义千问 API 密钥。请先设置环境变量 "
            "DASHSCOPE_API_KEY（也兼容 QWEN_API_KEY）。"
        )
    return API_Key_QW
