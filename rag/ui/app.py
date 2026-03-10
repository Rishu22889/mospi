"""
Streamlit web UI for the MoSPI RAG chatbot.

Features:
- Input box with streaming responses
- Source snippets and clickable links
- k and temperature sliders
- Chat history
"""
import json
import os
import time
import requests
import streamlit as st

NO_DATA_PHRASES = [
    "don't have that in my data",
    "i don't have that",
    "not found in my data",
    "not in my data",
    "no information in my data",
]

def has_real_answer(text: str) -> bool:
    return not any(p in text.lower() for p in NO_DATA_PHRASES)


API_URL = os.getenv("API_URL", "http://api:8000")

# ── Page config ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="MoSPI Q&A Chatbot",
    page_icon="📊",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
.citation-box {
    background: #f0f4ff;
    border-left: 4px solid #4c6ef5;
    padding: 10px 14px;
    border-radius: 4px;
    margin: 6px 0;
    font-size: 0.88rem;
}
.citation-box a { color: #2c50b5; text-decoration: none; }
.citation-box a:hover { text-decoration: underline; }
.snippet-text { color: #555; font-style: italic; margin-top: 4px; }
.stat-card {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px 16px;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.image("rag/ui/assets/logo.png", width=200, caption="MoSPI")
    st.title("⚙️ Settings")

    top_k = st.slider("Number of sources (k)", min_value=1, max_value=10,
                      value=5, help="How many document chunks to retrieve")
    temperature = st.slider("Temperature", min_value=0.0, max_value=1.0,
                             value=0.1, step=0.05,
                             help="Higher = more creative, lower = more factual")
    use_mmr = st.toggle("Use MMR (diversity)", value=True,
                         help="Maximal Marginal Relevance reduces redundant sources")

    st.divider()
    st.subheader("🔄 Data Management")
    if st.button("Rebuild Index", type="secondary"):
        with st.spinner("Triggering ETL pipeline..."):
            try:
                r = requests.post(f"{API_URL}/ingest", timeout=10)
                if r.status_code == 200:
                    st.success("Ingestion started in background!")
                else:
                    st.error(f"Failed: {r.text}")
            except Exception as e:
                st.error(f"Could not reach API: {e}")

    st.divider()
    # Health check
    try:
        health = requests.get(f"{API_URL}/health", timeout=3).json()
        col1, col2 = st.columns(2)
        with col1:
            status = "🟢" if health.get("ollama_healthy") else "🔴"
            st.markdown(f"{status} **LLaMA**")
        with col2:
            status = "🟢" if health.get("index_loaded") else "🔴"
            st.markdown(f"{status} **Index**")
    except Exception:
        st.warning("⚠️ API offline")

# ── Main UI ───────────────────────────────────────────────────────────
st.title("📊 MoSPI Statistical Data Q&A")
st.caption("Ask questions about Indian economic statistics — powered by LLaMA 3 + RAG")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("citations") and has_real_answer(msg.get("content", "")):
            with st.expander(f"📚 Sources ({len(msg['citations'])})"):
                for cit in msg["citations"]:
                    snippet = cit.get("snippet", "")
                    st.markdown(
                        f"""<div class="citation-box">
                            <a href="{cit['url']}" target="_blank">🔗 {cit['title']}</a>
                            <div class="snippet-text">{snippet[:200]}...</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

# Suggested questions
if not st.session_state.messages:
    st.markdown("### 💡 Try asking:")
    example_qs = [
        "What is India's latest GDP growth rate?",
        "What was the CPI inflation in January 2024?",
        "What is the Index of Industrial Production for manufacturing?",
        "What are the latest employment statistics from MoSPI?",
    ]
    cols = st.columns(2)
    for i, q in enumerate(example_qs):
        if cols[i % 2].button(q, key=f"ex_{i}"):
            st.session_state["prefill_question"] = q
            st.rerun()

# Chat input
prefill = st.session_state.pop("prefill_question", None)
question = st.chat_input("Ask about Indian economic statistics...") or prefill

if question:
    # Add user message
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Stream response
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        citations_data = []
        full_answer = ""

        try:
            with requests.post(
                f"{API_URL}/ask/stream",
                json={
                    "question": question,
                    "k": top_k,
                    "temperature": temperature,
                    "use_mmr": use_mmr,
                },
                stream=True,
                timeout=120,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            data = json.loads(line[6:])
                            if "token" in data:
                                full_answer += data["token"]
                                response_placeholder.markdown(full_answer + "▌")
                            if data.get("done"):
                                citations_data = data.get("citations", [])

            response_placeholder.markdown(full_answer)

            # Show citations
            if citations_data and has_real_answer(full_answer):
                with st.expander(f"📚 Sources ({len(citations_data)})"):
                    for cit in citations_data:
                        st.markdown(
                            f"""<div class="citation-box">
                                <a href="{cit['url']}" target="_blank">🔗 {cit['title']}</a>
                            </div>""",
                            unsafe_allow_html=True,
                        )

        except requests.exceptions.ConnectionError:
            full_answer = "⚠️ Cannot connect to the API server. Make sure `docker compose up` is running."
            response_placeholder.error(full_answer)
        except Exception as e:
            full_answer = f"⚠️ Error: {str(e)}"
            response_placeholder.error(full_answer)

    # Save to history
    st.session_state.messages.append({
        "role": "assistant",
        "content": full_answer,
        "citations": citations_data,
    })

# ── Footer ────────────────────────────────────────────────────────────
st.divider()
st.caption("Data sourced from mospi.gov.in · Powered by LLaMA 3 via Ollama · Built with Streamlit + FastAPI + FAISS")
