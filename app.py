import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import re

# 1. Page Config
st.set_page_config(page_title="Mtrol Precision Analytics", layout="wide")

# --- SIDEBAR LOGO ---
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)

# --- HARDCODED STANDARDS ---
MT3_VALS = {
    "flow": {"ref_range": 200.0, "ppm": None, "unit": "Kg/Hr"},
    "opening": {"ref_range": 100.0, "ppm": 2449.99, "unit": "%"},
    "p1": {"ref_range": 17.0, "ppm": 21455.76, "unit": "bar"},
    "p2": {"ref_range": 17.0, "ppm": 20355.54, "unit": "bar"}
}

MT4_VALS = {
    "flow": {"ref_range": 500.0, "ppm": None, "unit": "Kg/Hr"},
    "opening": {"ref_range": 100.0, "ppm": 2170.41, "unit": "%"},
    "p1": {"ref_range": 17.0, "ppm": 129.91, "unit": "bar"},
    "p2": {"ref_range": 17.0, "ppm": 310.21, "unit": "bar"}
}

TEMP_DELTA_FIXED = 89.85

# --- DATA CLEANING & SYNC ---
@st.cache_data
def load_and_sync_data(dev_upload, temp_upload):
    # Load Device Data
    df_dev = pd.read_csv(dev_upload)
    time_col = next((c for c in df_dev.columns if "time" in c.lower()), "Time Stamp")
    df_dev[time_col] = pd.to_datetime(df_dev[time_col], errors='coerce')
    
    # Clean non-numeric characters (**, Message, etc.)
    targets = ["P1", "P2", "Flow Rate", "% Opening"]
    for col in df_dev.columns:
        if any(t.lower() in col.lower() for t in targets):
            df_dev[col] = pd.to_numeric(df_dev[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce')
    
    # FIX: Handle Duplicate Timestamps in Device Data
    df_dev = df_dev.groupby(time_col).mean().sort_index()
    
    # Load Temp Data
    df_temp = pd.read_csv(temp_upload).dropna(subset=['Timestamp'])
    df_temp['Timestamp'] = pd.to_datetime(df_temp['Timestamp'])
    
    # FIX: Handle Duplicate Timestamps in Temp Data (if any)
    df_temp = df_temp.groupby('Timestamp').mean().sort_index()
    
    # Sync Indices (Both are now unique)
    combined = pd.concat([df_dev, df_temp], axis=1)
    
    # Interpolate (1s Sync)
    combined['Temperature (°C)(Temp)'] = combined['Temperature (°C)(Temp)'].interpolate(method='time')
    
    # Trim to device window
    return combined.loc[df_dev.index[0] : df_dev.index[-1]].reset_index().rename(columns={'index': 'Full_Time'})

# --- MAIN UI ---
st.title("Mtrol Full-Cycle Stability Dashboard")

st.sidebar.header("📁 Data Upload")
device_file = st.sidebar.file_uploader("1. Upload Device CSV", type=['csv'])
temp_file = st.sidebar.file_uploader("2. Upload Chamber_temp_data CSV", type=['csv'])

st.sidebar.header("Analysis Settings")
smooth_data = st.sidebar.toggle("Enable Signal Smoothing", value=True)
window_size = st.sidebar.slider("Smoothing Window (sec)", 5, 100, 20) if smooth_data else 1

if device_file and temp_file:
    # Use a try-except block to catch any remaining processing issues
    try:
        df = load_and_sync_data(device_file, temp_file)
        device_mode = "Mtrol 4" if "MT4" in device_file.name.upper() or "MTROL 4" in device_file.name.upper() else "Mtrol 3"
        data_lookup = MT4_VALS if device_mode == "Mtrol 4" else MT3_VALS
        
        available_params = [c for c in df.columns if any(t in c.lower() for t in ["flow", "opening", "p1", "p2"])]
        
        if available_params:
            selected_param = st.sidebar.selectbox("🎯 Select Parameter", available_params)
            clean_key = next((k for k in ["flow", "opening", "p1", "p2"] if k in selected_param.lower()), "p1")
            
            ref_range = data_lookup[clean_key]["ref_range"]
            target_ppm = data_lookup[clean_key]["ppm"]
            unit = data_lookup[clean_key]["unit"]

            # --- CALCULATIONS ---
            raw_series = df[selected_param]
            clean_series = raw_series.rolling(window=window_size, center=True).mean() if smooth_data else raw_series
            
            c_max = clean_series.expanding().max()
            c_min = clean_series.expanding().min()
            drift = c_max - c_min
            df['PPM_Stability'] = (drift * 1000000) / (TEMP_DELTA_FIXED * ref_range)

            # --- METRICS ---
            st.subheader(f"📊 {selected_param} Performance ({device_mode})")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Final Stability", f"{df['PPM_Stability'].iloc[-1]:.2f} PPM")
            m2.metric("Max Drift Observed", f"{drift.max():.4f} {unit}")
            m3.metric("Reference Scale", f"{ref_range} {unit}")
            m4.metric("Target PPM (Standard)", f"{target_ppm}" if target_ppm else "N/A")

            # --- GRAPH ---
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            fig.add_trace(go.Scattergl(
                x=df['Full_Time'], y=df['PPM_Stability'], 
                name="Stability (PPM)", line=dict(color="#00CCFF", width=2)
            ), secondary_y=False)

            fig.add_trace(go.Scattergl(
                x=df['Full_Time'], y=df['Temperature (°C)(Temp)'], 
                name="Chamber Temp", line=dict(color="#FFD700", dash='dot')
            ), secondary_y=True)

            fig.update_layout(
                template="plotly_dark", height=600,
                hovermode="x unified", dragmode="zoom",
                xaxis=dict(title="Time Progress", rangeslider=dict(visible=True, thickness=0.05)),
                yaxis=dict(title="<b>Stability (PPM)</b>", color="#00CCFF", fixedrange=False),
                yaxis2=dict(title="<b>Chamber Temp (°C)</b>", color="#FFD700", side='right', fixedrange=False),
                legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center")
            )

            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

            with st.expander("🔍 View Math Breakdown"):
                st.latex(rf"PPM = \frac{{({c_max.max():.4f} - {c_min.min():.4f}) \times 1,000,000}}{{89.85 \times {ref_range}}}")

        else:
            st.warning("Could not identify Mtrol parameters in the file.")
            
    except Exception as e:
        st.error(f"Error processing files: {e}")
else:
    st.info("Upload Device and Chamber CSVs to begin.")
