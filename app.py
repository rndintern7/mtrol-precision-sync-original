import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

st.set_page_config(layout="wide", page_title="Mtrol Precision Sync")

# --- DATA CONSTANTS ---
PPM_DATA = {
    "Mtrol 3": {"Flow Rate": None, "% Opening": 2449.99, "P1": 21455.76, "P2": 20355.54},
    "Mtrol 4": {"Flow Rate": None, "% Opening": 2170.41, "P1": 129.91, "P2": 310.21}
}

# --- STYLING ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #00CCFF !important; }
    [data-testid="stMetricLabel"] { font-size: 16px !important; font-weight: bold !important; }
    </style>
    """, unsafe_allow_html=True)

# --- HEADER ---
h_col1, h_col2 = st.columns([4, 1])
with h_col1:
    st.title("Mtrol Full-Cycle Analysis")
    st.write("### 1s Synchronized Original Data")
with h_col2:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)

# --- UPLOADERS ---
st.sidebar.header("📁 Data Upload")
device_file = st.sidebar.file_uploader("1. Upload Device Data (Original)", type=['csv'])
temp_file = st.sidebar.file_uploader("2. Upload Chamber_temp_data", type=['csv'])

@st.cache_data
def load_and_clean(dev_file, temp_file):
    df_dev = pd.read_csv(dev_file)
    df_dev['Time Stamp'] = pd.to_datetime(df_dev['Time Stamp'])
    
    # CRITICAL: Clean non-numeric values like '**' or 'Message'
    for col in ["P1", "P2", "Flow Rate", "% Opening"]:
        if col in df_dev.columns:
            df_dev[col] = pd.to_numeric(df_dev[col], errors='coerce')
    
    df_temp = pd.read_csv(temp_file).dropna(subset=['Timestamp'])
    df_temp['Timestamp'] = pd.to_datetime(df_temp['Timestamp'])
    
    df_dev = df_dev.set_index('Time Stamp').sort_index()
    df_temp = df_temp.set_index('Timestamp').sort_index()
    
    combined = pd.concat([df_dev, df_temp], axis=1)
    # Sync: Guess temp for every second between 2-minute samples
    combined['Temperature (°C)(Temp)'] = combined['Temperature (°C)(Temp)'].interpolate(method='time')
    
    return combined.loc[df_dev.index[0] : df_dev.index[-1]].reset_index().rename(columns={'index': 'Full_Time'})

if device_file and temp_file:
    device_type = "Mtrol 4" if "MT4" in device_file.name.upper() or "MTROL 4" in device_file.name.upper() else "Mtrol 3"
    df = load_and_clean(device_file, temp_file)
    
    selected = st.sidebar.selectbox("🎯 Select Parameter", ["P1", "P2", "Flow Rate", "% Opening"])

    # --- METRICS ---
    st.write("---")
    m1, m2, m3, m4 = st.columns(4)
    v_max, v_min = df[selected].max(), df[selected].min()
    v_ppm = PPM_DATA[device_type].get(selected, "—")
    unit = "bar" if "P" in selected else ("Kg/Hr" if "Flow" in selected else "%")

    m1.metric("Device Identified", device_type)
    m2.metric(f"MAX {selected}", f"{v_max:.2f} {unit}" if pd.notnull(v_max) else "N/A")
    m3.metric(f"MIN {selected}", f"{v_min:.2f} {unit}" if pd.notnull(v_min) else "N/A")
    m4.metric("PPM Target", f"{v_ppm}")
    st.write("---")

    # --- SCALING ---
    if "flow" in selected.lower(): l_range, l_dtick = [0, 320], 40
    elif "p" in selected.lower(): l_range, l_dtick = [0, 20], 2
    else: l_range, l_dtick = [-20, 70], 10

    # --- PLOT ---
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scattergl(x=df['Full_Time'], y=df[selected], name=selected, line=dict(color="#00CCFF")), secondary_y=False)
    fig.add_trace(go.Scattergl(x=df['Full_Time'], y=df['Temperature (°C)(Temp)'], name="Chamber Temp", line=dict(color="#FFD700", dash='dot')), secondary_y=True)

    fig.update_layout(
        template="plotly_dark", height=650, hovermode="x unified", dragmode="zoom",
        xaxis=dict(title="Time", rangeslider=dict(visible=True), showspikes=True, spikemode="across"),
        yaxis=dict(title=f"<b>{selected} ({unit})</b>", range=l_range, dtick=l_dtick, fixedrange=False),
        yaxis2=dict(title="<b>Chamber Temp (°C)</b>", range=[-20, 70], dtick=10, fixedrange=False),
        legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center")
    )
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
else:
    st.info("👈 Upload your Original Device CSV and Chamber_temp_data CSV to begin.")
