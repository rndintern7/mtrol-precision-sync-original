import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

# 1. Page Config
st.set_page_config(page_title="Mtrol Precision Analytics", layout="wide")

# --- SIDEBAR LOGO ---
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)

# --- HARDCODED STANDARDS ---
MT3_VALS = {
    "flow": {"ref_range": 200.0, "ppm": None, "unit": "Kg/Hr", "l_range": [0, 320], "dtick": 40},
    "opening": {"ref_range": 100.0, "ppm": 2449.99, "unit": "%", "l_range": [-10, 110], "dtick": 20},
    "p1": {"ref_range": 17.0, "ppm": 21455.76, "unit": "bar", "l_range": [0, 20], "dtick": 2},
    "p2": {"ref_range": 17.0, "ppm": 20355.54, "unit": "bar", "l_range": [0, 20], "dtick": 2}
}

MT4_VALS = {
    "flow": {"ref_range": 500.0, "ppm": None, "unit": "Kg/Hr", "l_range": [0, 550], "dtick": 50},
    "opening": {"ref_range": 100.0, "ppm": 2170.41, "unit": "%", "l_range": [-10, 110], "dtick": 20},
    "p1": {"ref_range": 17.0, "ppm": 129.91, "unit": "bar", "l_range": [0, 20], "dtick": 2},
    "p2": {"ref_range": 17.0, "ppm": 310.21, "unit": "bar", "l_range": [0, 20], "dtick": 2}
}

TEMP_DELTA_FIXED = 89.85

@st.cache_data
def load_and_sync_data(dev_upload, temp_upload):
    df_dev = pd.read_csv(dev_upload)
    time_col = next((c for c in df_dev.columns if "time" in c.lower()), "Time Stamp")
    df_dev[time_col] = pd.to_datetime(df_dev[time_col], errors='coerce')
    
    # Clean non-numeric characters
    targets = ["P1", "P2", "Flow Rate", "% Opening"]
    for col in df_dev.columns:
        if any(t.lower() in col.lower() for t in targets):
            df_dev[col] = pd.to_numeric(df_dev[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce')
    
    # Remove duplicates and sync
    df_dev = df_dev.groupby(time_col).mean().sort_index()
    df_temp = pd.read_csv(temp_upload).dropna(subset=['Timestamp'])
    df_temp['Timestamp'] = pd.to_datetime(df_temp['Timestamp'])
    df_temp = df_temp.groupby('Timestamp').mean().sort_index()
    
    combined = pd.concat([df_dev, df_temp], axis=1)
    combined['Temperature (°C)(Temp)'] = combined['Temperature (°C)(Temp)'].interpolate(method='time')
    
    # Performance Fix: Downsample data if it exceeds 50,000 rows (prevents cursor lag)
    if len(combined) > 50000:
        combined = combined.iloc[::2] # Take every 2nd row to speed up rendering
        
    return combined.loc[df_dev.index[0] : df_dev.index[-1]].reset_index().rename(columns={'index': 'Full_Time'})

# --- MAIN UI ---
st.title("Mtrol Full-Cycle Stability Dashboard")

st.sidebar.header("📁 Data Upload")
device_file = st.sidebar.file_uploader("1. Upload Device CSV", type=['csv'])
temp_file = st.sidebar.file_uploader("2. Upload Chamber_temp_data CSV", type=['csv'])

if device_file and temp_file:
    df = load_and_sync_data(device_file, temp_file)
    device_mode = "Mtrol 4" if "MT4" in device_file.name.upper() else "Mtrol 3"
    data_lookup = MT4_VALS if device_mode == "Mtrol 4" else MT3_VALS
    
    available_params = [c for c in df.columns if any(t in c.lower() for t in ["flow", "opening", "p1", "p2"])]
    
    if available_params:
        selected_param = st.sidebar.selectbox("🎯 Select Parameter to Graph", available_params)
        clean_key = next((k for k in ["flow", "opening", "p1", "p2"] if k in selected_param.lower()), "p1")
        
        # Standards for Calculation
        std = data_lookup[clean_key]
        
        # --- CALC PPM (In background) ---
        c_max, c_min = df[selected_param].expanding().max(), df[selected_param].expanding().min()
        drift = c_max - c_min
        final_ppm = (drift.max() * 1000000) / (TEMP_DELTA_FIXED * std["ref_range"])

        # --- METRICS ---
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Device Mode", device_mode)
        m2.metric(f"Max {selected_param}", f"{df[selected_param].max():.2f}")
        m3.metric("Calculated PPM", f"{final_ppm:.2f}")
        m4.metric("Standard Target", f"{std['ppm']}" if std['ppm'] else "N/A")

        # --- GRAPH (PARAMETER + TEMP) ---
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # Main Parameter Trace (GPU Accelerated)
        fig.add_trace(go.Scattergl(
            x=df['Full_Time'], y=df[selected_param], 
            name=selected_param, line=dict(color="#00CCFF", width=1.5)
        ), secondary_y=False)

        # Chamber Temp Trace
        fig.add_trace(go.Scattergl(
            x=df['Full_Time'], y=df['Temperature (°C)(Temp)'], 
            name="Chamber Temp", line=dict(color="#FFD700", dash='dot', width=2)
        ), secondary_y=True)

        fig.update_layout(
            template="plotly_dark", height=700,
            hovermode="x unified", dragmode="zoom",
            xaxis=dict(title="Time Progress", rangeslider=dict(visible=True, thickness=0.05)),
            yaxis=dict(
                title=f"<b>{selected_param} ({std['unit']})</b>", 
                color="#00CCFF", 
                range=std["l_range"], 
                dtick=std["dtick"],
                fixedrange=False
            ),
            yaxis2=dict(
                title="<b>Chamber Temperature (°C)</b>", 
                color="#FFD700", 
                range=[-20, 70], 
                fixedrange=False
            ),
            legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center")
        )

        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displaylogo': False})

        with st.expander("🔍 View Statistics & Math"):
            st.write(f"Ref Range Used: {std['ref_range']}")
            st.latex(rf"PPM = \frac{{{drift.max():.4f} \times 1,000,000}}{{89.85 \times {std['ref_range}}}}")
else:
    st.info("Upload Device and Chamber CSVs to begin.")
