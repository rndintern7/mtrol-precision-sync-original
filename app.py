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
def process_data(dev_upload, temp_upload):
    # --- Load Chamber Temp Data ---
    df_temp = pd.read_csv(temp_upload)
    # Drop leading empty rows/headers often found in chamber data
    df_temp = df_temp.dropna(subset=[df_temp.columns[0], df_temp.columns[1]], how='any')
    df_temp.columns = ['Timestamp', 'Chamber_Temp']
    df_temp['Timestamp'] = pd.to_datetime(df_temp['Timestamp'], errors='coerce')
    df_temp = df_temp.dropna(subset=['Timestamp']).groupby('Timestamp').mean().sort_index()

    # --- Load Device Data ---
    df_dev = pd.read_csv(dev_upload)
    time_col = next((c for c in df_dev.columns if "time" in c.lower()), "Time Stamp")
    df_dev[time_col] = pd.to_datetime(df_dev[time_col], errors='coerce')
    
    # Clean numeric columns (P1, P2, etc) from non-numeric noise
    targets = ["P1", "P2", "Flow Rate", "% Opening"]
    for col in df_dev.columns:
        if any(t.lower() in col.lower() for t in targets):
            df_dev[col] = pd.to_numeric(df_dev[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce')
    
    # Average any duplicate 1s records
    df_dev = df_dev.groupby(time_col).mean().sort_index()
    
    # --- Synchronize ---
    # Merge and interpolate 2-min chamber data to 1-sec device timestamps
    combined = pd.concat([df_dev, df_temp], axis=1)
    combined['Chamber_Temp'] = combined['Chamber_Temp'].interpolate(method='time')
    
    # PERFORMANCE: Downsample for smooth rendering if data is huge
    if len(combined) > 30000:
        step = len(combined) // 30000
        combined = combined.iloc[::step]
        
    return combined.loc[df_dev.index[0] : df_dev.index[-1]].reset_index().rename(columns={'index': 'Full_Time'})

# --- MAIN UI ---
st.title("Mtrol Full-Cycle Analytics")

# Sidebar Uploads
st.sidebar.header("📁 Data Sources")
device_file = st.sidebar.file_uploader("1. Device CSV (Original Data)", type=['csv'])
temp_file = st.sidebar.file_uploader("2. Chamber Temp CSV", type=['csv'])

if device_file and temp_file:
    try:
        df = process_data(device_file, temp_file)
        
        # Identify Device Mode
        device_mode = "Mtrol 4" if "MT4" in device_file.name.upper() else "Mtrol 3"
        data_lookup = MT4_VALS if device_mode == "Mtrol 4" else MT3_VALS
        
        # 1. STANDALONE CHAMBER TEMP PLOT
        st.subheader("🌡️ 1. Chamber Temperature Profile")
        t_fig = go.Figure()
        t_fig.add_trace(go.Scattergl(x=df['Full_Time'], y=df['Chamber_Temp'], name="Temp", line=dict(color="#FFD700")))
        t_fig.update_layout(template="plotly_dark", height=250, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(t_fig, use_container_width=True)

        st.divider()

        # 2. SELECTABLE SYNCHRONIZED PARAMETER PLOT
        available_params = [c for c in df.columns if any(t in c.lower() for t in ["flow", "opening", "p1", "p2"])]
        
        if available_params:
            selected_param = st.sidebar.selectbox("🎯 Select Parameter to Graph", available_params)
            clean_key = next((k for k in ["flow", "opening", "p1", "p2"] if k in selected_param.lower()), "p1")
            std = data_lookup[clean_key]
            
            # PPM Calculation Logic
            drift = df[selected_param].expanding().max() - df[selected_param].expanding().min()
            final_ppm = (drift.max() * 1000000) / (TEMP_DELTA_FIXED * std["ref_range"])

            # Metrics Row
            st.subheader(f"📊 2. Synchronized: {selected_param} vs Chamber Temp")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Device", device_mode)
            m2.metric(f"Max {selected_param}", f"{df[selected_param].max():.2f} {std['unit']}")
            m3.metric("Calculated PPM", f"{final_ppm:.2f}")
            m4.metric("Chamber ΔT", f"{TEMP_DELTA_FIXED}°C")

            # Main Synchronized Graph
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Trace 1: Selected Parameter
            fig.add_trace(go.Scattergl(
                x=df['Full_Time'], y=df[selected_param], 
                name=selected_param, line=dict(color="#00CCFF", width=1.5)
            ), secondary_y=False)

            # Trace 2: Chamber Temp
            fig.add_trace(go.Scattergl(
                x=df['Full_Time'], y=df['Chamber_Temp'], 
                name="Chamber Temp", line=dict(color="#FFD700", dash='dot', width=2)
            ), secondary_y=True)

            fig.update_layout(
                template="plotly_dark", height=600,
                hovermode="x unified", dragmode="zoom",
                xaxis=dict(title="Timeline", rangeslider=dict(visible=True, thickness=0.05)),
                yaxis=dict(title=f"<b>{selected_param} ({std['unit']})</b>", color="#00CCFF", range=std["l_range"], dtick=std["dtick"], fixedrange=False),
                yaxis2=dict(title="<b>Chamber Temp (°C)</b>", color="#FFD700", side='right', range=[-20, 70], fixedrange=False),
                legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center")
            )
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displaylogo': False})

            # Math Breakdown Expander
            with st.expander("🔍 View Statistics & Math"):
                st.write(f"Ref Range (Denominator): {std['ref_range']}")
                st.write(f"Total Drift Observed: {drift.max():.4f}")
                l_formula = r"PPM = \frac{" + f"{drift.max():.4f}" + r" \times 1,000,000}{89.85 \times " + f"{std['ref_range']}" + r"}"
                st.latex(l_formula)
        else:
            st.error("No valid Mtrol parameters (P1, P2, Flow, Opening) found in CSV.")

    except Exception as e:
        st.error(f"Critical Error: {e}")
else:
    st.info("👈 Please upload your Device and Chamber data in the sidebar.")
