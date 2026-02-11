import torch
import numpy as np
import json
from transformers import AutoTokenizer, AutoModel
from sklearn.metrics.pairwise import cosine_similarity

# 配置
model_path = "./bge_large_zh"
device = "cuda" if torch.cuda.is_available() else "cpu"

# 加载模型
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModel.from_pretrained(model_path, use_safetensors=True).to(device).eval()


def vectorize_text(text):
    """将文本转换为向量"""
    inputs = tokenizer(
        text,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt"
    ).to(device)

    with torch.inference_mode():
        outputs = model(**inputs)
        embeddings = outputs.last_hidden_state[:, 0]
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

    return embeddings.cpu().numpy()


def load_knowledge_base():
    """加载知识库（向量 + 文章内容）"""
    try:
        # 加载主题向量
        theme_vectors = np.load('knowledgeBase/features_Theme.npy')

        # 加载文章内容（json 文件）
        with open('knowledgeBase/themes_Content.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            articles = data.get("articles", [])

        # 验证一致性
        if len(articles) != theme_vectors.shape[0]:
            print(f"数据不匹配：文章数({len(articles)}) ≠ 向量数({theme_vectors.shape[0]})")
            return None, None

        return theme_vectors, articles
    except Exception as e:
        print(f"加载知识库时出错: {e}")
        return None, None


def find_most_similar(query_vector, theme_vectors, articles):
    """查找最相似的文章段落"""
    similarities = cosine_similarity(query_vector, theme_vectors)[0]
    top_indices = np.argsort(similarities)[::-1]  # 按相似度降序排列

    results = []
    for idx in top_indices[:3]:  # 返回前3个
        article = articles[idx]
        results.append({
            "similarity": float(similarities[idx]),
            "theme": article["theme"],
            "content": article["content"]
        })

    return results


import random

def searchresult_content(user_input):
    """返回相似度最高的前5个段落里随机选择一个"""
    # 加载知识库
    theme_vectors, articles = load_knowledge_base()
    if theme_vectors is None:
        print("请先运行生成向量的脚本初始化知识库")
        return None

    print(f"知识库已加载，包含 {len(articles)} 条段落")

    try:
        # 向量化用户输入
        query_vector = vectorize_text(user_input)
        if query_vector is None:
            print("向量化失败")
            return None

        # 查找相似主题
        results = find_most_similar(query_vector, theme_vectors, articles)
        if not results:
            print("未找到匹配结果")
            return None

        # 取前5个（如果不足5个就取全部），然后随机选一个
        top_k = results[:5]
        chosen = random.choice(top_k)

        print("********************************************************")
        print(f"[{chosen.get('theme')}] {chosen.get('content', '无内容')}")
        print(f"（相似度：{chosen.get('similarity', 0):.2%}）")
        print("********************************************************")
        return chosen.get('content', '无内容')

    except Exception as e:
        print(f"处理过程中出错: {e}")
        return None

if __name__ == "__main__":
    searchresult_content("请你写一段拳法对决的情节")
