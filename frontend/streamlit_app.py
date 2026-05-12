import base64
import io
from typing import Optional

import requests
import streamlit as st
from PIL import Image

import core.config as config


st.set_page_config(
    page_title="LiverSmart 肝脏病例辅助分析系统",
    page_icon=":stethoscope:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main {
        background: linear-gradient(180deg, #f7f4ee 0%, #eef3f8 100%);
    }
    .stChatMessage {
        border-radius: 12px;
    }
    .block-container {
        padding-top: 2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _headers(service_api_key: str) -> dict:
    headers = {}
    if service_api_key.strip():
        headers["X-API-Key"] = service_api_key.strip()
    return headers


def _decode_preview_image(image_b64: Optional[str]):
    if not image_b64:
        return None
    data = base64.b64decode(image_b64)
    return Image.open(io.BytesIO(data))


def _call_backend_json(backend_url: str, service_api_key: str, payload: dict) -> dict:
    response = requests.post(
        f"{backend_url.rstrip('/')}/v1/consult",
        json=payload,
        headers=_headers(service_api_key),
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def _call_backend_upload(
    backend_url: str,
    service_api_key: str,
    query: str,
    reviewer_enabled: bool,
    dicom_zip,
) -> dict:
    files = {
        "dicom_zip": (
            dicom_zip.name,
            dicom_zip.getvalue(),
            "application/zip",
        )
    }
    data = {
        "query": query,
        "reviewer_enabled": str(reviewer_enabled).lower(),
    }
    response = requests.post(
        f"{backend_url.rstrip('/')}/v1/consult/upload",
        data=data,
        files=files,
        headers=_headers(service_api_key),
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


with st.sidebar:
    st.title("系统设置")
    st.caption("前端通过 HTTP 调用后端 API，适合演示前后端分离架构")

    backend_url = st.text_input(
        "后端 API 地址",
        value=config.BACKEND_API_URL,
        help="默认指向本机 FastAPI 服务，例如 http://127.0.0.1:8000",
    )
    service_api_key = st.text_input(
        "服务鉴权 Key",
        value="",
        type="password",
        help="如果后端启用了 X-API-Key 校验，可在这里填写；未启用可留空。",
    )
    dicom_dir = st.text_input(
        "DICOM 目录路径",
        value=config.DEFAULT_DICOM_DIR or "",
        help="本地调试可直接传目录路径；如需更像产品，可改用下方 zip 上传。",
    )
    dicom_zip = st.file_uploader(
        "上传 DICOM 压缩包",
        type=["zip"],
        help="将一个包含完整 DICOM 序列的文件夹压缩为 zip 后上传。",
    )
    reviewer_enabled = st.checkbox("启用审核节点", value=True)

    st.divider()
    st.markdown(
        """
        **当前后端能力**
        - 医疗问题意图识别
        - 指南文档检索与证据返回
        - 影像感知占位链路
        - zip 上传后端解压处理
        - 结构化告警与执行轨迹
        """
    )
    st.caption("版本：V1.5")


st.title("LiverSmart 肝脏病例辅助分析系统")
st.caption("面向后端服务演示的前端页面")

if "messages" not in st.session_state:
    st.session_state.messages = []

col_chat, col_preview = st.columns([3, 2])

with col_preview:
    st.subheader("影像预览")
    preview_placeholder = st.empty()

    if "last_image" not in st.session_state:
        preview_placeholder.info("当前暂无影像结果。若后端返回预览图，会在这里显示。")
    else:
        preview_placeholder.image(
            st.session_state.last_image,
            caption="最新影像预览",
            use_container_width=True,
        )

    st.divider()
    st.subheader("输入方式")
    if dicom_zip is not None:
        st.write(f"当前上传：{dicom_zip.name}")
    else:
        st.text(f"当前 DICOM 目录：\n{(dicom_dir or '未填写')[:120]}")


with col_chat:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("image"):
                st.image(message["image"], width=300)

    prompt = st.chat_input("请输入病例问题，例如：请概述该患者下一步检查建议")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("后端正在处理请求..."):
                try:
                    if dicom_zip is not None:
                        response = _call_backend_upload(
                            backend_url=backend_url,
                            service_api_key=service_api_key,
                            query=prompt,
                            reviewer_enabled=reviewer_enabled,
                            dicom_zip=dicom_zip,
                        )
                    else:
                        payload = {
                            "query": prompt,
                            "image_path": (dicom_dir or "").strip() or None,
                            "reviewer_enabled": reviewer_enabled,
                        }
                        response = _call_backend_json(
                            backend_url=backend_url,
                            service_api_key=service_api_key,
                            payload=payload,
                        )

                    final_report = response.get("report", "")
                    preview_img = _decode_preview_image(response.get("preview_image_base64"))

                    st.markdown(final_report)

                    warnings = response.get("warnings", [])
                    if warnings:
                        with st.expander("查看系统告警"):
                            for warning in warnings:
                                st.write(f"- {warning}")

                    evidence = response.get("evidence", [])
                    if evidence:
                        with st.expander("查看检索证据"):
                            for idx, item in enumerate(evidence, start=1):
                                source = item.get("source", "未知来源")
                                snippet = item.get("snippet", "")
                                st.markdown(f"**证据 {idx}｜{source}**")
                                st.write(snippet)

                    trace = response.get("trace", [])
                    if trace:
                        with st.expander("查看执行轨迹"):
                            for item in trace:
                                st.write(
                                    f"{item.get('node', '-')}: {item.get('status', '-')} | "
                                    f"{item.get('message', '')}"
                                )

                    if preview_img:
                        preview_placeholder.image(
                            preview_img,
                            caption="最新影像预览",
                            use_container_width=True,
                        )
                        st.session_state.last_image = preview_img

                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": final_report,
                            "image": preview_img,
                        }
                    )
                except requests.HTTPError as exc:
                    detail = exc.response.text if exc.response is not None else str(exc)
                    st.error(f"后端返回错误：{detail}")
                except Exception as exc:
                    st.error(f"运行失败：{exc}")
                    st.exception(exc)


st.markdown("---")
st.caption("说明：前端现在通过 HTTP 调用 FastAPI 后端，支持目录路径输入与 zip 上传两种方式。")
