import streamlit as st
from agent_groq import run_agent

st.set_page_config(
    page_title="PGx Agent",
    page_icon="🧬",
    layout="wide"
)

st.title("Pharmacogenomics Agent")
st.markdown("Powered by Groq + MyGene + MyVariant + PharmGKB + PubChem")

query = st.text_input(
    "Ask about a gene, variant, or drug",
    placeholder="What does BRCA1 do?"
)

if st.button("Submit"):
    with st.spinner("Analyzing..."):
        answer = run_agent(query)

    st.markdown("### Response")
    st.write(answer)

st.sidebar.header("Demo Questions")
st.sidebar.button("What does BRCA1 do?")
st.sidebar.button("Tell me about rs4244285")
st.sidebar.button("What is Warfarin?")