import streamlit as st

import core.config as config
from services.medical_agent import LiverSmartAgent


st.set_page_config(
    page_title="LiverSmart Liver Diagnosis Assistant",
    page_icon=":hospital:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main {
        background-color: #f5f7f9;
    }
    .stChatMessage {
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_agent(api_key: str) -> LiverSmartAgent:
    return LiverSmartAgent(api_key=api_key)


with st.sidebar:
    st.title("System Settings")
    st.info("This demo combines image perception, retrieval, and an LLM report step.")

    api_key = st.text_input(
        "LLM API Key",
        value=config.LLM_API_KEY or "",
        type="password",
        help="Optional for quick testing. Leave blank to run in fallback mode without spending tokens.",
    )

    default_dir = config.DEFAULT_DICOM_DIR or ""
    dicom_dir = st.text_input(
        "DICOM Directory",
        value=default_dir,
        help="Point this to a DICOM series folder, or set LIVER_DEFAULT_DICOM_DIR.",
    )

    st.divider()

    try:
        current_api_key = api_key or ""
        if st.session_state.get("agent_api_key") != current_api_key:
            with st.spinner("Initializing LiverSmart agent..."):
                st.session_state.agent = get_agent(current_api_key)
            st.session_state.agent_api_key = current_api_key

        if current_api_key:
            st.success("Agent ready.")
        else:
            st.info("Fallback mode enabled: retrieval and backend flow work without consuming LLM tokens.")
    except Exception as exc:
        st.error(f"Initialization failed: {exc}")

    st.divider()
    st.caption("Version: V1.3")


st.title("LiverSmart Liver Diagnosis Assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

col_chat, col_preview = st.columns([3, 2])

with col_preview:
    st.subheader("Image Preview")
    preview_placeholder = st.empty()

    if "last_image" not in st.session_state:
        preview_placeholder.info("No perception result yet.")
    else:
        preview_placeholder.image(
            st.session_state.last_image,
            caption="AI preview result",
            use_container_width=True,
        )

    st.divider()
    st.subheader("Data Source")
    st.text(f"Current directory:\n{(dicom_dir or '(not configured)')[:120]}")

with col_chat:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "image" in message and message["image"]:
                st.image(message["image"], width=300)

    if prompt := st.chat_input("Ask a question about the current case..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        if "agent" in st.session_state:
            with st.chat_message("assistant"):
                with st.spinner("Running image analysis and knowledge retrieval..."):
                    try:
                        final_report, preview_img, final_state = st.session_state.agent.run(
                            (dicom_dir or "").strip() or None,
                            prompt,
                        )

                        st.markdown(final_report)

                        warnings = final_state.get("warnings", [])
                        if warnings:
                            with st.expander("Workflow warnings"):
                                for warning in warnings:
                                    st.write(f"- {warning}")

                        if preview_img:
                            preview_placeholder.image(
                                preview_img,
                                caption="AI preview result",
                                use_container_width=True,
                            )
                            st.session_state.last_image = preview_img

                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": final_report,
                                "image": preview_img if preview_img else None,
                            }
                        )
                    except Exception as exc:
                        st.error(f"Error: {exc}")
                        st.exception(exc)
        else:
            st.error("Agent is not initialized. Add your API key in the sidebar.")

st.markdown("---")
st.caption("Research demo only. Clinical use requires separate validation.")
