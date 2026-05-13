import os
import sys
import torch
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from rag.text_cleaner import MedicalTextCleaner
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import core.config as config

class DocumentProcessor:
    def __init__(self, db_path=config.DB_PATH):
        self.db_path = db_path
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"初始化知识处理引擎 (Device: {self.device}) ---")
        self.cleaner = MedicalTextCleaner()
        
        # 1. 嵌入模型
        self.embeddings = HuggingFaceEmbeddings(
            model_name=r"C:\Users\21204\.cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5\snapshots\7999e1d3359715c523056ef9478215996d62a620",  # 👈 传本地路径，它就不会去联网下载了
            model_kwargs={'device': self.device},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        # 2. 医疗语义切分器
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=600, 
            chunk_overlap=80
        )

    def process_pdf(self, pdf_path):
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"找不到指南文件: {pdf_path}")
            
        print(f"正在读取 PDF: {os.path.basename(pdf_path)}...")
        loader = PyMuPDFLoader(pdf_path)
        docs = loader.load()
        raw_chunks = self.text_splitter.split_documents(docs)
        valid_chunks = []
        for chunk in raw_chunks:
            # 1. 清洗：去除页码、多余空格等
            cleaned_content = self.cleaner.clean_text(chunk.page_content)
            # 2. 判定：如果这一块不是噪音（比如不是纯参考文献、长度够长）
            if not self.cleaner.is_noise(cleaned_content):
                chunk.page_content = cleaned_content
                chunk.metadata["source"] = os.path.basename(pdf_path)
                valid_chunks.append(chunk)
            else:
                continue
        print(f"解析成功：原始 {len(raw_chunks)} 个，保留有效知识块 {len(valid_chunks)} 个")
        return valid_chunks

    def build_or_update_db(self, chunks):
        if os.path.exists(self.db_path):
            print("发现现有索引，正在执行增量更新...")
            vector_db = FAISS.load_local(self.db_path, self.embeddings, allow_dangerous_deserialization=True)
            vector_db.add_documents(chunks)
        else:
            print("正在构建初始向量索引...")
            vector_db = FAISS.from_documents(chunks, self.embeddings)
            
        vector_db.save_local(self.db_path)
        print(f"向量库已保存至: {self.db_path}\n")

if __name__ == "__main__":
    processor = DocumentProcessor()
