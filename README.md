# Trading The Fear Index — SPY / VIX

Aplicación Streamlit para replicar y analizar la estrategia **Trading The Fear Index**
de Markos Katsanos: salir del S&P 500 (SPY) cuando el VIX entra en pánico y
volver a entrar cuando el miedo se agota.

## Estrategia

**Salida del SPY (pánico):**

- `VIXUP > 50 %`: el VIX sube más del 50 % en 6 sesiones.
- `RC > 0,8`: tendencia de correlación del VIX acelerada.
- Estocástico del VIX (10 y 25 días) por encima del estocástico del SPY.

**Reentrada al SPY:**

- `STSPYS > STVIXS`: el estocástico rápido del SPY supera al del VIX.
- O el estocástico del VIX pierde impulso respecto al día anterior.

Las señales se ejecutan a la **apertura del día siguiente** para evitar
look-ahead bias.

## Funcionalidad

- Selector de periodo: máximo, 10, 5 o 3 años.
- Indicadores configurables bajo el gráfico de velas: VIXUP/VIXDN, RC,
  estocásticos rápido y lento.
- 5 pestañas: resumen ejecutivo, informe cuantitativo, rendimientos temporales,
  drawdown y listado de operaciones.
- Métricas de riesgo y retorno, comparación con SPY Buy & Hold, matriz mensual.
- Descarga de todas las operaciones en CSV.

## Datos

- SPY y `^VIX` desde Yahoo Finance (yfinance), desde 1990.
- No requiere API keys ni secrets.
- Caché de 1 hora.

## Ejecutar en local

```powershell
cd C:\Users\koldo\PROYECTO-OPENCODE\TRADINGTHEFEAR
pip install -r requirements.txt
streamlit run app.py
```

También puedes usar `run.bat`.

## Desplegar en Streamlit Community Cloud

1. Sube a un repositorio público de GitHub el contenido de esta carpeta
   (no la carpeta como subcarpeta): `app.py`, `requirements.txt`, `README.md`,
   `.streamlit/config.toml`, `.gitignore` y, opcionalmente, `run.bat`.
2. Entra en <https://share.streamlit.io> y elige **Create app**.
3. Repositorio: el que acabas de crear. Rama: `main`.
4. Main file path: `app.py`.
5. Advanced settings: Python **3.12** (o 3.11).
6. Deploy. La primera carga descarga SPY y VIX de Yahoo Finance.

## Estructura

```text
TRADINGTHEFEAR/
├── app.py
├── requirements.txt
├── README.md
├── run.bat
├── .gitignore
└── .streamlit/
    └── config.toml
```

## Aviso

Herramienta educativa. No constituye asesoramiento financiero. Los resultados
usan comisión 0 % y una tasa libre de riesgo del 4 % anual; verifica las
hipótesis antes de operar en real.
