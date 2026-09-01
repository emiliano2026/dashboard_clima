import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import gdown
import os
import numpy as np

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Dashboard de Clima - SMN", layout="wide")
st.title("🌦️ Dashboard de Datos Climáticos - SMN")

# --- 1. CARGA DE DATOS DESDE GOOGLE DRIVE ---
@st.cache_data
def load_data():
    file_id = "1-XZ-eYH7iyxJpaWerNaBERy_joHr4lLJ"
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    output = "datos_clima_smn.csv"
    
    if not os.path.exists(output):
        with st.spinner("Descargando datos desde Google Drive..."):
            gdown.download(url, output, quiet=False)
    
    # Leer el CSV
    df_raw = pd.read_csv(output, delimiter='|', skipinitialspace=True)
    df_raw.columns = df_raw.columns.str.strip()
    
    # --- IDENTIFICAR COLUMNAS DE VIENTO (de forma segura) ---
    # Buscamos columnas que contengan "Frecuencia", "Velocidad promedio" o "CALMA"
    # Pero solo si existen en el DataFrame
    posibles_wind = ['Frecuencia', 'Velocidad promedio', 'CALMA']
    wind_cols = []
    for col in df_raw.columns:
        if any(key in col for key in posibles_wind):
            wind_cols.append(col)
    
    # Si no hay columnas de viento, creamos un DataFrame vacío con los metadatos
    id_vars = ['PROVINCIA', 'ESTACIÓN', 'Latitud', 'Longitud', 'Altura campo obs.', 'Período', 'VARIABLE', 'ESTADÍSTICO']
    
    if wind_cols:
        df_wind = df_raw[id_vars + wind_cols].copy()
        # Limpiar valores de viento: reemplazar 'S/D' y 'S/P' por NaN
        for col in wind_cols:
            df_wind[col] = pd.to_numeric(df_wind[col].replace(['S/D', 'S/P', ''], np.nan), errors='coerce')
    else:
        # Si no hay columnas de viento, solo guardamos los metadatos
        df_wind = df_raw[id_vars].copy()
        # Añadir columnas vacías para evitar errores posteriores
        for col in ['Frecuencia N', 'Frecuencia NE', 'Frecuencia E', 'Frecuencia SE', 
                    'Frecuencia S', 'Frecuencia SW', 'Frecuencia W', 'Frecuencia NW',
                    'Velocidad promedio N', 'Velocidad promedio NE', 'Velocidad promedio E', 
                    'Velocidad promedio SE', 'Velocidad promedio S', 'Velocidad promedio SW', 
                    'Velocidad promedio W', 'Velocidad promedio NW', 'Frecuencia CALMA']:
            df_wind[col] = np.nan
    
    # --- TRANSFORMACIÓN DE DATOS MENSUALES (formato largo) ---
    meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    
    df_long = pd.melt(
        df_raw,
        id_vars=id_vars,
        value_vars=meses,
        var_name='Mes',
        value_name='Valor'
    )
    
    # Limpiar valores mensuales
    df_long['Valor'] = pd.to_numeric(df_long['Valor'].replace(['S/D', 'S/P', ''], np.nan), errors='coerce')
    
    # Mapear meses a números
    mes_map = {'Ene': 1, 'Feb': 2, 'Mar': 3, 'Abr': 4, 'May': 5, 'Jun': 6,
               'Jul': 7, 'Ago': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dic': 12}
    df_long['Mes_num'] = df_long['Mes'].map(mes_map)
    
    # Limpiar nombres
    for col in ['ESTACIÓN', 'VARIABLE', 'ESTADÍSTICO']:
        df_long[col] = df_long[col].str.strip()
        if col in df_wind.columns:
            df_wind[col] = df_wind[col].str.strip()
    
    return df_long, df_wind, wind_cols

df_long, df_wind, wind_cols = load_data()

if df_long.empty:
    st.warning("No se pudieron cargar los datos. Verifica el archivo.")
    st.stop()

# --- 2. BARRA LATERAL: FILTROS ---
st.sidebar.header("🔍 Filtros")

# Obtener estaciones (solo aquellas que tienen al menos un dato en df_long)
estaciones_con_datos = df_long['ESTACIÓN'].unique()
estaciones = sorted(estaciones_con_datos)
estacion_seleccionada = st.sidebar.selectbox("📍 Selecciona la Estación", estaciones)

# Filtrar datos mensuales por estación
df_estacion = df_long[df_long['ESTACIÓN'] == estacion_seleccionada]

# --- Variables y estadísticos con datos válidos ---
df_valid = df_estacion.dropna(subset=['Valor'])
if df_valid.empty:
    st.warning(f"⚠️ No hay datos disponibles para la estación **{estacion_seleccionada}**. Por favor, selecciona otra.")
    st.stop()

variables_disponibles = sorted(df_valid['VARIABLE'].unique())
variable_seleccionada = st.sidebar.selectbox("📊 Selecciona la Variable", variables_disponibles)

df_var = df_valid[df_valid['VARIABLE'] == variable_seleccionada]
estadisticos_disponibles = sorted(df_var['ESTADÍSTICO'].unique())
estadistico_seleccionado = st.sidebar.selectbox("📈 Selecciona el Estadístico", estadisticos_disponibles)

# --- 3. DATOS DE UBICACIÓN Y VIENTO ---
df_wind_estacion = df_wind[df_wind['ESTACIÓN'] == estacion_seleccionada]

if not df_wind_estacion.empty:
    lat = df_wind_estacion['Latitud'].iloc[0]
    lon = df_wind_estacion['Longitud'].iloc[0]
    altura = df_wind_estacion['Altura campo obs.'].iloc[0]
    periodo = df_wind_estacion['Período'].iloc[0]
else:
    lat, lon, altura, periodo = None, None, None, None

# --- 4. VISUALIZACIÓN PRINCIPAL ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader(f"📈 Variación Mensual de {variable_seleccionada}")
    
    df_final = df_var[df_var['ESTADÍSTICO'] == estadistico_seleccionado].sort_values('Mes_num')
    
    if not df_final.empty and df_final['Valor'].notna().any():
        fig_line = px.line(
            df_final,
            x='Mes',
            y='Valor',
            markers=True,
            title=f"{variable_seleccionada} - {estadistico_seleccionado}",
            labels={'Mes': 'Mes', 'Valor': 'Valor'},
            template='plotly_white',
        )
        
        if df_final['Valor'].notna().sum() > 1:
            valor_anual = df_final['Valor'].mean()
            fig_line.add_hline(
                y=valor_anual,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Media Anual: {valor_anual:.2f}",
                annotation_position="bottom right",
            )
        
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info(f"ℹ️ No hay datos mensuales para {variable_seleccionada} - {estadistico_seleccionado} en esta estación.")

with col2:
    st.subheader("📍 Ubicación de la Estación")
    if lat and lon:
        st.write(f"**{estacion_seleccionada}**")
        st.write(f"Altura: {altura}")
        st.write(f"Período: {periodo}")
        
        m = folium.Map(location=[lat, lon], zoom_start=10)
        folium.Marker(
            [lat, lon],
            popup=f"{estacion_seleccionada}<br>Altura: {altura}",
            icon=folium.Icon(color="red", icon="cloud"),
        ).add_to(m)
        st_folium(m, width=400, height=300)
    else:
        st.warning("No se encontraron datos de ubicación para esta estación.")

# --- 5. ROSA DE LOS VIENTOS ---
st.subheader("🌬️ Rosa de los Vientos")

# Verificar si la estación tiene datos de viento (reales, no NaN)
if not df_wind_estacion.empty:
    # Extraer frecuencias y velocidades para las 8 direcciones
    direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    frecuencias = []
    velocidades = []
    
    for dir in direcciones:
        freq_col = f'Frecuencia {dir}'
        vel_col = f'Velocidad promedio {dir}'
        
        freq_val = df_wind_estacion[freq_col].iloc[0] if freq_col in df_wind_estacion.columns else np.nan
        vel_val = df_wind_estacion[vel_col].iloc[0] if vel_col in df_wind_estacion.columns else np.nan
        
        if pd.notna(freq_val) and pd.notna(vel_val):
            frecuencias.append(freq_val)
            velocidades.append(vel_val)
        else:
            frecuencias.append(0)
            velocidades.append(0)
    
    calma_col = 'Frecuencia CALMA'
    calma_val = df_wind_estacion[calma_col].iloc[0] if calma_col in df_wind_estacion.columns else np.nan
    
    # Verificar si hay algún dato de viento válido
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
            template='plotly_dark',
            title=f"Rosa de Vientos - {estacion_seleccionada}",
            hover_data={'Velocidad (km/h)': True}
        )
        
        fig_wind.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, tickfont=dict(size=10)),
                angularaxis=dict(direction="clockwise", period=8, tickfont=dict(size=12))
            )
        )
        
        st.plotly_chart(fig_wind, use_container_width=True)
        
        if pd.notna(calma_val) and calma_val > 0:
            st.metric("Frecuencia CALMA (‰)", f"{calma_val:.1f}")
    else:
        st.info("ℹ️ No hay datos de viento válidos (todas las frecuencias son cero o nulas) para esta estación.")
else:
    st.info("ℹ️ Esta estación no tiene datos de viento en el archivo.")

# --- 6. DATOS PUNTUALES (KPI's) ---
st.subheader("📊 Datos Puntuales Clave")

kpi_estadisticos = ['Número de años considerados', 'Máximo valor diario', 'Mínimo valor diario']
kpi_data = {}

for est in kpi_estadisticos:
    if est in estadisticos_disponibles:
        df_kpi = df_var[df_var['ESTADÍSTICO'] == est]
        if not df_kpi.empty:
            valores = df_kpi['Valor'].dropna()
            if not valores.empty:
                kpi_data[est] = valores.mean()

if kpi_data:
    cols = st.columns(len(kpi_data))
    for i, (nombre, valor) in enumerate(kpi_data.items()):
        with cols[i]:
            display_name = nombre.replace('valor', '').strip()
            if display_name == '':
                display_name = nombre
            st.metric(label=display_name, value=f"{valor:.1f}" if not pd.isna(valor) else "N/D")
else:
    st.info("ℹ️ No se encontraron datos puntuales adicionales para esta variable/estación.")

# --- 7. TABLA DE DATOS (opcional) ---
with st.expander("📋 Ver todos los datos de la variable seleccionada"):
    if not df_final.empty:
        st.dataframe(df_final[['Mes', 'Valor']])
    else:
        st.write("No hay datos para mostrar.")
