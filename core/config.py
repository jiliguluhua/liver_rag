import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = str(PROJECT_ROOT)

DOCUMENTS_DIR = str(PROJECT_ROOT / "data" / "documents")
MODEL_DIR = str(PROJECT_ROOT / "models")
RESULT_DIR = str(PROJECT_ROOT / "results")
DB_PATH = str(PROJECT_ROOT / "faiss_index")

PERCEPTION_MODEL_NAME = "swin_unetr_btcv_segmentation"
PERCEPTION_MODEL_PATH = os.path.join(MODEL_DIR, PERCEPTION_MODEL_NAME, "models", "model.pt")
PERCEPTION_META_PATH = os.path.join(MODEL_DIR, PERCEPTION_MODEL_NAME, "configs", "metadata.json")

EMBEDDING_MODEL_NAME = "bge-small-zh-v1.5"
EMBEDDING_MODEL_PATH = r"C:\Users\21204\.cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5\snapshots\7999e1d3359715c523056ef9478215996d62a620"

LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").strip()
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-chat").strip()

# Example DeepSeek-compatible settings for real LLM calls.
# Keep these commented for fallback-only testing with zero token usage.
# LLM_API_KEY = "your-deepseek-api-key"
# LLM_BASE_URL = "https://api.deepseek.com"
# LLM_MODEL_NAME = "deepseek-chat"

SERVICE_API_KEY = os.getenv("LIVER_SERVICE_API_KEY", "").strip()
DEFAULT_DICOM_DIR = os.getenv("LIVER_DEFAULT_DICOM_DIR", "").strip()

RETRIEVAL_ALPHA = 0.7
TOP_K = 3

for path in [DOCUMENTS_DIR, MODEL_DIR, RESULT_DIR]:
    os.makedirs(path, exist_ok=True)
