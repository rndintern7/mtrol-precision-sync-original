import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# Page Config
st.set_page_config(page_title="Mtrol PPM Dashboard", layout="wide")

# 1. SIDEBAR CONTROLS
st.sidebar.header("📊 Control Panel")

device = st.sidebar.selectbox("Select Device", ["Mtrol 3", "Mtrol 4"])
param_choice = st.sidebar.selectbox("Select Parameter", 
                                    ["1: Flow Rate", "2: % Opening", "3: P1", "4: P2"])
target_temp = st.sidebar.slider("Target Temperature (°C)", -20.0, 70.0, 70.0, 0.5)
tolerance = st.sidebar.slider("Tolerance (+/- °C)", 0.1, 5.0, 1.0)

# 2. COLOR PALETTE (8 Colors)
color_palette = {
    'Mtrol 3': {'1: Flow Rate': '#1f77b4', '2: % Opening': '#2ca02c', '3: P1': '#ff7f0e', '4: P2': '#9467bd'},
    'Mtrol 4': {'1: Flow Rate': '#d62728', '2: % Opening': '#17becf', '3: P1': '#bcbd22', '4: P2': '#e377c2'}
}

# 3. LOAD DATA
@st.cache_data # This makes the website fast
def load_data(dev):
    if dev == "Mtrol 3":
        file = 'Mtrol_3_11-13_March_2min_Average - Mtrol_3_11-13_March_2min_Average.csv.csv'
    else:
        file = 'Mtrol_4_11-13_March_2min_Average - Mtrol_4_11-13_March_2min_Average.csv.csv'
    df = pd.read_csv(file)
    df['Time Stamp'] = pd.to_datetime(df['Time Stamp'])
    return df

try:
    df = load_data(device)
    param_map = {'1: Flow Rate': 'Flow Rate', '2: % Opening': '% Opening', '3: P1': 'P1', '4: P2': 'P2'}
    col = param_map[param_choice]

    # Filter Logic
    mask = (df['Chamber Temperature (°C)'] >= target_temp - tolerance) & \
           (df['Chamber Temperature (°C)'] <= target_temp + tolerance)
    df_fixed = df[mask].copy()

    if not df_fixed.empty:
        # PPM Calculation
        mean_val = df_fixed[col].mean()
        df_fixed['PPM'] = ((df_fixed[col] - mean_val) / mean_val) * 1_000_000

        # 4. PLOTLY GRAPH
        fig = go.Figure()
        selected_color = color_palette[device][param_choice]
        
        # Main Trace
        fig.add_trace(go.Scatter(
            x=df_fixed['Time Stamp'], y=df_fixed['PPM'],
            mode='lines+markers',
            line=dict(color=selected_color, width=3),
            name=f"ACTIVE: {device} {col}"
        ))

        # Add Legend Reference Traces
        for d in ['Mtrol 3', 'Mtrol 4']:
            for p, color in color_palette[d].items():
                fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers',
                                         marker=dict(color=color, size=10),
                                         name=f"{d} {p.split(': ')[1]}"))

        fig.update_layout(
            title=f"<b>{device} Stability: {col}</b> (Temp: {target_temp}°C ±{tolerance})",
            xaxis=dict(title="Time Stamp", rangeslider=dict(visible=True)),
            yaxis=dict(title="PPM Deviation"),
            legend=dict(title="Color Key", yanchor="top", y=1, xanchor="left", x=1.02),
            height=700, template="plotly_white"
        )

        st.plotly_chart(fig, use_container_width=True)
        
        # 5. STATS SUMMARY
        col1, col2, col3 = st.columns(3)
        col1.metric("Average Value", f"{mean_val:.4f}")
        col2.metric("Max PPM", f"{df_fixed['PPM'].max():.2f}")
        col3.metric("Min PPM", f"{df_fixed['PPM'].min():.2f}")

    else:
        st.warning(f"No data found for {target_temp}°C within ±{tolerance}°C tolerance.")

except FileNotFoundError:
    st.error("CSV files not found. Please ensure they are in the same folder as app.py")