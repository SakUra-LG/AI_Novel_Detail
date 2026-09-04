"""共享的 BGE-Large-ZH 嵌入模型。

检索素材和专业知识共用同一个模型实例，避免启动时重复占用内存。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer


MODEL_PATH = Path(__file__).resolve().parent / "bge_large_zh"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

tokenizer = AutoTokenizer.from_pretrained(str(MODEL_PATH))
model = AutoModel.from_pretrained(
    str(MODEL_PATH), use_safetensors=True
).to(DEVICE).eval()


def batch_vectorize(texts, batch_size: int = 32, max_length: int = 512):
    """将一组文本编码为 L2 归一化的 CLS 向量。"""
    all_embeddings = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        ).to(DEVICE)

        with torch.inference_mode():
            outputs = model(**inputs)
            embeddings = outputs.last_hidden_state[:, 0]
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
        all_embeddings.append(embeddings.cpu().numpy())

    return np.vstack(all_embeddings)


def vectorize_text(text: str, max_length: int = 512):
    """将单段文本编码为一行向量。"""
    return batch_vectorize([text], batch_size=1, max_length=max_length)
