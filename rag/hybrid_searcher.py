from __future__ import annotations

import os
import sys

import jieba
import numpy as np
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import core.config as config
from services.redis_store import redis_store


class MedicalHybridSearcher:
    def __init__(self, db_path: str = config.DB_PATH, model_path: str = config.EMBEDDING_MODEL_PATH):
        self.embeddings = HuggingFaceEmbeddings(model_name=model_path)
        self.vector_db = FAISS.load_local(db_path, self.embeddings, allow_dangerous_deserialization=True)

        dict_path = config.MEDICAL_DICT_PATH
        if os.path.exists(dict_path):
            jieba.load_userdict(dict_path)

        all_docs_dict = self.vector_db.docstore._dict
        self.all_docs = list(all_docs_dict.values())
        self.corpus_tokens = [list(jieba.cut(doc.page_content)) for doc in self.all_docs]
        self.bm25 = BM25Okapi(self.corpus_tokens)

    def search(self, query: str, top_k: int = 3):
        cached_docs = redis_store.get_search_results(query, top_k)
        if cached_docs is not None:
            return cached_docs

        vector_res = self.vector_db.similarity_search_with_score(query, k=10)
        vector_docs = [res[0] for res in vector_res]

        query_tokens = list(jieba.cut(query))
        bm25_scores = self.bm25.get_scores(query_tokens)
        top_bm25_indices = np.argsort(bm25_scores)[::-1][:10]
        bm25_docs = [self.all_docs[i] for i in top_bm25_indices]

        rrf_scores: dict[str, float] = {}
        rank_constant = 60
        content_to_doc = {}

        for rank, doc in enumerate(vector_docs):
            content = doc.page_content
            content_to_doc[content] = doc
            rrf_scores[content] = rrf_scores.get(content, 0.0) + 1.0 / (rank_constant + rank + 1)

        for rank, doc in enumerate(bm25_docs):
            content = doc.page_content
            content_to_doc[content] = doc
            rrf_scores[content] = rrf_scores.get(content, 0.0) + 1.0 / (rank_constant + rank + 1)

        sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        final_docs = [content_to_doc[item[0]] for item in sorted_results]
        top_docs = final_docs[:top_k]
        redis_store.set_search_results(query, top_k, top_docs)
        return top_docs


if __name__ == "__main__":
    searcher = MedicalHybridSearcher(model_path=config.EMBEDDING_MODEL_PATH, db_path=config.DB_PATH)
    results = searcher.search("肿瘤体积 20ml 治疗方案")
    for doc in results:
        print(f"\n匹配到指南内容: {doc.page_content[:100]}...")
