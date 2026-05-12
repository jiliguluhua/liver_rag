import base64
import io
from typing import Optional

import requests
import streamlit as st
from PIL import Image

import core.config as config


st.set_page_config(
    page_title="LiverSmart Demo",
    page_icon=":stethoscope:",
    layout="wide",
    initial_sidebar_state="expanded",
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


def _render_response(response: dict, preview_placeholder) -> None:
    final_report = response.get("report", "")
    st.markdown(final_report)

    preview_img = _decode_preview_image(response.get("preview_image_base64"))
    if preview_img:
        preview_placeholder.image(
            preview_img,
            caption="Preview",
            use_container_width=True,
        )
        st.session_state.last_image = preview_img

    warnings = response.get("warnings", [])
    if warnings:
        with st.expander("Warnings"):
            for warning in warnings:
                st.write(f"- {warning}")

    evidence = response.get("evidence", [])
    if evidence:
        with st.expander("Evidence"):
            for idx, item in enumerate(evidence, start=1):
                source = item.get("source", "unknown")
                snippet = item.get("snippet", "")
                st.markdown(f"**Evidence {idx} | {source}**")
                st.write(snippet)

    trace = response.get("trace", [])
    if trace:
        with st.expander("Trace"):
            for item in trace:
                st.write(
                    f"{item.get('node', '-')}: {item.get('status', '-')} | "
                    f"{item.get('message', '')}"
                )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": final_report,
            "image": preview_img,
        }
    )


if "messages" not in st.session_state:
    st.session_state.messages = []


with st.sidebar:
    st.title("Settings")
    backend_url = st.text_input("Backend API URL", value=config.BACKEND_API_URL)
    service_api_key = st.text_input("Service API Key", value="", type="password")
    dicom_dir = st.text_input("DICOM directory path", value=config.DEFAULT_DICOM_DIR or "")
    reviewer_enabled = st.checkbox("Enable reviewer", value=True)
    st.info("Directory mode only in the frontend for now. Zip upload stays available in the backend API.")


st.title("LiverSmart Demo")
st.caption("Frontend calling FastAPI backend")

col_chat, col_preview = st.columns([3, 2])

with col_preview:
    st.subheader("Preview")
    preview_placeholder = st.empty()
    if "last_image" not in st.session_state:
        preview_placeholder.info("No preview yet.")
    else:
        preview_placeholder.image(
            st.session_state.last_image,
            caption="Preview",
            use_container_width=True,
        )

    st.subheader("Input")
    st.text(f"Current DICOM directory:\n{(dicom_dir or 'not set')[:120]}")


with col_chat:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("image"):
                st.image(message["image"], width=300)

    query = st.text_area(
        "Case question",
        placeholder="Example: summarize the next recommended examination step",
        height=110,
    )

    analyze_clicked = st.button("Analyze", use_container_width=True, type="primary")

    if analyze_clicked:
        if not query.strip():
            st.error("Please enter a question before submitting.")
        else:
            st.session_state.messages.append({"role": "user", "content": query})
            with st.chat_message("user"):
                st.markdown(query)

            with st.chat_message("assistant"):
                phase = st.empty()
                try:
                    phase.info("Sending request to backend...")
                    response = _call_backend_json(
                        backend_url=backend_url,
                        service_api_key=service_api_key,
                        payload={
                            "query": query,
                            "image_path": (dicom_dir or "").strip() or None,
                            "reviewer_enabled": reviewer_enabled,
                        },
                    )
                    phase.success("Backend finished request processing.")
                    _render_response(response, preview_placeholder)
                except requests.HTTPError as exc:
                    detail = exc.response.text if exc.response is not None else str(exc)
                    phase.error("Backend returned an error.")
                    st.error(detail)
                except requests.RequestException as exc:
                    phase.error("Cannot reach backend service.")
                    st.error(str(exc))
                except Exception as exc:
                    phase.error("Unexpected frontend error.")
                    st.error(str(exc))
                    st.exception(exc)


st.markdown("---")
st.caption("Frontend uses directory-path mode. Zip upload remains available in the FastAPI backend.")
