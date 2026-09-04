import numpy as np
import json
import os
from sklearn.metrics.pairwise import cosine_similarity
from embedding_model import vectorize_text as encode_text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_profession_knowledge():
    """加载专业知识库"""
    try:
        # 加载向量
        vectors_path = os.path.join(BASE_DIR, 'knowledgeBase', 'features_profession.npy')
        vectors = np.load(vectors_path)

        # 加载元数据
        features_profession_path = os.path.join(BASE_DIR, 'knowledgeBase', 'features_profession.json')
        with open(features_profession_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        # 验证数据一致性
        if len(metadata["data"]) != vectors.shape[0]:
            print(f"数据不匹配：知识点数({len(metadata['data'])}) ≠ 向量数({vectors.shape[0]})")
            return None, None

        return vectors, metadata["data"]
    except Exception as e:
        print(f"加载知识库时出错: {e}")
        return None, None


def vectorize_text(text):
    """将文本转换为向量"""
    return encode_text(text, max_length=256)


def find_most_similar(query_vector, vectors, knowledge_data, top_k=3):
    """查找最相似的知识点"""
    similarities = cosine_similarity(query_vector, vectors)[0]
    top_indices = np.argsort(similarities)[::-1]  # 按相似度降序排列

    results = []
    for idx in top_indices[:top_k]:
        item = knowledge_data[idx]
        results.append({
            "similarity": float(similarities[idx]),
            "name": item["name"],
            "description": item["description"],
            "vector": item["vector"]
        })

    return results


def searchresult_profession(user_input):
    """推荐最相关的专业知识点"""
    # 加载知识库
    vectors, knowledge_data = load_profession_knowledge()
    if vectors is None:
        print("请先运行知识库初始化脚本")
        return None

    # 向量化用户输入
    query_vector = vectorize_text(user_input)

    # 查找相似知识点
    results = find_most_similar(query_vector, vectors, knowledge_data)

    if not results:
        print("未找到匹配的知识点")
        return None

    # 返回最佳匹配
    best_match = results[0]
    print("\n=== 推荐结果 ===")
    print(best_match['name'] + "：" + best_match['description'])
    return (best_match['name'] + "：" + best_match['description'])


# 示例使用
if __name__ == "__main__":
    while True:
        user_input = input("\n请输入查询内容（输入q退出）: ").strip()
        if user_input.lower() == 'q':
            break
