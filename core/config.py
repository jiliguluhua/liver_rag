import os

from dotenv import load_dotenv

load_dotenv()

# --- 1. 基础路径配置 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据与模型存放目录
DOCUMENTS_DIR = os.path.join(BASE_DIR, "data/documents")
MODEL_DIR = os.path.join(BASE_DIR, "models")
RESULT_DIR = os.path.join(BASE_DIR, "results")
DB_PATH = os.path.join(BASE_DIR, "faiss_index")

# --- 2. 具体的模型与文件配置 ---
# 影像分割模型 (Swin UNETR)
PERCEPTION_MODEL_NAME = "swin_unetr_btcv_segmentation"
PERCEPTION_MODEL_PATH = os.path.join(MODEL_DIR, PERCEPTION_MODEL_NAME, "models", "model.pt")
PERCEPTION_META_PATH = os.path.join(MODEL_DIR, PERCEPTION_MODEL_NAME, "configs", "metadata.json")

# 嵌入模型 (BGE-Small) - 填入你本地的绝对路径
EMBEDDING_MODEL_NAME = "bge-small-zh-v1.5"
EMBEDDING_MODEL_PATH = r"C:\Users\21204\.cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5\snapshots\7999e1d3359715c523056ef9478215996d62a620"

# LLM（务必用环境变量或 .env，勿提交密钥）
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").strip()
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-chat").strip()

# HTTP API：可选服务密钥（请求头 X-API-Key）；不设置则不校验
SERVICE_API_KEY = os.getenv("LIVER_SERVICE_API_KEY", "").strip()

# 会诊默认 DICOM 序列目录（可被 Streamlit / POST body 覆盖）
DEFAULT_DICOM_DIR = os.getenv("LIVER_DEFAULT_DICOM_DIR", "").strip()

# 本地llm模型
# LLM_LOCAL_MODEL_NAME = "Qwen2.5-0.5B-Instruct"
# LLM_LOCAL_MODEL_PATH = r"C:\Users\21204\.cache\huggingface\hub\models--Qwen--Qwen2.5-0.5B-Instruct\snapshots\7ae557604adf67be50417f59c2c2f167def9a775"

# LLM_LOCAL_MODEL_NAME = "Qwen2.5-Coder-7B-Instruct-GPTQ-Int4"
# LLM_LOCAL_MODEL_PATH = r"C:\Users\21204\.cache\huggingface\hub\models--Qwen--Qwen2.5-Coder-7B-Instruct-GPTQ-Int4"

# --- 3. Agent 策略配置 ---
# RAG 检索权重 (0.7 向量 : 0.3 关键词)
RETRIEVAL_ALPHA = 0.7
TOP_K = 3

# --- 4. 自动创建必要目录 ---
for path in [DOCUMENTS_DIR, MODEL_DIR, RESULT_DIR]:
    os.makedirs(path, exist_ok=True)