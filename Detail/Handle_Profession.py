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


def batch_vectorize(texts, batch_size=8):
    """批量向量化文本"""
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="pt"
        ).to(device)

        with torch.inference_mode():
            outputs = model(**inputs)
            embeddings = outputs.last_hidden_state[:, 0]
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
        all_embeddings.append(embeddings.cpu().numpy())
    return np.vstack(all_embeddings)


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
    feature_vectors = batch_vectorize(text_features)

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
        knowledge_results, vectors = process_knowledge("knowledgeBase/Professional.txt")
        print(f"成功处理 {len(knowledge_results)} 个知识点")

        # 保存向量
        np.save('knowledgeBase/features_profession.npy', vectors)

        # 保存元数据
        with open('knowledgeBase/features_profession.json', 'w', encoding='utf-8') as f:
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
