import base64
import io
import time
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


def _call_backend_upload(
    backend_url: str,
    service_api_key: str,
    *,
    query: str,
    reviewer_enabled: bool,
    image_file,
) -> dict:
    response = requests.post(
        f"{backend_url.rstrip('/')}/v1/consult/upload",
        data={
            "query": query,
            "reviewer_enabled": str(reviewer_enabled).lower(),
        },
        files={"image_file": (image_file.name, image_file.getvalue(), image_file.type or "application/octet-stream")},
        headers=_headers(service_api_key),
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def _submit_job(backend_url: str, service_api_key: str, payload: dict) -> dict:
    response = requests.post(
        f"{backend_url.rstrip('/')}/v1/jobs",
        json=payload,
        headers=_headers(service_api_key),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _submit_upload_job(
    backend_url: str,
    service_api_key: str,
    *,
    query: str,
    reviewer_enabled: bool,
    image_file,
) -> dict:
    response = requests.post(
        f"{backend_url.rstrip('/')}/v1/jobs/upload",
        data={
            "query": query,
            "reviewer_enabled": str(reviewer_enabled).lower(),
        },
        files={"image_file": (image_file.name, image_file.getvalue(), image_file.type or "application/octet-stream")},
        headers=_headers(service_api_key),
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def _fetch_job(backend_url: str, service_api_key: str, job_id: str) -> dict:
    response = requests.get(
        f"{backend_url.rstrip('/')}/v1/jobs/{job_id}",
        headers=_headers(service_api_key),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _status_label(status: str) -> str:
    mapping = {
        "queued": "Queued",
        "running": "Running",
        "completed": "Completed",
        "failed": "Failed",
    }
    return mapping.get(status, status or "unknown")


def _status_message(status: str) -> str:
    mapping = {
        "queued": "Task accepted by backend and waiting in the queue.",
        "running": "Backend worker is processing the task.",
        "completed": "Task completed and result is ready.",
        "failed": "Task failed. Inspect the returned error message.",
    }
    return mapping.get(status, "Task state updated.")


def _render_job_snapshot(job: dict, status_placeholder, detail_placeholder) -> None:
    status = job.get("status", "unknown")
    job_id = job.get("job_id", "-")
    session_id = job.get("session_id", "-")
    consultation_id = job.get("consultation_id")
    status_placeholder.info(f"Job `{job_id}` | Session `{session_id}` | Status `{_status_label(status)}`")

    details = [
        f"Status detail: {_status_message(status)}",
        f"Query: {job.get('query', '')}",
    ]
    if consultation_id is not None:
        details.append(f"Consultation ID: {consultation_id}")
    if job.get("created_at"):
        details.append(f"Created at: {job['created_at']}")
    if job.get("started_at"):
        details.append(f"Started at: {job['started_at']}")
    if job.get("completed_at"):
        details.append(f"Completed at: {job['completed_at']}")
    if job.get("error_message"):
        details.append(f"Error: {job['error_message']}")
    detail_placeholder.caption("\n".join(details))


def _poll_job_until_finished(
    backend_url: str,
    service_api_key: str,
    job_id: str,
    status_placeholder,
    detail_placeholder,
    poll_interval_seconds: float,
    max_wait_seconds: int,
) -> dict:
    start = time.time()
    last_job = {}
    while True:
        job = _fetch_job(backend_url, service_api_key, job_id)
        last_job = job
        _render_job_snapshot(job, status_placeholder, detail_placeholder)
        status = job.get("status")
        if status in {"completed", "failed"}:
            return job
        if time.time() - start > max_wait_seconds:
            raise TimeoutError(f"Job polling exceeded {max_wait_seconds} seconds.")
        time.sleep(poll_interval_seconds)


def _render_response(response: dict, preview_placeholder) -> None:
    trace = response.get("trace", [])
    if _used_parallel_branches(trace):
        st.info("This run executed retrieval and perception in parallel before report generation.")

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


def _used_parallel_branches(trace: list[dict]) -> bool:
    completed_nodes = {item.get("node") for item in trace if item.get("status") == "completed"}
    return "retriever" in completed_nodes and "perceptor" in completed_nodes


if "messages" not in st.session_state:
    st.session_state.messages = []


with st.sidebar:
    st.title("Settings")
    backend_url = st.text_input("Backend API URL", value=config.BACKEND_API_URL)
    service_api_key = st.text_input("Service API Key", value="", type="password")
    dicom_dir = st.text_input("DICOM directory path", value=config.DEFAULT_DICOM_DIR or "")
    image_file = st.file_uploader("NIfTI upload", type=["nii.gz"], help="Optional .nii.gz upload. When present, upload mode overrides path mode.")
    reviewer_enabled = st.checkbox("Enable reviewer", value=True)
    async_mode = st.checkbox("Use async job mode", value=True)
    poll_interval_seconds = st.slider("Job polling interval (seconds)", min_value=1.0, max_value=5.0, value=1.5, step=0.5)
    max_wait_seconds = st.slider("Max wait time (seconds)", min_value=15, max_value=300, value=90, step=15)
    if image_file is not None:
        st.info(f"Upload mode enabled: {image_file.name}")
    else:
        st.info("Path mode enabled. You can also upload a single .nii.gz file.")


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
    if image_file is not None:
        st.text(f"Current NIfTI upload:\n{image_file.name}")
    else:
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
                detail = st.empty()
                try:
                    if async_mode:
                        phase.info(
                            "Uploading NIfTI file and creating async job..."
                            if image_file is not None
                            else "Submitting async consultation job to backend..."
                        )
                        submitted = (
                            _submit_upload_job(
                                backend_url=backend_url,
                                service_api_key=service_api_key,
                                query=query,
                                reviewer_enabled=reviewer_enabled,
                                image_file=image_file,
                            )
                            if image_file is not None
                            else _submit_job(
                                backend_url=backend_url,
                                service_api_key=service_api_key,
                                payload={
                                    "query": query,
                                    "image_path": (dicom_dir or "").strip() or None,
                                    "reviewer_enabled": reviewer_enabled,
                                },
                            )
                        )
                        job_id = submitted["job_id"]
                        phase.success(f"Job submitted successfully: {job_id}")
                        detail.caption("Frontend is now polling backend job status.")

                        job = _poll_job_until_finished(
                            backend_url=backend_url,
                            service_api_key=service_api_key,
                            job_id=job_id,
                            status_placeholder=phase,
                            detail_placeholder=detail,
                            poll_interval_seconds=poll_interval_seconds,
                            max_wait_seconds=max_wait_seconds,
                        )
                        if job.get("status") == "failed":
                            phase.error("Backend job failed.")
                            st.error(job.get("error_message", "Unknown job failure."))
                        else:
                            phase.success("Backend job completed.")
                            result = job.get("result") or {}
                            _render_response(result, preview_placeholder)
                    else:
                        phase.info(
                            "Uploading NIfTI file and waiting for synchronous processing..."
                            if image_file is not None
                            else "Sending synchronous request to backend..."
                        )
                        response = (
                            _call_backend_upload(
                                backend_url=backend_url,
                                service_api_key=service_api_key,
                                query=query,
                                reviewer_enabled=reviewer_enabled,
                                image_file=image_file,
                            )
                            if image_file is not None
                            else _call_backend_json(
                                backend_url=backend_url,
                                service_api_key=service_api_key,
                                payload={
                                    "query": query,
                                    "image_path": (dicom_dir or "").strip() or None,
                                    "reviewer_enabled": reviewer_enabled,
                                },
                            )
                        )
                        phase.success("Backend finished request processing.")
                        detail.caption("Synchronous mode completed in a single request.")
                        _render_response(response, preview_placeholder)
                except requests.HTTPError as exc:
                    detail_text = exc.response.text if exc.response is not None else str(exc)
                    phase.error("Backend returned an error.")
                    st.error(detail_text)
                except requests.RequestException as exc:
                    phase.error("Cannot reach backend service.")
                    st.error(str(exc))
                except TimeoutError as exc:
                    phase.warning("Job is still running, but frontend polling timed out.")
                    st.warning(str(exc))
                except Exception as exc:
                    phase.error("Unexpected frontend error.")
                    st.error(str(exc))
                    st.exception(exc)


st.markdown("---")
st.caption("Frontend supports path mode, single .nii.gz upload, synchronous requests, and async job polling.")
