"""Compatibility Streamlit entrypoint.

Run:
    streamlit run app.py
"""

# Importing the frontend module is enough because Streamlit executes the page
# from top-level statements in that module.
from frontend import streamlit_app as streamlit_app  # noqa: F401
