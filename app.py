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
    st.sidebar.warning("Logo no encontrado.")

st.title("📊 Dashboard Datos Clima IIPAC")
st.caption("Fuente: Servicio Meteorológico Nacional (SMN), serie 1991-2020.")

# --- FUNCIONES ---
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
    if series.dtype == 'object':
        series = series.str.replace(',', '.').str.replace('S/D', '').str.replace('S/P', '').str.strip()
        series = series.replace('', np.nan)
        return pd.to_numeric(series, errors='coerce')
    return pd.to_numeric(series, errors='coerce')

# --- CARGA DE DATOS ---
@st.cache_data
def load_data():
    file_id = "1-XZ-eYH7iyxJpaWerNaBERy_joHr4lLJ"
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    output = "datos_clima_smn.csv"
    
    if not os.path.exists(output):
        with st.spinner("Descargando datos..."):
            gdown.download(url, output, quiet=False)
    
    with open(output, 'r', encoding='utf-8') as f:
        first_line = f.readline()
        sep = '|' if '|' in first_line else (';' if ';' in first_line else ',')
    
    df_raw = pd.read_csv(output, delimiter=sep, skipinitialspace=True, encoding='utf-8', dtype=str, keep_default_na=False)
    df_raw.columns = df_raw.columns.str.strip()
    
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
            st.error(f"Columna '{key}' no encontrada. Columnas: {list(df_raw.columns)}")
            st.stop()
    
    meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    meses_encontrados = [m for m in meses if m in df_raw.columns]
    
    # ID vars
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- DATOS DE VIENTO: filas donde VARIABLE contiene "Frecuencia (‰) y velocidad promedio" ---
    pattern_viento = re.compile(r'frecuencia.*velocidad', re.IGNORECASE)
    df_viento_raw = df_raw[df_raw[col_names['variable']].str.contains(pattern_viento, na=False)]
    
    # Si no se encuentra, buscar por "Frecuencia (‰)"
    if df_viento_raw.empty:
        pattern_viento = re.compile(r'frecuencia.*‰', re.IGNORECASE)
        df_viento_raw = df_raw[df_raw[col_names['variable']].str.contains(pattern_viento, na=False)]
    
    # DataFrame de viento (mantenemos formato ancho con meses)
    df_wind = df_viento_raw[id_vars + meses_encontrados].copy()
    for col in meses_encontrados:
        df_wind[col] = convertir_numerico(df_wind[col])
    
    # --- DATOS MENSUALES (excluyendo viento) ---
    df_no_viento = df_raw[~df_raw[col_names['variable']].str.contains(pattern_viento, na=False)]
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
        df_wind[nombre_real] = df_wind[nombre_real].str.strip()
    
    # Identificar variable de viento
    variable_viento = None
    if not df_wind.empty:
        variable_viento = df_wind[col_names['variable']].iloc[0]
    
    return df_long, df_wind, col_names, meses, variable_viento

df_long, df_wind, col_names, meses, variable_viento = load_data()
if df_long.empty:
    st.stop()

# --- FILTROS ---
col_estacion = col_names['estacion']
col_variable = col_names['variable']
col_estadistico = col_names['estadistico']

estaciones = sorted(df_long[col_estacion].unique())
estacion_seleccionada = st.sidebar.selectbox("📍 Estación", estaciones)

df_estacion = df_long[df_long[col_estacion] == estacion_seleccionada]
df_valid = df_estacion.dropna(subset=['Valor'])

if df_valid.empty:
    st.warning(f"No hay datos para {estacion_seleccionada}. Elige otra.")
    st.stop()

# Variables (excluyendo viento)
variables_todas = sorted(df_valid[col_variable].unique())
variables = [v for v in variables_todas if v != variable_viento]
if not variables:
    st.warning("No hay variables disponibles.")
    st.stop()

variable_seleccionada = st.sidebar.selectbox("📊 Variable", variables)

df_var = df_valid[df_valid[col_variable] == variable_seleccionada]
estadisticos = sorted(df_var[col_estadistico].unique())
estadistico_seleccionado = st.sidebar.selectbox("📈 Estadístico", estadisticos)

# Superposición
superponer = st.sidebar.checkbox("🔄 Superponer estadísticos")
estadisticos_a_superponer = []
if superponer:
    estadisticos_a_superponer = st.sidebar.multiselect(
        "Selecciona estadísticos (máx 3)",
        estadisticos,
        default=estadisticos[:2] if len(estadisticos) >= 2 else estadisticos
    )

# --- UBICACIÓN ---
df_wind_estacion = df_wind[df_wind[col_estacion] == estacion_seleccionada]
if not df_wind_estacion.empty:
    lat = df_wind_estacion[col_names['latitud']].iloc[0]
    lon = df_wind_estacion[col_names['longitud']].iloc[0]
    altura_raw = str(df_wind_estacion[col_names['altura']].iloc[0])
    altura_num = re.search(r'[\d.]+', altura_raw)
    altura = altura_num.group(0) if altura_num else altura_raw
    periodo = df_wind_estacion[col_names['periodo']].iloc[0]
else:
    lat = lon = altura = periodo = None

# --- GRÁFICO PRINCIPAL ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader(f"📈 Variación Mensual de {variable_seleccionada}")
    
    if superponer and len(estadisticos_a_superponer) > 1:
        fig = go.Figure()
        for est in estadisticos_a_superponer:
            df_temp = df_var[df_var[col_estadistico] == est].sort_values('Mes_num')
            df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
            df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
            df_completo = df_completo.merge(df_temp[['Mes_num', 'Valor']], on='Mes_num', how='left')
            fig.add_trace(go.Scatter(
                x=df_completo['Mes'],
                y=df_completo['Valor'],
                mode='lines+markers',
                name=est,
                line=dict(width=2),
                connectgaps=True
            ))
        fig.update_layout(
            title=f"{variable_seleccionada} - Comparativa",
            xaxis_title="Mes",
            yaxis_title="Valor",
            template='plotly_white',
            legend_title="Estadístico"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        df_final = df_var[df_var[col_estadistico] == estadistico_seleccionado].sort_values('Mes_num')
        df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
        df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
        df_completo = df_completo.merge(df_final[['Mes_num', 'Valor']], on='Mes_num', how='left')
        
        # Asegurar que Valor sea numérico
        df_completo['Valor'] = pd.to_numeric(df_completo['Valor'], errors='coerce')
        
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
        
        if df_completo['Valor'].notna().sum() > 1:
            media = df_completo['Valor'].mean()
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

# --- ROSA DE VIENTOS ---
st.subheader("🌬️ Rosa de los Vientos")

if variable_viento and not df_wind_estacion.empty:
    # Obtener estadísticos de viento para esta estación
    estadisticos_viento = df_wind_estacion[col_estadistico].unique()
    
    # Direcciones
    direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    freq_stats = [f'Frecuencia {d}' for d in direcciones]
    vel_stats = [f'Velocidad promedio {d}' for d in direcciones]
    calma_stat = 'Frecuencia CALMA'
    
    # Verificar si existen
    freq_exist = [s for s in freq_stats if s in estadisticos_viento]
    vel_exist = [s for s in vel_stats if s in estadisticos_viento]
    
    if freq_exist and vel_exist:
        # Opciones de período (meses)
        opciones_periodo = [m for m in meses if m in df_wind.columns]
        if 'Anual' in df_wind.columns:
            opciones_periodo.append('Anual')
        
        if opciones_periodo:
            mes_seleccionado = st.selectbox(
                "Selecciona el período para la rosa de vientos",
                opciones_periodo,
                key="mes_viento_radar"
            )
            
            frecuencias = []
            velocidades = []
            
            for dir in direcciones:
                # Frecuencia
                freq_row = df_wind_estacion[df_wind_estacion[col_estadistico] == f'Frecuencia {dir}']
                if not freq_row.empty:
                    freq_val = freq_row[mes_seleccionado].iloc[0]
                    frecuencias.append(freq_val if pd.notna(freq_val) else 0)
                else:
                    frecuencias.append(0)
                
                # Velocidad
                vel_row = df_wind_estacion[df_wind_estacion[col_estadistico] == f'Velocidad promedio {dir}']
                if not vel_row.empty:
                    vel_val = vel_row[mes_seleccionado].iloc[0]
                    velocidades.append(vel_val if pd.notna(vel_val) else 0)
                else:
                    velocidades.append(0)
            
            # CALMA
            calma_row = df_wind_estacion[df_wind_estacion[col_estadistico] == calma_stat]
            calma_val = calma_row[mes_seleccionado].iloc[0] if not calma_row.empty and calma_stat in estadisticos_viento else 0
            
            # Cerrar polígono
            direcciones_closed = direcciones + [direcciones[0]]
            frecuencias_closed = frecuencias + [frecuencias[0]]
            velocidades_closed = velocidades + [velocidades[0]]
            
            # Gráfico de radar
            fig_radar = go.Figure()
            
            fig_radar.add_trace(go.Scatterpolar(
                r=frecuencias_closed,
                theta=direcciones_closed,
                mode='lines+markers',
                name='Frecuencia (‰)',
                line=dict(color='blue', width=2),
                marker=dict(color='blue', size=6),
                fill='toself',
                fillcolor='rgba(0, 0, 255, 0.1)'
            ))
            
            fig_radar.add_trace(go.Scatterpolar(
                r=velocidades_closed,
                theta=direcciones_closed,
                mode='lines+markers',
                name='Velocidad (km/h)',
                line=dict(color='red', width=2),
                marker=dict(color='red', size=6),
                fill='toself',
                fillcolor='rgba(255, 0, 0, 0.1)'
            ))
            
            if calma_val and calma_val > 0:
                fig_radar.add_trace(go.Scatterpolar(
                    r=[calma_val],
                    theta=['N'],
                    mode='markers',
                    name=f'CALMA ({calma_val:.1f}‰)',
                    marker=dict(color='black', size=12, symbol='circle'),
                    showlegend=True
                ))
            
            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, tickfont=dict(size=10), gridcolor='lightgray'),
                    angularaxis=dict(direction='clockwise', period=8, tickfont=dict(size=12))
                ),
                title=f"Rosa de Vientos - {estacion_seleccionada} ({mes_seleccionado})",
                template='plotly_white',
                legend=dict(orientation='h', y=1.1)
            )
            
            st.plotly_chart(fig_radar, use_container_width=True)
            
            if calma_val and calma_val > 0:
                st.metric("Frecuencia CALMA (‰)", f"{calma_val:.1f}")
        else:
            st.info("ℹ️ No hay columnas de meses para la rosa de vientos.")
    else:
        st.info("ℹ️ No se encontraron estadísticos de dirección en los datos de viento.")
else:
    st.info("ℹ️ No hay datos de viento disponibles.")

# --- OTROS DATOS ---
st.subheader("📊 Otros Datos")
kpi_estadisticos = ['Número de años considerados', 'Máximo valor diario', 'Mínimo valor diario']
kpi_data = {}
for est in kpi_estadisticos:
    if est in estadisticos:
        df_kpi = df_var[df_var[col_estadistico] == est]
        if not df_kpi.empty:
            valores = df_kpi['Valor'].dropna()
            if not valores.empty:
                kpi_data[est] = valores.mean()

if kpi_data:
    cols = st.columns(len(kpi_data))
    for i, (nombre, valor) in enumerate(kpi_data.items()):
        with cols[i]:
            display = nombre.replace('valor', '').strip()
            st.metric(label=display if display else nombre, value=f"{valor:.1f}")
else:
    st.info("No hay datos adicionales.")

# --- TABLA DE DATOS ---
with st.expander("📋 Ver datos de la variable seleccionada"):
    if 'df_completo' in locals():
        st.dataframe(df_completo)
    elif 'df_final' in locals():
        st.dataframe(df_final[['Mes', 'Valor']])
