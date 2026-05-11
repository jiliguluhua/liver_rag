import os
from langchain_openai import ChatOpenAI
from monai.bundle import download
import core.config as config
from skills.document_processor import DocumentProcessor
from perception.perception import MedicalPerception

class SystemInitializer:
    # 1. 负责下载模型和构建 RAG 索引 (run_all)
    # 2. 负责导出预设好的 logic_llm 和 report_llm (供 90% 的场景直接使用)
    # 3. 负责暴露 get_llm 方法 (供 10% 的特殊场景自定义)
    
    def __init__(self, base_dir="./models", documents_dir="./data/documents", db_path="faiss_index"):
        self.base_dir = base_dir
        self.documents_dir = documents_dir
        self.db_path = db_path
        
        # 确保所有基础文件夹存在
        for d in [base_dir, documents_dir, "./results"]:
            os.makedirs(d, exist_ok=True)

    def setup_perception(self):
        """初始化感知层模型 (Swin UNETR)"""
        model_name = "swin_unetr_btcv_segmentation"
        target_path = os.path.join(self.base_dir, model_name)
        
        if not os.path.exists(target_path):
            print(f"首次运行，正在下载 Swin UNETR 医学模型权重...")
            try:
                download(name=model_name, bundle_dir=self.base_dir)
                print("模型下载成功！")
            except Exception as e:
                print(f"下载失败: {e}")
        else:
            print("医学分割模型已就绪。")
        return target_path
    
    def setup_knowledge(self, filename):
        """初始化认知层知识库 (RAG)"""
        full_pdf_path = os.path.join(self.documents_dir, filename)
        
        if os.path.exists(full_pdf_path):
            print(f"--- 正在处理: {filename} ---")
            processor = DocumentProcessor(db_path=self.db_path)
            chunks = processor.process_pdf(full_pdf_path)
            processor.build_or_update_db(chunks)
        else:
            print(f"找不到文件: {full_pdf_path}")

    def get_llm(self, temperature=0):
        """统一获取 LLM 客户端"""
        return ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=config.LLM_API_KEY,
            openai_api_base="https://api.deepseek.com",
            temperature=temperature
        )
        
    def run_all(self):
        self.setup_perception()
        if not os.path.exists(self.documents_dir):
            print(f"错误: 文件夹 {self.documents_dir} 不存在")
            return
        pdf_files = [f for f in os.listdir(self.documents_dir) if f.endswith(".pdf")]
        if not pdf_files:
            print("data/documents 文件夹下没有 PDF 文件，跳过知识库构建。")
        else:
            for filename in pdf_files:
                self.setup_knowledge(filename)
        print("文献初始化任务完成。")

# --- 全局 initializer ---
initializer = SystemInitializer()
# 预定义两个不同温控的默认模型供 Agent 使用
logic_llm = initializer.get_llm(temperature=0)      # 决策用
report_llm = initializer.get_llm(temperature=0.3)    # 生成报告用

if __name__ == "__main__":
    initializer = SystemInitializer()
    initializer.run_all()