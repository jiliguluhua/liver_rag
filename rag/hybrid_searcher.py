import os
import sys
import jieba
import numpy as np
from rank_bm25 import BM25Okapi
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import core.config as config

class MedicalHybridSearcher:
    def __init__(self, db_path=config.DB_PATH, model_path=config.EMBEDDING_MODEL_PATH):
        # 1. 初始化向量库
        self.embeddings = HuggingFaceEmbeddings(model_name=model_path)
        self.vector_db = FAISS.load_local(db_path, self.embeddings, allow_dangerous_deserialization=True)
        
        # 2. 准备 Jieba 与自定义字典
        dict_path = config.MEDICAL_DICT_PATH
        if os.path.exists(dict_path):
            jieba.load_userdict(dict_path)
            print(f"✅ 成功加载医疗自定义词典: {dict_path}")
        else:
            print("⚠️ 未找到自定义词典，使用 jieba 默认分词")

        # 3. 提取所有文档并构建 BM25 索引
        all_docs_dict = self.vector_db.docstore._dict
        self.all_docs = list(all_docs_dict.values())
        
        # 使用 jieba 进行分词构建语料库
        self.corpus_tokens = [list(jieba.cut(doc.page_content)) for doc in self.all_docs]
        self.bm25 = BM25Okapi(self.corpus_tokens)
        print("✅ 混合检索引擎就绪：Jieba + RRF 架构")

    def search(self, query, top_k=3):
        # --- 步骤 1: 向量检索 (Vector Search) ---
        # 返回格式为 List[tuple(Document, score)]
        vector_res = self.vector_db.similarity_search_with_score(query, k=10)
        vector_docs = [res[0] for res in vector_res]
        
        # --- 步骤 2: 关键词检索 (BM25 Search) ---
        query_tokens = list(jieba.cut(query))
        bm25_scores = self.bm25.get_scores(query_tokens)
        top_bm25_indices = np.argsort(bm25_scores)[::-1][:10]
        bm25_docs = [self.all_docs[i] for i in top_bm25_indices]

        # --- 步骤 3: RRF 排名融合 ---
        # 核心逻辑：不看绝对分数，只看各算法给出的排名
        rrf_scores = {} # key: doc_id (此处用内容哈希或内容本身), value: rrf_score
        k = 60 # RRF 标准常数
        
        # 辅助字典：用于通过内容找回原始 Document 对象
        content_to_doc = {}

        # 处理向量排名
        for rank, doc in enumerate(vector_docs):
            content = doc.page_content
            content_to_doc[content] = doc
            rrf_scores[content] = rrf_scores.get(content, 0) + 1.0 / (k + rank + 1)
            
        # 处理 BM25 排名
        for rank, doc in enumerate(bm25_docs):
            content = doc.page_content
            content_to_doc[content] = doc
            rrf_scores[content] = rrf_scores.get(content, 0) + 1.0 / (k + rank + 1)

        # 按 RRF 分数从高到低排序
        sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        # --- 步骤 4: 重新封装成 List[Document] ---
        # 这一步确保了返回格式与后续 main.py 和 llm_node.py 完美契合
        final_docs = [content_to_doc[item[0]] for item in sorted_results]

        # 如果需要 Rerank，可以在这里切片前加入 CrossEncoder 逻辑
        # final_docs = self._rerank(query, final_docs[:10])

        print(f"DEBUG: Hybrid Search 命中 {len(final_docs)} 条候选资料")
        return final_docs[:top_k]
    
if __name__ == "__main__":
    # 测试
    searcher = MedicalHybridSearcher(model_path=config.EMBEDDING_MODEL_PATH, db_path=config.DB_PATH)
    results = searcher.search("肿瘤体积 20ml 治疗方案")
    for doc, score in results:
        print(f"\n匹配到指南内容: {doc.page_content[:100]}...")
