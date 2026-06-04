"""
streamlit_app.py — web UI for the demo.

Run:
    python seed.py                  # build the database first
    streamlit run streamlit_app.py  # opens at http://localhost:8501

This is a THIN shell over query_engine.route(). It does not reimplement any
query logic and opens no writable database connection — all data access goes
through the read-only engine.
"""

import os
import streamlit as st
from query_engine import route

DB = os.path.join(os.path.dirname(__file__), "gas_renovation.db")

st.set_page_config(page_title="Renovation Project Assistant", page_icon="🏗️")

st.title("Renovation Project Assistant")
st.caption(
    "Ask about any site in plain English — materials status, permits, photos, "
    "design art, shipping, or contracts."
)
st.info("Read-only assistant: it retrieves and presents data, and can never change it.", icon="🔒")

if not os.path.exists(DB):
    st.error("Database not found. Run `python seed.py` first, then reload.")
    st.stop()

if "history" not in st.session_state:
    st.session_state.history = []

EXAMPLES = [
    "Have we ordered materials for the Warner Robins site?",
    "What about Gainesville — have we ordered materials there?",
    "Have we ordered anything for Flowery Branch yet?",
    "What's the holdup on the Warner Robins sign permit?",
    "Pull up the main ID render for Warner Robins.",
    "Are there any site photos for Flowery Branch?",
    "When are the canopy materials for Warner Robins expected to ship?",
    "Show me the contract for Gainesville.",
]

with st.sidebar:
    st.subheader("Sample sites")
    st.markdown(
        "- Next Level Petroleum — Warner Robins\n"
        "- QuikFuel — Gainesville\n"
        "- Star Mart — Flowery Branch"
    )
    st.subheader("Try asking")
    for ex in EXAMPLES:
        if st.button(ex, key=ex, use_container_width=True):
            st.session_state.pending = ex

default_q = st.session_state.pop("pending", "")
q = st.text_input("Your question", value=default_q, placeholder="e.g. Have we ordered materials for Warner Robins?")

col1, col2 = st.columns([1, 5])
with col1:
    ask = st.button("Ask", type="primary", use_container_width=True)
with col2:
    if st.button("Clear", use_container_width=True):
        st.session_state.history = []

if (ask or default_q) and q:
    try:
        answer = route(q)["answer"]
    except Exception as e:  # the engine refuses anything non-read-only
        answer = f"Refused: {e}"
    st.session_state.history.insert(0, (q, answer))

for question, answer in st.session_state.history:
    st.markdown(f"**> {question}**")
    st.markdown(answer.replace("\n", "  \n"))
    st.divider()
