import re
import numpy as np
import json
import os
from embedding_model import batch_vectorize

# 配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledgeBase")


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
    content = read_text_from_file(os.path.join(KNOWLEDGE_DIR, 'Content.txt'))

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
        vectors = batch_vectorize(texts, batch_size=32, max_length=512)
        print(f"向量化完成，特征维度: {vectors.shape}")
    except Exception as e:
        print(f"向量化过程中出错: {e}")
        exit(1)

    # 保存结果
    try:
        np.save(os.path.join(KNOWLEDGE_DIR, 'features_Theme.npy'), vectors)

        with open(os.path.join(KNOWLEDGE_DIR, 'themes_Content.json'), 'w', encoding='utf-8') as f:
            json.dump({
                "articles": articles,
                "count": len(articles)
            }, f, ensure_ascii=False, indent=4)

        print(f"成功保存文本向量和内容")
    except Exception as e:
        print(f"保存结果时出错: {e}")
        exit(1)
