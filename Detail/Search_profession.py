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


def load_profession_knowledge():
    """加载专业知识库"""
    try:
        # 加载向量
        vectors = np.load('knowledgeBase/features_profession.npy')

        # 加载元数据
        with open('knowledgeBase/features_profession.json', 'r', encoding='utf-8') as f:
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
    inputs = tokenizer(
        text,
        padding=True,
        truncation=True,
        max_length=256,
        return_tensors="pt"
    ).to(device)

    with torch.inference_mode():
        outputs = model(**inputs)
        embeddings = outputs.last_hidden_state[:, 0]
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

    return embeddings.cpu().numpy()


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
