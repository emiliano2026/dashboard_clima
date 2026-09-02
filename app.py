import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import gdown
import os
import numpy as np
import re

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Dashboard Clima IIPAC", layout="wide")

try:
    st.sidebar.image("LogoIIPAC.jpg", use_container_width=True)
except:
    st.sidebar.warning("Logo no encontrado. Sube 'LogoIIPAC.jpg'.")

st.title("📊 Dashboard Datos Clima IIPAC")
st.caption("Fuente: Servicio Meteorológico Nacional (SMN), serie 1991-2020.")

# --- FUNCIONES AUXILIARES ---
def normalizar_nombre(nombre):
    nombre = nombre.strip()
    nombre = re.sub(r'[áÁ]', 'a', nombre)
    nombre = re.sub(r'[éÉ]', 'e', nombre)
    nombre = re.sub(r'[íÍ]', 'i', nombre)
    nombre = re.sub(r'[óÓ]', 'o', nombre)
    nombre = re.sub(r'[úÚ]', 'u', nombre)
    nombre = re.sub(r'[ñÑ]', 'n', nombre)
    return re.sub(r'[^a-z0-9]', '', nombre.lower())

def buscar_columna(df, patrones):
    columnas_norm = {normalizar_nombre(col): col for col in df.columns}
    for patron in patrones:
        patron_norm = normalizar_nombre(patron)
        for col_norm, col_real in columnas_norm.items():
            if patron_norm in col_norm or col_norm in patron_norm:
                return col_real
    return None

def convertir_numerico(series):
    """Convierte una serie a numérico, manejando comas como decimales y múltiples dtypes."""
    if series is None:
        return series
    
    # Si la serie ya es puramente numérica, convertir directamente
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors='coerce')
    
    # Convertir a texto para reemplazar comas, espacios y valores sin dato del SMN
    s_str = series.astype(str).str.strip()
    s_str = s_str.str.replace(',', '.', regex=False)
    s_str = s_str.str.replace('S/D', '', regex=False).str.replace('S/P', '', regex=False)
    s_str = s_str.str.strip()
    s_str = s_str.replace(['', 'nan', 'None', 'NaN', 'null'], np.nan)
    
    return pd.to_numeric(s_str, errors='coerce')

def convertir_todas_numericas(df, columnas):
    """Aplica convertir_numerico a una lista de columnas."""
    for col in columnas:
        if col in df.columns:
            df[col] = convertir_numerico(df[col])
    return df

# --- 1. CARGA DE DATOS ---
@st.cache_data
def load_data():
    file_id = "1-XZ-eYH7iyxJpaWerNaBERy_joHr4lLJ"
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    output = "datos_clima_smn.csv"
    
    if not os.path.exists(output):
        with st.spinner("Descargando datos desde Google Drive..."):
            gdown.download(url, output, quiet=False)
    
    with open(output, 'r', encoding='utf-8') as f:
        first_line = f.readline()
        sep = '|' if '|' in first_line else (';' if ';' in first_line else ',')
    
    # Leer como texto para manejar decimales
    df_raw = pd.read_csv(output, delimiter=sep, skipinitialspace=True, 
                         encoding='utf-8', dtype=str, keep_default_na=False)
    df_raw.columns = df_raw.columns.str.strip()
    
    # --- MAPEO DE COLUMNAS ---
    mapeo = {
        'provincia': ['provincia'],
        'estacion': ['estación', 'estacion'],
        'latitud': ['latitud', 'lat'],
        'longitud': ['longitud', 'lon', 'long'],
        'altura': ['altura campo obs.', 'altura', 'alt'],
        'periodo': ['período', 'periodo'],
        'variable': ['variable'],
        'estadistico': ['estadístico', 'estadistico']
    }
    
    col_names = {}
    for key, patrones in mapeo.items():
        encontrada = buscar_columna(df_raw, patrones)
        if encontrada:
            col_names[key] = encontrada
        else:
            st.error(f"❌ No se encontró la columna para '{key}'. Columnas disponibles: {list(df_raw.columns)}")
            st.stop()
    
    # --- MESES Y PERÍODOS ---
    meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    meses_encontrados = [m for m in meses if m in df_raw.columns]
    if 'Anual' not in df_raw.columns:
        df_raw['Anual'] = ''
    periodos = meses_encontrados + ['Anual']
    
    # --- ID_VARS ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- CONVERTIR TODAS LAS COLUMNAS NUMÉRICAS (meses y Anual) ---
    columnas_a_convertir = [col for col in df_raw.columns if col in meses or col == 'Anual']
    df_raw = convertir_todas_numericas(df_raw, columnas_a_convertir)
    
    # --- DETECTAR VARIABLE DE VIENTO ---
    pattern_viento = re.compile(r'frecuencia.*velocidad', re.IGNORECASE)
    mask_viento = df_raw[col_names['variable']].str.contains(pattern_viento, na=False)
    if not mask_viento.any():
        pattern_viento2 = re.compile(r'frecuencia.*‰', re.IGNORECASE)
        mask_viento = df_raw[col_names['variable']].str.contains(pattern_viento2, na=False)
    
    df_viento_raw = df_raw[mask_viento].copy()
    df_no_viento = df_raw[~mask_viento].copy()
    
    # --- DATOS DE VIENTO ---
    wind_cols = [col for col in df_viento_raw.columns if col not in id_vars]
    df_wind = df_viento_raw[id_vars + wind_cols].copy()
    df_wind = convertir_todas_numericas(df_wind, wind_cols)
    for col in ['estacion', 'variable', 'estadistico']:
        nombre_real = col_names[col]
        df_wind[nombre_real] = df_wind[nombre_real].str.strip()
    
    # --- DATOS MENSUALES (formato largo) ---
    df_long = pd.melt(
        df_no_viento,
        id_vars=id_vars,
        value_vars=meses_encontrados,
        var_name='Mes',
        value_name='Valor'
    )
    df_long['Valor'] = convertir_numerico(df_long['Valor'])
    
    mes_map = {m: i+1 for i, m in enumerate(meses)}
    df_long['Mes_num'] = df_long['Mes'].map(mes_map)
    
    for col in ['estacion', 'variable', 'estadistico']:
        nombre_real = col_names[col]
        df_long[nombre_real] = df_long[nombre_real].str.strip()
    
    variable_viento_encontrada = None
    if not df_viento_raw.empty:
        variable_viento_encontrada = df_viento_raw[col_names['variable']].iloc[0]
    
    return df_long, df_wind, wind_cols, col_names, meses, periodos, variable_viento_encontrada

# --- CARGAR DATOS ---
df_long, df_wind, wind_cols, col_names, meses, periodos, variable_viento = load_data()
if df_long.empty:
    st.stop()

# --- 2. FILTROS ---
st.sidebar.header("🔍 Filtros")

col_estacion = col_names['estacion']
col_variable = col_names['variable']
col_estadistico = col_names['estadistico']

estaciones = sorted(df_long[col_estacion].unique())
estacion_seleccionada = st.sidebar.selectbox("📍 Estación", estaciones)

df_estacion = df_long[df_long[col_estacion] == estacion_seleccionada]
df_valid = df_estacion.dropna(subset=['Valor'])

if df_valid.empty:
    st.warning(f"⚠️ No hay datos para la estación **{estacion_seleccionada}**. Elige otra.")
    st.stop()

# --- VARIABLE (excluyendo viento) ---
variables_todas = sorted(df_valid[col_variable].unique())
variables = [v for v in variables_todas if v != variable_viento]
if not variables:
    st.warning("No hay variables disponibles.")
    st.stop()

variable_seleccionada = st.sidebar.selectbox("📊 Variable", variables)

# --- ESTADÍSTICOS (excluyendo "Número de años considerados") ---
df_var = df_valid[df_valid[col_variable] == variable_seleccionada]
todos_los_estadisticos = sorted(df_var[col_estadistico].unique())

ESTADISTICO_A_EXCLUIR = "Número de años considerados"
estadisticos = [e for e in todos_los_estadisticos if e != ESTADISTICO_A_EXCLUIR]

if not estadisticos:
    st.warning("No hay estadísticos disponibles (todos fueron excluidos).")
    st.stop()

estadistico_seleccionado = st.sidebar.selectbox("📈 Estadístico", estadisticos)

# --- SUPERPOSICIÓN ---
superponer = st.sidebar.checkbox("🔄 Superponer estadísticos")
estadisticos_a_superponer = []
if superponer:
    estadisticos_a_superponer = st.sidebar.multiselect(
        "Selecciona los estadísticos a superponer (máximo 3)",
        estadisticos,
        default=estadisticos[:2] if len(estadisticos) >= 2 else estadisticos
    )

# --- 3. UBICACIÓN ---
df_ubicacion = df_long[df_long[col_estacion] == estacion_seleccionada]
if not df_ubicacion.empty:
    lat = df_ubicacion[col_names['latitud']].iloc[0]
    lon = df_ubicacion[col_names['longitud']].iloc[0]
    altura_raw = str(df_ubicacion[col_names['altura']].iloc[0])
    altura_num = re.search(r'[\d.]+', altura_raw)
    altura = altura_num.group(0) if altura_num else altura_raw
    periodo = df_ubicacion[col_names['periodo']].iloc[0]
else:
    lat = lon = altura = periodo = None

# --- 4. GRÁFICO PRINCIPAL ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader(f"📈 Variación Mensual de {variable_seleccionada}")
    
    if superponer and len(estadisticos_a_superponer) > 1:
        fig = go.Figure()
        for est in estadisticos_a_superponer:
            df_temp = df_var[df_var[col_estadistico] == est].sort_values('Mes_num')
            df_temp = df_temp.groupby('Mes_num', as_index=False)['Valor'].mean()
            
            df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
            df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
            df_completo = df_completo.merge(df_temp[['Mes_num', 'Valor']], on='Mes_num', how='left')
            df_completo['Valor'] = convertir_numerico(df_completo['Valor'])
            
            fig.add_trace(go.Scatter(
                x=df_completo['Mes'],
                y=df_completo['Valor'],
                mode='lines+markers',
                name=est,
                line=dict(width=2),
                connectgaps=True
            ))
        fig.update_layout(
            title=f"{variable_seleccionada} - Comparativa de estadísticos",
            xaxis_title="Mes",
            yaxis_title="Valor",
            template='plotly_white',
            legend_title="Estadístico"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    else:
        df_final = df_var[df_var[col_estadistico] == estadistico_seleccionado].sort_values('Mes_num')
        df_final = df_final.groupby('Mes_num', as_index=False)['Valor'].mean()
        
        df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
        df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
        df_completo = df_completo.merge(df_final[['Mes_num', 'Valor']], on='Mes_num', how='left')
        df_completo['Valor'] = convertir_numerico(df_completo['Valor'])
        
        fig_line = px.line(
            df_completo,
            x='Mes',
            y='Valor',
            markers=True,
            title=f"{variable_seleccionada} - {estadistico_seleccionado}",
            labels={'Mes': 'Mes', 'Valor': 'Valor'},
            template='plotly_white',
        )
        fig_line.update_traces(connectgaps=True)
        
        valores_validos = df_completo['Valor'].dropna()
        if len(valores_validos) > 1:
            media = valores_validos.mean()
            fig_line.add_hline(
                y=media,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Media Anual: {media:.2f}",
                annotation_position="bottom right",
            )
        st.plotly_chart(fig_line, use_container_width=True)

with col2:
    st.subheader(f"📍 {estacion_seleccionada}")
    if lat and lon:
        st.write(f"Altura: {altura} msnm")
        st.write(f"Período: {periodo}")
        m = folium.Map(location=[float(lat), float(lon)], zoom_start=10)
        folium.Marker(
            [float(lat), float(lon)],
            popup=f"{estacion_seleccionada}<br>Altura: {altura} msnm",
            icon=folium.Icon(color="red", icon="cloud"),
        ).add_to(m)
        st_folium(m, width=400, height=300)
    else:
        st.warning("Datos de ubicación no disponibles.")

# --- 5. ROSA DE VIENTOS ---
st.subheader("🌬️ Rosa de los Vientos")

if variable_viento and not df_wind.empty:
    df_wind_estacion = df_wind[df_wind[col_estacion] == estacion_seleccionada]
    if not df_wind_estacion.empty:
        periodos_disponibles = [p for p in periodos if p in df_wind_estacion.columns]
        if periodos_disponibles:
            orden = {m: i for i, m in enumerate(meses)}
            orden['Anual'] = 12
            periodos_disponibles.sort(key=lambda x: orden.get(x, 99))
            periodo_viento = st.selectbox(
                "Selecciona el período para la rosa de vientos",
                periodos_disponibles,
                key="periodo_viento"
            )
        else:
            st.info("ℹ️ No hay períodos disponibles.")
            periodo_viento = None
    else:
        st.info(f"ℹ️ No hay datos de viento para {estacion_seleccionada}.")
        periodo_viento = None
else:
    st.info("ℹ️ La variable de viento no está disponible.")
    periodo_viento = None

col_wind, col_otros = st.columns([2, 1])

with col_wind:
    if variable_viento and periodo_viento and not df_wind_estacion.empty:
        direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        frecuencias = []
        velocidades = []
        
        for dir in direcciones:
            freq_row = df_wind_estacion[df_wind_estacion[col_estadistico] == f'Frecuencia {dir}']
            vel_row = df_wind_estacion[df_wind_estacion[col_estadistico] == f'Velocidad promedio {dir}']
            if not freq_row.empty and not vel_row.empty:
                freq_val = freq_row[periodo_viento].iloc[0]
                vel_val = vel_row[periodo_viento].iloc[0]
                frecuencias.append(freq_val if pd.notna(freq_val) else 0)
                velocidades.append(vel_val if pd.notna(vel_val) else 0)
            else:
                frecuencias.append(0)
                velocidades.append(0)
        
        calma_row = df_wind_estacion[df_wind_estacion[col_estadistico] == 'Frecuencia CALMA']
        calma_val = calma_row[periodo_viento].iloc[0] if not calma_row.empty else 0
        
        if any(f > 0 for f in frecuencias):
            df_wind_plot = pd.DataFrame({
                'Dirección': direcciones,
                'Frecuencia (‰)': frecuencias,
                'Velocidad (km/h)': velocidades
            })
            
            fig_wind = px.bar_polar(
                df_wind_plot,
                r='Frecuencia (‰)',
                theta='Dirección',
                color='Velocidad (km/h)',
                color_continuous_scale=px.colors.sequential.Plasma,
                template='plotly_white',
                title=f"Rosa de Vientos - {estacion_seleccionada} ({periodo_viento})",
                hover_data={'Velocidad (km/h)': True},
                barmode='relative'
            )
            fig_wind.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, tickfont=dict(size=12), gridcolor='lightgray'),
                    angularaxis=dict(direction="clockwise", period=8, tickfont=dict(size=14))
                ),
                height=500,
                width=500,
                margin=dict(l=80, r=80, t=80, b=80)
            )
            st.plotly_chart(fig_wind, use_container_width=True)
            
            if pd.notna(calma_val) and calma_val > 0:
                st.metric("Frecuencia CALMA (‰)", f"{calma_val:.1f}")
        else:
            st.info("ℹ️ No hay datos de viento válidos para este período.")
    else:
        if not variable_viento:
            st.info("ℹ️ La variable de viento no está disponible.")
        elif not periodo_viento:
            st.info("ℹ️ Selecciona un período para ver la rosa de vientos.")

# --- 6. OTROS DATOS (excluyendo "Número de años considerados") ---
with col_otros:
    st.subheader("📊 Otros Datos")
    
    estadisticos_puntuales = []
    for est in estadisticos:
        if est == ESTADISTICO_A_EXCLUIR:
            continue
        if 'promedio' in est.lower() and 'máximo' not in est.lower() and 'mínimo' not in est.lower():
            continue
        if est in ['Promedio', 'Máximo valor promedio', 'Mínimo valor promedio']:
            continue
        estadisticos_puntuales.append(est)
    
    kpi_data = {}
    for est in estadisticos_puntuales:
        df_kpi = df_var[df_var[col_estadistico] == est]
        if not df_kpi.empty:
            valores = convertir_numerico(df_kpi['Valor']).dropna()
            if not valores.empty:
                kpi_data[est] = valores.iloc[0]
    
    if kpi_data:
        for nombre, valor in kpi_data.items():
            if pd.notna(valor):
                display = nombre.replace('valor', '').strip()
                if display == '':
                    display = nombre
                st.metric(label=display, value=f"{valor:.2f}" if isinstance(valor, (int, float, np.floating, np.integer)) else str(valor))
    else:
        st.info("No hay datos puntuales adicionales para esta variable.")

# --- 7. TABLA DE DATOS ---
with st.expander("📋 Ver todos los datos de la variable seleccionada"):
    if 'df_completo' in locals():
        st.dataframe(df_completo)
    else:
        st.dataframe(df_final[['Mes', 'Valor']] if not df_final.empty else pd.DataFrame())

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def generar_grafico_givoni(df):
  """Genera el Diagrama Bioclimático de Givoni con Plotly.

  df debe contener: 'temperatura', 'humedad_relativa', y 'fecha' (datetime)
  """
  fig = go.Figure()

  # -------------------------------------------------------------------
  # 1. DELIMITACIÓN DE ZONAS BIOCLIMÁTICAS DE GIVONI (Superficies)
  # -------------------------------------------------------------------

  # Zona 1: Confort Directo
  fig.add_trace(
      go.Scatter(
          x=[20, 26, 26, 20, 20],
          y=[20, 20, 80, 80, 20],
          fill="toself",
          fillcolor="rgba(46, 204, 113, 0.35)",
          line=dict(color="#2ecc71", width=1.5),
          name="1. Confort Térmico",
          hoverinfo="name",
      )
  )

  # Zona 2: Ventilación Natural
  fig.add_trace(
      go.Scatter(
          x=[20, 32, 32, 26, 20],
          y=[20, 20, 85, 85, 20],
          fill="toself",
          fillcolor="rgba(52, 152, 219, 0.25)",
          line=dict(color="#3498db", width=1.5, dash="dot"),
          name="2. Ventilación Natural",
          hoverinfo="name",
      )
  )

  # Zona 3: Masa Térmica (Alta inercia)
  fig.add_trace(
      go.Scatter(
          x=[20, 35, 35, 20, 20],
          y=[20, 20, 50, 50, 20],
          fill="toself",
          fillcolor="rgba(230, 126, 34, 0.2)",
          line=dict(color="#e67e22", width=1.5, dash="dot"),
          name="3. Masa Térmica",
          hoverinfo="name",
      )
  )

  # Zona 4: Enfriamiento Evaporativo
  fig.add_trace(
      go.Scatter(
          x=[20, 40, 40, 20, 20],
          y=[10, 10, 45, 45, 10],
          fill="toself",
          fillcolor="rgba(155, 89, 182, 0.2)",
          line=dict(color="#9b59b6", width=1.5, dash="dot"),
          name="4. Enfriamiento Evaporativo",
          hoverinfo="name",
      )
  )

  # Zona 5: Calefacción Solar Pasiva
  fig.add_trace(
      go.Scatter(
          x=[10, 20, 20, 10, 10],
          y=[20, 20, 80, 80, 20],
          fill="toself",
          fillcolor="rgba(241, 196, 15, 0.25)",
          line=dict(color="#f1c40f", width=1.5, dash="dot"),
          name="5. Calefacción Solar Pasiva",
          hoverinfo="name",
      )
  )

  # -------------------------------------------------------------------
  # 2. CÁLCULO Y TRAZADO DE VECTORES MENSUALES (Variabilidad de datos)
  # -------------------------------------------------------------------
  df_temp = df.copy()
  df_temp["mes"] = df_temp["fecha"].dt.month
  df_temp["nombre_mes"] = df_temp["fecha"].dt.strftime("%B")

  # Agrupar por mes calculando promedios de Max y Min
  resumen_mensual = (
      df_temp.groupby(["mes", "nombre_mes"])
      .agg(
          t_max=("temperatura", "mean"),  # o 'max' para absolutos
          t_min=("temperatura", "mean"),  # o 'min' para absolutos
          hr_max=("humedad_relativa", "max"),
          hr_min=("humedad_relativa", "min"),
      )
      .reset_index()
  )

  # Simplificación de oscilación térmica diaria promedio por mes
  resumen_mensual["t_max_prom"] = df_temp.groupby("mes")["temperatura"].transform(
      lambda x: x[x > x.median()].mean()
  )
  resumen_mensual["t_min_prom"] = df_temp.groupby("mes")["temperatura"].transform(
      lambda x: x[x <= x.median()].mean()
  )

  # Trazar vectores por cada mes
  colores_meses = [
      "#1f77b4",
      "#aec7e8",
      "#2ca02c",
      "#98df8a",
      "#d62728",
      "#ff9896",
      "#9467bd",
      "#c5b0d5",
      "#8c564b",
      "#c49c94",
      "#e377c2",
      "#f7b6d2",
  ]

  for idx, row in resumen_mensual.iterrows():
    # Coordenadas Vector: (T_min, HR_max) -> (T_max, HR_min)
    x_vals = [row["t_min_prom"], row["t_max_prom"]]
    y_vals = [row["hr_max"], row["hr_min"]]

    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="lines+markers",
            name=f"{row['nombre_mes'].capitalize()}",
            line=dict(width=2.5, color=colores_meses[idx % len(colores_meses)]),
            marker=dict(size=7),
            text=[
                f"Noche ({row['nombre_mes']}): {x_vals[0]:.1f}°C, {y_vals[0]:.1f}% HR",
                f"Día ({row['nombre_mes']}): {x_vals[1]:.1f}°C, {y_vals[1]:.1f}% HR",
            ],
            hoverinfo="text",
        )
    )

  # -------------------------------------------------------------------
  # 3. CONFIGURACIÓN DE EJES Y ESTILO
  # -------------------------------------------------------------------
  fig.update_layout(
      title="Diagrama Bioclimático de Givoni - Vectores de Variación Mensual",
      xaxis=dict(
          title="Temperatura Seca del Aire (°C)",
          range=[0, 45],
          dtick=5,
          gridcolor="#e0e0e0",
      ),
      yaxis=dict(
          title="Humedad Relativa (%)",
          range=[0, 100],
          dtick=10,
          gridcolor="#e0e0e0",
      ),
      template="plotly_white",
      height=650,
      legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
  )

  return fig

st.subheader("Carta Bioclimática de Givoni")
fig_givoni = generar_grafico_givoni(df_filtrado)
st.plotly_chart(fig_givoni, use_container_width=True)
