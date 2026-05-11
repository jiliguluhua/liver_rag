import streamlit as st
import os
from PIL import Image
from main import LiverSmartAgent
import core.config as config

# ==========================================
# 1. 页面基础配置
# ==========================================
st.set_page_config(
    page_title="LiverSmart 肝脏智能辅助诊断系统",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义样式
st.markdown("""
    <style>
    .main {
        background-color: #f5f7f9;
    }
    .stChatMessage {
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 缓存加载逻辑 (解决显存占用核心改动)
# ==========================================
@st.cache_resource
def get_agent(api_key):
    """
    使用 cache_resource 确保 LiverSmartAgent (及其内部的大模型) 
    在整个应用运行期间只被加载一次。
    """
    return LiverSmartAgent(api_key=api_key)

# ==========================================
# 3. 侧边栏及初始化
# ==========================================
with st.sidebar:
    st.title("⚙️ 系统设置")
    st.info("本系统集成了 Swin UNETR 分割模型与 RAG 知识库检索。")
    
    api_key = st.text_input(
        "LLM API Key",
        value=config.LLM_API_KEY or "",
        type="password",
        help="也可在环境变量 LLM_API_KEY / .env 中配置",
    )

    default_dir = config.DEFAULT_DICOM_DIR or ""
    dicom_dir = st.text_input(
        "DICOM 序列目录",
        value=default_dir,
        help="指向包含 DICOM 序列的文件夹；或使用环境变量 LIVER_DEFAULT_DICOM_DIR",
    )
    
    st.divider()
    
    # 使用缓存函数初始化 Agent
    if api_key:
        try:
            if 'agent' not in st.session_state:
                with st.spinner("正在初始化医疗 AI 引擎..."):
                    # 调用带缓存的加载函数
                    st.session_state.agent = get_agent(api_key)
                st.success("医疗引擎就绪！")
        except Exception as e:
            st.error(f"初始化失败: {e}")
    else:
        st.warning("请配置 API Key 以启用对话功能。")

    st.divider()
    st.caption("版本: V1.3 (Hybrid Search + HTTP API + SQLite 会诊记录)")

# ==========================================
# 4. 主界面布局
# ==========================================
st.title("🩺 LiverSmart 肝脏智能辅助诊断系统")

# 聊天记录初始化
if "messages" not in st.session_state:
    st.session_state.messages = []

# 创建左右两栏
col_chat, col_preview = st.columns([3, 2])

# --- 右栏：影像预览区 ---
with col_preview:
    st.subheader("🖼️ 影像感知预览")
    preview_placeholder = st.empty()
    
    if "last_image" not in st.session_state:
        preview_placeholder.info("暂无感知结果。当您询问关于影像的问题时，AI 将自动分析并在此显示切片。")
    else:
        preview_placeholder.image(st.session_state.last_image, caption="AI 自动识别结果 (红色区域为 ROI)", use_container_width=True)

    st.divider()
    st.subheader("📁 数据源信息")
    st.text(f"当前分析目录:\n{(dicom_dir or '(未配置)')[:120]}")

# --- 左栏：对话区 ---
with col_chat:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "image" in message and message["image"]:
                st.image(message["image"], width=300)

    if prompt := st.chat_input("请输入您的问题..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        if 'agent' in st.session_state:
            with st.chat_message("assistant"):
                with st.spinner("Agent 正在思考中 (分析影像 + 检索指南)..."):
                    try:
                        if not (dicom_dir or "").strip():
                            st.error("请在左侧填写「DICOM 序列目录」或配置环境变量 LIVER_DEFAULT_DICOM_DIR。")
                        else:
                            final_report, preview_img = st.session_state.agent.run(
                                (dicom_dir or "").strip(),
                                prompt,
                            )

                            st.markdown(final_report)

                            if preview_img:
                                preview_placeholder.image(
                                    preview_img,
                                    caption="AI 自动识别结果",
                                    use_container_width=True,
                                )
                                st.session_state.last_image = preview_img

                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": final_report,
                                "image": preview_img if preview_img else None,
                            })

                    except Exception as e:
                        st.error(f"发生错误: {str(e)}")
                        st.exception(e)
        else:
            st.error("Agent 未初始化，请在左侧侧边栏配置 API Key。")

st.markdown("---")
st.caption("注：本系统仅供科研参考。模型基于 Swin UNETR 对腹部 CT 进行处理。")