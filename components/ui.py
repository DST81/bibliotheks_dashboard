import streamlit as st

def kpi_box(title, current, previous=None, previous_label="Vorjahr gesamt"):
    if isinstance(previous, (int, float)):
        previous_text = f"Vorjahr gesamt: {previous:,}".replace(",", "'")
    elif previous is not None:
        previous_text = str(previous)
    else:
        previous_text = ""

    current_text = f"{current:,}".replace(",", "'")

    st.markdown(f"""
    <div style="
        border:1px solid #E6E6E6;
        border-radius:12px;
        padding:15px;
        background:white;
        box-shadow:0 2px 6px rgba(0,0,0,0.05);
    ">
        <div style="font-size:14px;color:#666;">{title}</div>
        <div style="font-size:32px;font-weight:700;color:#264653;">
            {current_text}
        </div>
        <div style="
            font-size:13px;
            color:#666;
            margin-top:8px;
            line-height:1.4;
            text-align:left;
        ">
            {previous_text}
        </div>
    </div>
    """, unsafe_allow_html=True)
