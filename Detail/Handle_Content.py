import torch
import re
import numpy as np
import json
from transformers import AutoTokenizer, AutoModel

# 配置
model_path = "./bge_large_zh"
device = "cuda" if torch.cuda.is_available() else "cpu"

# 加载模型
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModel.from_pretrained(model_path, use_safetensors=True).to(device).eval()


def batch_vectorize(texts, batch_size=32):
    """批量向量化文本"""
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        ).to(device)

        with torch.inference_mode():
            outputs = model(**inputs)
            embeddings = outputs.last_hidden_state[:, 0]
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

        all_embeddings.append(embeddings.cpu().numpy())

    return np.vstack(all_embeddings)


def read_text_from_file(file_path):
    """读取文件并返回内容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        print(f"错误：文件 {file_path} 不存在")
        exit(1)
    except Exception as e:
        print(f"读取文件时出错: {e}")
        exit(1)


def parse_articles(content):
    """
    解析 txt 文件，提取每个大类下的段落。
    返回: [{"theme": "玄幻斗法", "content": "寒霜骤然凝结..."}, ...]
    """
    articles = []
    # 找到大标题，例如 "1.玄幻斗法"
    blocks = re.split(r"\n\d+\.", content)
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # 第一行是主题
        lines = block.splitlines()
        theme = lines[0].strip("：:")

        # 其余行是多条段落，每条用引号括起来
        paragraphs = re.findall(r'“(.*?)”|"(.*?)"', block, re.DOTALL)
        for p in paragraphs:
            text = p[0] if p[0] else p[1]
            if text.strip():
                articles.append({
                    "theme": theme,
                    "content": text.strip()
                })
    return articles


# 主流程
if __name__ == "__main__":
    # 读取文本内容
    content = read_text_from_file('knowledgeBase/Content.txt')

    # 解析文本 -> 文章列表
    articles = parse_articles(content)

    if not articles:
        print("没有提取到有效的文章，程序退出！")
        exit()

    print(f"成功解析 {len(articles)} 条文本")

    # 提取每条的 theme+content 作为向量化输入
    texts = [f"{a['theme']}：{a['content']}" for a in articles]

    # 批量向量化
    try:
        vectors = batch_vectorize(texts)
        print(f"向量化完成，特征维度: {vectors.shape}")
    except Exception as e:
        print(f"向量化过程中出错: {e}")
        exit(1)

    # 保存结果
    try:
        np.save('knowledgeBase/features_Theme.npy', vectors)

        with open('knowledgeBase/themes_Content.json', 'w', encoding='utf-8') as f:
            json.dump({
                "articles": articles,
                "count": len(articles)
            }, f, ensure_ascii=False, indent=4)

        print(f"成功保存文本向量和内容")
    except Exception as e:
        print(f"保存结果时出错: {e}")
        exit(1)
