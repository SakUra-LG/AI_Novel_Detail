import re
import numpy as np
import json
import os
from embedding_model import batch_vectorize

# 配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledgeBase")


def parse_knowledge_text(text):
    """解析专业知识文本（格式：名称：描述）"""
    pattern = r'(.+?)：(.+?)(?=\n.+?：|$)'
    matches = re.findall(pattern, text, re.DOTALL)

    knowledge_data = []
    for name, content in matches:
        description = content.replace('\n', ' ').strip()
        knowledge_data.append({
            "name": name.strip(),
            "description": description,
            "full_text": f"{name.strip()}：{description}"
        })
    return knowledge_data


def process_knowledge(file_path):
    """处理专业知识文本文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # 解析文本
    knowledge_data = parse_knowledge_text(text)
    if not knowledge_data:
        raise ValueError("未解析到有效的知识点数据")

    # 准备向量化文本
    text_features = [item["full_text"] for item in knowledge_data]

    # 向量化
    feature_vectors = batch_vectorize(text_features, batch_size=8, max_length=256)

    # 构建结果
    results = []
    for i, item in enumerate(knowledge_data):
        results.append({
            "name": item["name"],
            "vector": feature_vectors[i].tolist(),
            "description": item["description"]
        })

    return results, feature_vectors



if __name__ == "__main__":
    try:
        knowledge_results, vectors = process_knowledge(
            os.path.join(KNOWLEDGE_DIR, "Professional.txt")
        )
        print(f"成功处理 {len(knowledge_results)} 个知识点")

        # 保存向量
        np.save(os.path.join(KNOWLEDGE_DIR, 'features_profession.npy'), vectors)

        # 保存元数据
        with open(os.path.join(KNOWLEDGE_DIR, 'features_profession.json'), 'w', encoding='utf-8') as f:
            json.dump({
                "version": "1.0",
                "count": len(knowledge_results),
                "data": knowledge_results
            }, f, ensure_ascii=False, indent=2)

        print("向量和元数据保存成功！")
        print(f"向量维度：{vectors.shape}")

    except Exception as e:
        print(f"处理失败：{str(e)}")
        exit(1)
