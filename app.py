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

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Dashboard de Clima - SMN", layout="wide")
st.title("🌦️ Dashboard de Datos Climáticos - SMN")

# --- FUNCIONES AUXILIARES PARA NORMALIZAR NOMBRES DE COLUMNAS ---
def normalizar_nombre(nombre):
    """Quita tildes, convierte a minúsculas y elimina espacios"""
    nombre = nombre.strip()
    # Reemplazar tildes
    nombre = re.sub(r'[áÁ]', 'a', nombre)
    nombre = re.sub(r'[éÉ]', 'e', nombre)
    nombre = re.sub(r'[íÍ]', 'i', nombre)
    nombre = re.sub(r'[óÓ]', 'o', nombre)
    nombre = re.sub(r'[úÚ]', 'u', nombre)
    nombre = re.sub(r'[ñÑ]', 'n', nombre)
    return nombre.lower().replace(' ', '')

def buscar_columna(df, patrones):
    """
    Busca en las columnas del DataFrame un nombre que coincida con alguno de los patrones.
    Retorna el nombre exacto de la columna o None si no se encuentra.
    """
    columnas_norm = {normalizar_nombre(col): col for col in df.columns}
    for patron in patrones:
        patron_norm = normalizar_nombre(patron)
        if patron_norm in columnas_norm:
            return columnas_norm[patron_norm]
    return None

# --- 1. CARGA DE DATOS DESDE GOOGLE DRIVE ---
@st.cache_data
def load_data():
    file_id = "1-XZ-eYH7iyxJpaWerNaBERy_joHr4lLJ"
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    output = "datos_clima_smn.csv"
    
    if not os.path.exists(output):
        with st.spinner("Descargando datos desde Google Drive..."):
            gdown.download(url, output, quiet=False)
    
    # --- DETECTAR DELIMITADOR AUTOMÁTICAMENTE ---
    # Leer solo las primeras líneas para adivinar el separador
    with open(output, 'r', encoding='utf-8') as f:
        first_line = f.readline()
        if '|' in first_line:
            sep = '|'
        elif ';' in first_line:
            sep = ';'
        else:
            sep = ','
    
    # Leer el CSV con el separador detectado
    df_raw = pd.read_csv(output, delimiter=sep, skipinitialspace=True, encoding='utf-8')
    
    # Limpiar nombres de columnas: quitar espacios al inicio/final
    df_raw.columns = df_raw.columns.str.strip()
    
    # --- IDENTIFICAR COLUMNAS CRÍTICAS POR PATRÓN ---
    # Mapeo de nombres esperados a posibles variantes
    mapeo_columnas = {
        'provincia': ['provincia'],
        'estacion': ['estación', 'estacion', 'estacion'],
        'latitud': ['latitud', 'lat'],
        'longitud': ['longitud', 'lon', 'long'],
        'altura': ['altura campo obs.', 'altura', 'alt'],
        'periodo': ['período', 'periodo'],
        'variable': ['variable'],
        'estadistico': ['estadístico', 'estadistico']
    }
    
    # Diccionario para almacenar los nombres reales encontrados
    col_names = {}
    for key, patrones in mapeo_columnas.items():
        encontrada = buscar_columna(df_raw, patrones)
        if encontrada:
            col_names[key] = encontrada
        else:
            # Si no se encuentra, lanzar error con información de columnas disponibles
            st.error(f"❌ No se pudo encontrar la columna para '{key}'. Columnas disponibles: {list(df_raw.columns)}")
            st.stop()
    
    # --- IDENTIFICAR COLUMNAS DE MESES ---
    meses_esperados = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    meses_encontrados = [m for m in meses_esperados if m in df_raw.columns]
    if len(meses_encontrados) < 12:
        st.warning(f"⚠️ No se encontraron todos los meses. Meses encontrados: {meses_encontrados}")
    
    # --- IDENTIFICAR COLUMNAS DE VIENTO ---
    # Buscar columnas que contengan 'frecuencia' o 'velocidad promedio'
    wind_cols = []
    for col in df_raw.columns:
        col_lower = col.lower()
        if 'frecuencia' in col_lower or 'velocidad promedio' in col_lower:
            wind_cols.append(col)
    
    # También buscar 'CALMA'
    calma_col = buscar_columna(df_raw, ['Frecuencia CALMA', 'CALMA'])
    if calma_col:
        wind_cols.append(calma_col)
    
    # --- CONSTRUIR LISTA DE ID_VARS (metadatos) ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- CREAR DataFrame DE VIENTO (sin transformar) ---
    df_wind = df_raw[id_vars + wind_cols].copy()
    # Reemplazar 'S/D' y 'S/P' por NaN
    for col in wind_cols:
        df_wind[col] = pd.to_numeric(df_wind[col].replace(['S/D', 'S/P', ''], np.nan), errors='coerce')
    
    # --- TRANSFORMACIÓN DE DATOS MENSUALES (formato largo) ---
    df_long = pd.melt(
        df_raw,
        id_vars=id_vars,
        value_vars=meses_encontrados,
        var_name='Mes',
        value_name='Valor'
    )
    
    # Limpiar valores mensuales
    df_long['Valor'] = pd.to_numeric(df_long['Valor'].replace(['S/D', 'S/P', ''], np.nan), errors='coerce')
    
    # Mapear meses a números para orden correcto
    mes_map = {'Ene': 1, 'Feb': 2, 'Mar': 3, 'Abr': 4, 'May': 5, 'Jun': 6,
               'Jul': 7, 'Ago': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dic': 12}
    df_long['Mes_num'] = df_long['Mes'].map(mes_map)
    
    # Limpiar nombres de las columnas de estación, variable y estadístico
    for col in ['estacion', 'variable', 'estadistico']:
        nombre_real = col_names[col]
        df_long[nombre_real] = df_long[nombre_real].str.strip()
        df_wind[nombre_real] = df_wind[nombre_real].str.strip()
    
    # Renombrar columnas para uniformidad (opcional)
    # Dejamos los nombres originales para no perder información
    
    return df_long, df_wind, wind_cols, col_names, meses_encontrados

# --- CARGAR DATOS ---
df_long, df_wind, wind_cols, col_names, meses = load_data()

if df_long.empty:
    st.stop()

# --- 2. BARRA LATERAL: FILTROS ---
st.sidebar.header("🔍 Filtros")

# Obtener nombres de las columnas clave
col_estacion = col_names['estacion']
col_variable = col_names['variable']
col_estadistico = col_names['estadistico']

# Obtener estaciones con datos
estaciones_con_datos = df_long[col_estacion].unique()
estaciones = sorted(estaciones_con_datos)
estacion_seleccionada = st.sidebar.selectbox("📍 Selecciona la Estación", estaciones)

# Filtrar por estación
df_estacion = df_long[df_long[col_estacion] == estacion_seleccionada]

# --- Variables y estadísticos con datos válidos ---
df_valid = df_estacion.dropna(subset=['Valor'])
if df_valid.empty:
    st.warning(f"⚠️ No hay datos disponibles para la estación **{estacion_seleccionada}**. Por favor, selecciona otra.")
    st.stop()

# Variables disponibles
variables_disponibles = sorted(df_valid[col_variable].unique())
variable_seleccionada = st.sidebar.selectbox("📊 Selecciona la Variable", variables_disponibles)

# Estadísticos disponibles
df_var = df_valid[df_valid[col_variable] == variable_seleccionada]
estadisticos_disponibles = sorted(df_var[col_estadistico].unique())
estadistico_seleccionado = st.sidebar.selectbox("📈 Selecciona el Estadístico", estadisticos_disponibles)

# --- 3. DATOS DE UBICACIÓN Y VIENTO ---
# Obtener fila de viento para la estación seleccionada
df_wind_estacion = df_wind[df_wind[col_estacion] == estacion_seleccionada]

if not df_wind_estacion.empty:
    lat = df_wind_estacion[col_names['latitud']].iloc[0]
    lon = df_wind_estacion[col_names['longitud']].iloc[0]
    altura = df_wind_estacion[col_names['altura']].iloc[0]
    periodo = df_wind_estacion[col_names['periodo']].iloc[0]
else:
    lat, lon, altura, periodo = None, None, None, None

# --- 4. VISUALIZACIÓN PRINCIPAL ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader(f"📈 Variación Mensual de {variable_seleccionada}")
    
    df_final = df_var[df_var[col_estadistico] == estadistico_seleccionado].sort_values('Mes_num')
    
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
        
        m = folium.Map(location=[float(lat), float(lon)], zoom_start=10)
        folium.Marker(
            [float(lat), float(lon)],
            popup=f"{estacion_seleccionada}<br>Altura: {altura}",
            icon=folium.Icon(color="red", icon="cloud"),
        ).add_to(m)
        st_folium(m, width=400, height=300)
    else:
        st.warning("No se encontraron datos de ubicación para esta estación.")

# --- 5. ROSA DE LOS VIENTOS ---
st.subheader("🌬️ Rosa de los Vientos")

if not df_wind_estacion.empty:
    direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    frecuencias = []
    velocidades = []
    
    for dir in direcciones:
        freq_col = f'Frecuencia {dir}'
        vel_col = f'Velocidad promedio {dir}'
        # Buscar si existen esas columnas en wind_cols
        if freq_col in df_wind_estacion.columns and vel_col in df_wind_estacion.columns:
            freq_val = df_wind_estacion[freq_col].iloc[0]
            vel_val = df_wind_estacion[vel_col].iloc[0]
            frecuencias.append(freq_val if pd.notna(freq_val) else 0)
            velocidades.append(vel_val if pd.notna(vel_val) else 0)
        else:
            frecuencias.append(0)
            velocidades.append(0)
    
    # CALMA
    calma_col = buscar_columna(df_wind_estacion, ['Frecuencia CALMA', 'CALMA'])
    calma_val = df_wind_estacion[calma_col].iloc[0] if calma_col else np.nan
    
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
        st.info("ℹ️ No hay datos de viento válidos para esta estación.")
else:
    st.info("ℹ️ Esta estación no tiene datos de viento en el archivo.")

# --- 6. DATOS PUNTUALES (KPI's) ---
st.subheader("📊 Datos Puntuales Clave")

kpi_estadisticos = ['Número de años considerados', 'Máximo valor diario', 'Mínimo valor diario']
kpi_data = {}

for est in kpi_estadisticos:
    if est in estadisticos_disponibles:
        df_kpi = df_var[df_var[col_estadistico] == est]
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
    st.dataframe(df_final[['Mes', 'Valor']] if not df_final.empty else pd.DataFrame())
