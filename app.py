import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import warnings
import io
warnings.filterwarnings('ignore')

# Configuración de la página
st.set_page_config(page_title="Quant Report: Trading The Fear Index", layout="wide")

# --- INYECCIÓN DE CSS PARA TEMA OSCURO Y TABLAS PROFESIONALES ---
st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    [data-testid="stSidebar"] { background-color: #1A1C23; border-right: 1px solid #333333; }
    [data-testid="stMetric"] { background-color: #1E1E1E; border: 1px solid #333333; padding: 15px; border-radius: 8px; }
    [data-testid="stMetricLabel"] { color: #B0B0B0 !important; font-size: 14px !important; }
    [data-testid="stMetricValue"] { color: #FAFAFA !important; font-size: 22px !important; font-weight: bold !important; }
    [data-testid="stDataFrame"] { border: 1px solid #333333; border-radius: 8px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #1E1E1E; border-radius: 4px 4px 0px 0px; color: #B0B0B0; }
    .stTabs [aria-selected="true"] { background-color: #2962FF !important; color: #FFFFFF !important; }
    .stSelectbox label, .stMarkdown { color: #E0E0E0 !important; }
    </style>
""", unsafe_allow_html=True)

# --- CARGA Y PROCESAMIENTO DE DATOS ---
@st.cache_data(ttl=3600)
def load_and_process_data():
    try:
        with st.spinner("Descargando datos históricos..."):
            spy_raw = yf.Ticker("SPY").history(start="1990-01-01")
            vix_raw = yf.Ticker("^VIX").history(start="1990-01-01")
    except Exception as exc:
        st.error(f"❌ Error al descargar datos: {exc}")
        st.stop()

    if spy_raw.empty or vix_raw.empty:
        st.error("❌ Error al descargar datos de SPY o VIX.")
        st.stop()

    spy = spy_raw[['Open', 'High', 'Low', 'Close']]
    vix = vix_raw[['Open', 'High', 'Low', 'Close']]
    if spy.index.tz is not None: spy.index = spy.index.tz_localize(None)
    if vix.index.tz is not None: vix.index = vix.index.tz_localize(None)
    
    vix.columns = ['VIXO', 'VIXH', 'VIXL', 'VIX']
    df = pd.concat([spy, vix], axis=1).dropna()
    if df.empty: st.error("❌ Error alineando fechas."); st.stop()

    # Indicadores
    VBARS, RCBARS, STBARSS, STBARSL = 6, 5, 10, 25
    df['VIX_L_6'] = df['VIXL'].rolling(VBARS).min().shift(1)
    df['VIXUP'] = (df['VIXH'] / df['VIX_L_6'] - 1) * 100
    df['VIX_H_6'] = df['VIX'].rolling(VBARS).max().shift(1)
    df['VIXDN'] = (df['VIX'] / df['VIX_H_6'] - 1) * 100
    
    y_arr = np.arange(1, RCBARS + 1)
    mean_y, std_y = y_arr.mean(), y_arr.std()
    def calc_E_xy(x): return np.dot(x, y_arr) / RCBARS
    E_xy = df['VIX'].rolling(RCBARS).apply(calc_E_xy, raw=True)
    E_x = df['VIX'].rolling(RCBARS).mean()
    std_x = df['VIX'].rolling(RCBARS).std()
    df['RC'] = (E_xy - E_x * mean_y) / (std_x * std_y + 1e-10)
    
    df['STOCHVS'] = (df['VIX'] - df['VIXL'].rolling(STBARSS).min()) / (df['VIXH'].rolling(STBARSS).max() - df['VIXL'].rolling(STBARSS).min() + 0.0001) * 100
    df['STVIXS'] = df['STOCHVS'].rolling(3).mean()
    df['STOCHSS'] = (df['Close'] - df['Low'].rolling(STBARSS).min()) / (df['High'].rolling(STBARSS).max() - df['Low'].rolling(STBARSS).min() + 0.0001) * 100
    df['STSPYS'] = df['STOCHSS'].rolling(3).mean()
    df['STOCHVL'] = (df['VIX'] - df['VIXL'].rolling(STBARSL).min()) / (df['VIXH'].rolling(STBARSL).max() - df['VIXL'].rolling(STBARSL).min() + 0.0001) * 100
    df['STVIXL'] = df['STOCHVL'].rolling(3).mean()
    df['STOCHSL'] = (df['Close'] - df['Low'].rolling(STBARSL).min()) / (df['High'].rolling(STBARSL).max() - df['Low'].rolling(STBARSL).min() + 0.0001) * 100
    df['STSPYL'] = df['STOCHSL'].rolling(3).mean()
    
    # Señales
    cond1 = df['VIXUP'] > 50
    cond2 = (df['RC'] > 0.8) & (df['RC'] > df['RC'].shift(1))
    cond3 = (df['STVIXL'] > df['STSPYL']) & (df['STVIXS'] > df['STSPYS']) & (df['STVIXS'] > df['STVIXS'].shift(1))
    df['Signal_Exit'] = cond1 & cond2 & cond3
    cond_entry1 = df['STSPYS'] > df['STVIXS']
    cond_entry2 = df['STVIXS'] < df['STVIXS'].shift(1)
    df['Signal_Entry'] = cond_entry1 | cond_entry2
    
    df['Exit_Exec'] = df['Signal_Exit'].shift(1).fillna(False)
    df['Entry_Exec'] = df['Signal_Entry'].shift(1).fillna(False)
    
    in_market = np.zeros(len(df), dtype=bool)
    if len(df) > 0: in_market[0] = True
    for i in range(1, len(df)):
        if in_market[i-1]: in_market[i] = False if df['Exit_Exec'].iloc[i] else True
        else: in_market[i] = True if df['Entry_Exec'].iloc[i] else False
            
    df['In_Market'] = in_market
    df['SPY_Return'] = df['Close'].pct_change(fill_method=None)
    df['Strategy_Return'] = df['In_Market'].astype(int) * df['SPY_Return']
    df['Equity'] = (1 + df['Strategy_Return'].fillna(0)).cumprod() * 10000
    df['Benchmark'] = (df['Close'] / df['Close'].iloc[0]) * 10000
    
    return df

df_full = load_and_process_data()

# --- SIDEBAR ---
st.sidebar.title("⚙️ Configuración")
period = st.sidebar.selectbox("Periodo de datos", ["Max", "10y", "5y", "3y"], index=0)
df = df_full.copy()
if period == "3y": df = df[df.index >= (datetime.datetime.now() - pd.DateOffset(years=3))]
elif period == "5y": df = df[df.index >= (datetime.datetime.now() - pd.DateOffset(years=5))]
elif period == "10y": df = df[df.index >= (datetime.datetime.now() - pd.DateOffset(years=10))]
if df.empty: st.error("❌ No hay datos."); st.stop()

indicator_options_list = ["VIXUP / VIXDN (%)", "RC (Tendencia Correlación)", "Estocástico Rápido (10)", "Estocástico Lento (25)"]
num_indicators = st.sidebar.selectbox("Número de indicadores", [1, 2, 3], index=1)
selected_indicators = []
for i in range(num_indicators):
    available_options = [opt for opt in indicator_options_list if opt not in selected_indicators]
    if available_options: selected_indicators.append(st.sidebar.selectbox(f"Indicador {i+1}", available_options, index=0))

# --- LEYENDA RECUPERADA DE LA ESTRATEGIA ---
st.sidebar.markdown("---")
st.sidebar.markdown("### 📖 Sobre la Estrategia")
st.sidebar.markdown("""
**Basado en *Trading The Fear Index* de Markos Katsanos.**

🔴 **Señal de SALIDA del SPY (Pánico):**
* **VIXUP > 50%:** El VIX sube más del 50% en 6 días.
* **RC > 0.8:** Tendencia de correlación del VIX acelerada.
* **Estocásticos:** El estocástico del VIX (10 y 25 días) supera al del SPY.

🟢 **Señal de REENTRADA al SPY:**
* **STSPYS > STVIXS:** El estocástico rápido del SPY supera al del VIX.
* **O bien:** El estocástico del VIX pierde impulso (cae respecto al día anterior).

⚙️ **Ejecución:**
Las señales se ejecutan a la **apertura del día siguiente** (*shift(1)*) para evitar *look-ahead bias*.
""")

# --- GRÁFICO PRINCIPAL ---
st.title("📈 SPY & VIX: Trading The Fear Index")
indicator_map = {"VIXUP / VIXDN (%)": ["VIXUP", "VIXDN"], "RC (Tendencia Correlación)": ["RC"], "Estocástico Rápido (10)": ["STVIXS", "STSPYS"], "Estocástico Lento (25)": ["STVIXL", "STSPYL"]}
num_subplots = 1 + len(selected_indicators)
row_heights = [0.6] + [0.4 / len(selected_indicators)] * len(selected_indicators) if selected_indicators else [1.0]
fig = make_subplots(rows=num_subplots, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights, subplot_titles=["SPY"] + selected_indicators)
fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='SPY', increasing_line_color='#26A69A', decreasing_line_color='#EF5350'), row=1, col=1)
colors = ['#2962FF', '#FF6D00', '#AB47BC', '#00ACC1']
for idx, ind_name in enumerate(selected_indicators):
    row_num = idx + 2
    for c_idx, col in enumerate(indicator_map[ind_name]):
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=col, line=dict(color=colors[c_idx % len(colors)], width=2)), row=row_num, col=1)
    if ind_name == "RC (Tendencia Correlación)": fig.add_hline(y=0.8, line_dash="dash", line_color="red", row=row_num, col=1)
fig.update_layout(template='plotly_dark', xaxis_rangeslider_visible=False, height=700, margin=dict(l=50, r=50, t=50, b=50), plot_bgcolor='#0E1117', paper_bgcolor='#0E1117')
st.plotly_chart(fig, use_container_width=True)

# ==============================================================================
# MOTOR DE ANÁLISIS CUANTITATIVO AVANZADO
# ==============================================================================

strat_ret = df['Strategy_Return'].dropna()
bench_ret = df['SPY_Return'].dropna()
equity = df['Equity']
benchmark = df['Benchmark']
rf_daily = 0.04 / 252

# 1. CÁLCULO DE TRADES (DETALLADO PARA EXPORTACIÓN)
trades_data = []
in_trade = False
entry_idx = 0
entry_price = 0
entry_date = None

for i in range(len(df)):
    if df['In_Market'].iloc[i] and not in_trade:
        in_trade = True
        entry_price = df['Open'].iloc[i]  # Precio de ejecución real (Open del día)
        entry_date = df.index[i]
        entry_idx = i
    elif not df['In_Market'].iloc[i] and in_trade:
        in_trade = False
        exit_price = df['Open'].iloc[i]  # Precio de ejecución real (Open del día)
        exit_date = df.index[i]
        ret = (exit_price / entry_price) - 1
        duration = i - entry_idx
        trades_data.append({
            'Fecha Entrada': entry_date,
            'Precio Entrada': entry_price,
            'Fecha Salida': exit_date,
            'Precio Salida': exit_price,
            'Retorno (%)': ret * 100,
            'Duración (días)': duration,
            'Resultado': 'Ganancia' if ret > 0 else 'Pérdida'
        })

# Si al final del periodo seguimos en mercado, cerrar la operación
if in_trade:
    exit_price = df['Close'].iloc[-1]
    exit_date = df.index[-1]
    ret = (exit_price / entry_price) - 1
    duration = len(df) - 1 - entry_idx
    trades_data.append({
        'Fecha Entrada': entry_date,
        'Precio Entrada': entry_price,
        'Fecha Salida': exit_date,
        'Precio Salida': exit_price,
        'Retorno (%)': ret * 100,
        'Duración (días)': duration,
        'Resultado': 'Ganancia' if ret > 0 else 'Pérdida'
    })

trades_df = pd.DataFrame(trades_data) if trades_data else pd.DataFrame(columns=['Fecha Entrada', 'Precio Entrada', 'Fecha Salida', 'Precio Salida', 'Retorno (%)', 'Duración (días)', 'Resultado'])

# Cálculos estadísticos sobre los trades
wins = trades_df[trades_df['Retorno (%)'] > 0]['Retorno (%)'] if not trades_df.empty else pd.Series()
losses = trades_df[trades_df['Retorno (%)'] <= 0]['Retorno (%)'] if not trades_df.empty else pd.Series()
total_trades = len(trades_df)
win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
avg_win = wins.mean() if len(wins) > 0 else 0
avg_loss = losses.mean() if len(losses) > 0 else 0
largest_win = wins.max() if len(wins) > 0 else 0
largest_loss = losses.min() if len(losses) > 0 else 0
profit_factor = (wins.sum() / abs(losses.sum())) if not losses.empty and losses.sum() != 0 else (np.inf if not wins.empty and wins.sum() > 0 else 0)
avg_duration = trades_df['Duración (días)'].mean() if total_trades > 0 else 0
time_in_market = (df['In_Market'].sum() / len(df)) * 100
expectancy = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss)

# 2. MÉTRICAS DE RENDIMIENTO Y RIESGO
total_return = (equity.iloc[-1] / 10000 - 1) * 100
bench_total_return = (benchmark.iloc[-1] / 10000 - 1) * 100
years = (df.index[-1] - df.index[0]).days / 365.25
cagr_strat = ((equity.iloc[-1] / 10000) ** (1 / years) - 1) * 100 if years > 0 else 0
cagr_bench = ((benchmark.iloc[-1] / 10000) ** (1 / years) - 1) * 100 if years > 0 else 0

vol_strat = strat_ret.std() * np.sqrt(252) * 100
vol_bench = bench_ret.std() * np.sqrt(252) * 100

dd_series = (equity / equity.cummax() - 1) * 100
max_dd = dd_series.min()
is_dd = dd_series < 0
dd_groups = (is_dd != is_dd.shift()).cumsum()
dd_duration = dd_series[is_dd].groupby(dd_groups[is_dd]).count().max() if is_dd.any() else 0

ulcer_index = np.sqrt(np.mean(dd_series**2))
var_95 = np.percentile(strat_ret, 5) * 100
cvar_95 = strat_ret[strat_ret <= np.percentile(strat_ret, 5)].mean() * 100 if len(strat_ret[strat_ret <= np.percentile(strat_ret, 5)]) > 0 else 0

best_day = strat_ret.max() * 100
worst_day = strat_ret.min() * 100
monthly_ret = strat_ret.resample(pd.offsets.MonthEnd()).apply(lambda x: (1+x).prod()-1)
best_month = monthly_ret.max() * 100
worst_month = monthly_ret.min() * 100

# 3. MÉTRICAS AJUSTADAS AL RIESGO
excess_ret = strat_ret - rf_daily
sharpe = (np.sqrt(252) * excess_ret.mean() / excess_ret.std()) if excess_ret.std() != 0 else 0
downside_ret = excess_ret[excess_ret < 0]
sortino = (np.sqrt(252) * excess_ret.mean() / downside_ret.std()) if len(downside_ret) > 0 and downside_ret.std() != 0 else 0
calmar = cagr_strat / abs(max_dd) if max_dd != 0 else 0
omega = (excess_ret[excess_ret > 0].sum() / abs(excess_ret[excess_ret < 0].sum())) if excess_ret[excess_ret < 0].sum() != 0 else np.inf

# 4. COMPARATIVA CON BENCHMARK
cov_matrix = np.cov(strat_ret, bench_ret)
beta = cov_matrix[0, 1] / cov_matrix[1, 1] if cov_matrix[1, 1] != 0 else 0
alpha = (strat_ret.mean() - (rf_daily + beta * (bench_ret.mean() - rf_daily))) * 252 * 100
r_squared = (np.corrcoef(strat_ret, bench_ret)[0, 1])**2
tracking_error = (strat_ret - bench_ret).std() * np.sqrt(252) * 100
info_ratio = ((strat_ret - bench_ret).mean() * 252) / ((strat_ret - bench_ret).std() * np.sqrt(252)) if (strat_ret - bench_ret).std() != 0 else 0

# 5. DISTRIBUCIÓN
skewness = strat_ret.skew()
kurtosis = strat_ret.kurtosis()

# ==============================================================================
# INTERFAZ DEL REPORTE PROFESIONAL (TABS)
# ==============================================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Resumen Ejecutivo", "📑 Informe Cuantitativo", "📅 Rendimientos Temporales", "📉 Análisis de Drawdown", "📋 Listado de Operaciones"])

with tab1:
    st.subheader("Métricas Clave de Rendimiento y Riesgo")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Capital Final", f"${equity.iloc[-1]:,.0f}", f"{total_return:.2f}%")
    c2.metric("CAGR (Estrategia)", f"{cagr_strat:.2f}%", f"{cagr_strat - cagr_bench:.2f}% vs SPY")
    c3.metric("Max Drawdown", f"{max_dd:.2f}%", delta_color="inverse")
    c4.metric("Sharpe Ratio", f"{sharpe:.2f}")
    
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Sortino Ratio", f"{sortino:.2f}")
    c6.metric("Calmar Ratio", f"{calmar:.2f}")
    c7.metric("Win Rate", f"{win_rate:.1f}%")
    c8.metric("Profit Factor", f"{profit_factor:.2f}" if profit_factor != np.inf else "∞")

with tab2:
    st.subheader("Informe Detallado de Métricas (Estilo Institucional)")
    
    df_perf = pd.DataFrame({
        "Métrica": ["Retorno Total", "CAGR (Anualizado)", "Volatilidad Anual", "Mejor Día", "Peor Día", "Mejor Mes", "Peor Mes"],
        "Estrategia": [f"{total_return:.2f}%", f"{cagr_strat:.2f}%", f"{vol_strat:.2f}%", f"{best_day:.2f}%", f"{worst_day:.2f}%", f"{best_month:.2f}%", f"{worst_month:.2f}%"],
        "Benchmark (SPY)": [f"{bench_total_return:.2f}%", f"{cagr_bench:.2f}%", f"{vol_bench:.2f}%", "-", "-", "-", "-"]
    })
    
    df_risk = pd.DataFrame({
        "Métrica": ["Max Drawdown", "Duración Max DD (días)", "Ulcer Index", "VaR (95%)", "CVaR / Expected Shortfall (95%)", "Downside Deviation"],
        "Valor": [f"{max_dd:.2f}%", f"{dd_duration}", f"{ulcer_index:.2f}", f"{var_95:.2f}%", f"{cvar_95:.2f}%", f"{downside_ret.std() * np.sqrt(252) * 100:.2f}%"]
    })
    
    df_risk_adj = pd.DataFrame({
        "Métrica": ["Sharpe Ratio", "Sortino Ratio", "Calmar Ratio", "Omega Ratio", "Information Ratio", "Treynor Ratio"],
        "Valor": [f"{sharpe:.2f}", f"{sortino:.2f}", f"{calmar:.2f}", f"{omega:.2f}" if omega != np.inf else "∞", f"{info_ratio:.2f}", f"{(strat_ret.mean()*252 - rf_daily*252)/beta:.2f}" if beta != 0 else "N/A"]
    })
    
    df_comp = pd.DataFrame({
        "Métrica": ["Alpha (Anualizado)", "Beta", "R-Cuadrado (R²)", "Tracking Error"],
        "Valor": [f"{alpha:.2f}%", f"{beta:.2f}", f"{r_squared:.2f}", f"{tracking_error:.2f}%"]
    })
    
    df_trades = pd.DataFrame({
        "Métrica": ["Total Operaciones", "Win Rate (%)", "Profit Factor", "Tiempo en Mercado (%)", "Duración Media (días)", "Ganancia Media Trade (%)", "Pérdida Media Trade (%)", "Mayor Ganancia (%)", "Mayor Pérdida (%)", "Expectativa Matemática (%)"],
        "Valor": [f"{total_trades}", f"{win_rate:.1f}%", f"{profit_factor:.2f}" if profit_factor != np.inf else "∞", f"{time_in_market:.1f}%", f"{avg_duration:.1f}", f"{avg_win:.2f}%", f"{avg_loss:.2f}%", f"{largest_win:.2f}%", f"{largest_loss:.2f}%", f"{expectancy:.2f}%"]
    })
    
    df_dist = pd.DataFrame({
        "Métrica": ["Skewness (Asimetría)", "Kurtosis (Curtosis)"],
        "Valor": [f"{skewness:.3f}", f"{kurtosis:.3f}"]
    })

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🟢 Rendimiento")
        st.dataframe(df_perf, hide_index=True, use_container_width=True, height=280)
        st.markdown("#### 🟡 Riesgo Ajustado")
        st.dataframe(df_risk_adj, hide_index=True, use_container_width=True, height=250)
        st.markdown("#### 🔵 Comparativa vs SPY")
        st.dataframe(df_comp, hide_index=True, use_container_width=True, height=180)
    with col2:
        st.markdown("#### 🔴 Riesgo")
        st.dataframe(df_risk, hide_index=True, use_container_width=True, height=280)
        st.markdown("#### 🟣 Estadísticas de Operaciones")
        st.dataframe(df_trades, hide_index=True, use_container_width=True, height=400)
        st.markdown("#### ⚪ Distribución")
        st.dataframe(df_dist, hide_index=True, use_container_width=True, height=110)

with tab3:
    st.subheader("Rendimientos Anuales y Mensuales")
    
    yearly_ret = strat_ret.resample(pd.offsets.YearEnd()).apply(lambda x: (1+x).prod()-1) * 100
    bench_yearly = bench_ret.resample(pd.offsets.YearEnd()).apply(lambda x: (1+x).prod()-1) * 100
    df_yearly = pd.DataFrame({
        'Año': yearly_ret.index.year.astype(str),
        'Estrategia (%)': yearly_ret.values.round(2),
        'SPY Buy&Hold (%)': bench_yearly.values.round(2),
        'Exceso (%)': (yearly_ret.values - bench_yearly.values).round(2)
    })
    st.markdown("#### 📊 Rendimiento Anual Comparativo")
    st.dataframe(df_yearly, hide_index=True, use_container_width=True, height=400)
    
    st.markdown("#### 📅 Matriz de Rendimientos Mensuales (%)")
    df['Year'] = df.index.year
    df['Month'] = df.index.month
    monthly_pivot = df.groupby(['Year', 'Month'])['Strategy_Return'].apply(lambda x: (1+x).prod()-1).unstack() * 100
    month_names = {
        1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun',
        7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic',
    }
    monthly_pivot.columns = [month_names[int(c)] for c in monthly_pivot.columns]
    monthly_pivot.index = monthly_pivot.index.astype(str)
    monthly_pivot.index.name = 'Año'
    st.dataframe(monthly_pivot.round(2).fillna('-'), use_container_width=True, height=400)

with tab4:
    st.subheader("Evolución del Drawdown")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=dd_series, fill='tozeroy', name='Drawdown (%)', line=dict(color='#EF5350', width=1), fillcolor='rgba(239, 83, 80, 0.2)'))
    fig_dd.update_layout(template='plotly_dark', height=400, title="Perfil de Drawdown de la Estrategia", yaxis_title="Drawdown (%)", plot_bgcolor='#0E1117', paper_bgcolor='#0E1117')
    fig_dd.update_xaxes(showgrid=True, gridcolor='#333333')
    fig_dd.update_yaxes(showgrid=True, gridcolor='#333333')
    st.plotly_chart(fig_dd, use_container_width=True)
    
    st.markdown(f"""
    **Análisis del Drawdown:**
    * **Caída Máxima:** {max_dd:.2f}%
    * **Días en Drawdown Máximo:** {dd_duration} días hábiles.
    * **Ulcer Index:** {ulcer_index:.2f} *(Mide la profundidad y duración de los drawdowns; cuanto más bajo, mejor para la "salud mental" del inversor).*
    """)

# --- NUEVA PESTAÑA: LISTADO DE OPERACIONES CON DESCARGA ---
with tab5:
    st.subheader("📋 Detalle de Todas las Operaciones")
    st.markdown("Listado cronológico de todas las operaciones ejecutadas por la estrategia. Los precios corresponden al **Open del día de ejecución** (día siguiente a la señal).")
    
    if not trades_df.empty:
        # Formatear fechas para mostrar
        trades_display = trades_df.copy()
        trades_display['Fecha Entrada'] = trades_display['Fecha Entrada'].dt.strftime('%Y-%m-%d')
        trades_display['Fecha Salida'] = trades_display['Fecha Salida'].dt.strftime('%Y-%m-%d')
        trades_display['Precio Entrada'] = trades_display['Precio Entrada'].round(2)
        trades_display['Precio Salida'] = trades_display['Precio Salida'].round(2)
        trades_display['Retorno (%)'] = trades_display['Retorno (%)'].round(2)
        
        st.dataframe(
            trades_display,
            hide_index=True,
            use_container_width=True,
            height=500,
            column_config={
                "Fecha Entrada": st.column_config.TextColumn("Fecha Entrada", width="small"),
                "Precio Entrada": st.column_config.NumberColumn("Precio Entrada", format="$%.2f"),
                "Fecha Salida": st.column_config.TextColumn("Fecha Salida", width="small"),
                "Precio Salida": st.column_config.NumberColumn("Precio Salida", format="$%.2f"),
                "Retorno (%)": st.column_config.NumberColumn("Retorno (%)", format="%.2f"),
                "Duración (días)": st.column_config.NumberColumn("Duración (días)", width="small"),
                "Resultado": st.column_config.TextColumn("Resultado", width="small")
            }
        )
        
        # Botón de descarga CSV
        csv_buffer = io.StringIO()
        trades_df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue()
        
        st.download_button(
            label="📥 Descargar Operaciones (CSV)",
            data=csv_data,
            file_name=f"trades_spy_fear_strategy_{period}_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
        
        # Resumen rápido de la tabla
        st.markdown("---")
        summary_col1, summary_col2, summary_col3 = st.columns(3)
        with summary_col1:
            st.metric("Total Operaciones", f"{len(trades_df)}")
        with summary_col2:
            st.metric("Operaciones Ganadoras", f"{len(trades_df[trades_df['Resultado'] == 'Ganancia'])}")
        with summary_col3:
            st.metric("Operaciones Perdedoras", f"{len(trades_df[trades_df['Resultado'] == 'Pérdida'])}")
    else:
        st.warning("No se han generado operaciones en el periodo seleccionado.")

st.info(f"📅 **Periodo analizado:** {df.index[0].strftime('%Y-%m-%d')} a {df.index[-1].strftime('%Y-%m-%d')} | Tasa Libre de Riesgo asumida: 4% anual | Comisión: 0% (Teórica)")