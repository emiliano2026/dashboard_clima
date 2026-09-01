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
st.set_page_config(page_title="Dashboard Clima IIPAC", layout="wide")

# --- LOGO ---
try:
    st.sidebar.image("LogoIIPAC.jpg", use_container_width=True)
except:
    st.sidebar.warning("Logo no encontrado. Sube 'LogoIIPAC.jpg' al repositorio.")

# --- TÍTULO ---
st.title("📊 Dashboard Datos Clima IIPAC")
st.caption("Fuente: Servicio Meteorológico Nacional (SMN)")

# --- FUNCIONES AUXILIARES ---
def normalizar_nombre(nombre):
    """Quita tildes, espacios y convierte a minúsculas"""
    nombre = nombre.strip()
    nombre = re.sub(r'[áÁ]', 'a', nombre)
    nombre = re.sub(r'[éÉ]', 'e', nombre)
    nombre = re.sub(r'[íÍ]', 'i', nombre)
    nombre = re.sub(r'[óÓ]', 'o', nombre)
    nombre = re.sub(r'[úÚ]', 'u', nombre)
    nombre = re.sub(r'[ñÑ]', 'n', nombre)
    return re.sub(r'[^a-z0-9]', '', nombre.lower())

def buscar_columna(df, patrones):
    """Busca una columna que contenga alguna de las palabras clave"""
    columnas_norm = {normalizar_nombre(col): col for col in df.columns}
    for patron in patrones:
        patron_norm = normalizar_nombre(patron)
        for col_norm, col_real in columnas_norm.items():
            if patron_norm in col_norm or col_norm in patron_norm:
                return col_real
    return None

def extraer_direccion(nombre_columna):
    """Extrae la dirección cardinal (N, NE, E, etc.) de un nombre de columna"""
    direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    for dir in direcciones:
        if dir in nombre_columna:
            return dir
    return None

# --- 1. CARGA DE DATOS ---
@st.cache_data
def load_data():
    file_id = "1-XZ-eYH7iyxJpaWerNaBERy_joHr4lLJ"
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    output = "datos_clima_smn.csv"
    
    if not os.path.exists(output):
        with st.spinner("Descargando datos desde Google Drive..."):
            gdown.download(url, output, quiet=False)
    
    # Detectar separador
    with open(output, 'r', encoding='utf-8') as f:
        first_line = f.readline()
        sep = '|' if '|' in first_line else (';' if ';' in first_line else ',')
    
    df_raw = pd.read_csv(output, delimiter=sep, skipinitialspace=True, encoding='utf-8')
    df_raw.columns = df_raw.columns.str.strip()
    
    # --- MAPEO DE COLUMNAS CLAVE ---
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
    
    # --- MESES ---
    meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    meses_encontrados = [m for m in meses if m in df_raw.columns]
    if len(meses_encontrados) < 12:
        st.warning(f"⚠️ Solo se encontraron {len(meses_encontrados)} meses. Se usarán los disponibles.")
    
    # --- COLUMNAS DE VIENTO (BUSCANDO "ANUAL") ---
    wind_cols = []
    # Buscar columnas que contengan "ANUAL" o "anual"
    for col in df_raw.columns:
        if 'anual' in col.lower():
            wind_cols.append(col)
    
    # Si no se encontraron con "ANUAL", buscar por palabras clave genéricas
    if not wind_cols:
        keywords = ['frecuencia', 'velocidad promedio', 'calma']
        for col in df_raw.columns:
            col_lower = col.lower()
            if any(kw in col_lower for kw in keywords):
                wind_cols.append(col)
    
    # --- ID_VARS ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- DATOS DE VIENTO (solo si hay columnas) ---
    if wind_cols:
        df_wind = df_raw[id_vars + wind_cols].copy()
        for col in wind_cols:
            df_wind[col] = pd.to_numeric(df_wind[col].replace(['S/D', 'S/P', ''], np.nan), errors='coerce')
    else:
        df_wind = pd.DataFrame()
        st.warning("⚠️ No se encontraron columnas de viento en el archivo.")
    
    # --- DATOS MENSUALES (formato largo) ---
    df_long = pd.melt(
        df_raw,
        id_vars=id_vars,
        value_vars=meses_encontrados,
        var_name='Mes',
        value_name='Valor'
    )
    df_long['Valor'] = pd.to_numeric(df_long['Valor'].replace(['S/D', 'S/P', ''], np.nan), errors='coerce')
    
    mes_map = {m: i+1 for i, m in enumerate(meses)}
    df_long['Mes_num'] = df_long['Mes'].map(mes_map)
    
    # Limpiar nombres
    for col in ['estacion', 'variable', 'estadistico']:
        nombre_real = col_names[col]
        df_long[nombre_real] = df_long[nombre_real].str.strip()
        if not df_wind.empty:
            df_wind[nombre_real] = df_wind[nombre_real].str.strip()
    
    return df_long, df_wind, wind_cols, col_names, meses

# --- CARGAR DATOS ---
df_long, df_wind, wind_cols, col_names, meses = load_data()
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

variables = sorted(df_valid[col_variable].unique())
variable_seleccionada = st.sidebar.selectbox("📊 Variable", variables)

df_var = df_valid[df_valid[col_variable] == variable_seleccionada]
estadisticos = sorted(df_var[col_estadistico].unique())

# --- SELECCIÓN MÚLTIPLE DE ESTADÍSTICOS PARA SUPERPOSICIÓN ---
st.sidebar.markdown("---")
st.sidebar.subheader("📈 Superposición")
superponer = st.sidebar.checkbox("Activar superposición de estadísticos")
estadisticos_seleccionados = []
if superponer and len(estadisticos) > 1:
    estadisticos_seleccionados = st.sidebar.multiselect(
        "Selecciona los estadísticos a superponer",
        options=estadisticos,
        default=estadisticos[:2] if len(estadisticos) >= 2 else estadisticos
    )
else:
    estadistico_seleccionado = st.sidebar.selectbox("📈 Estadístico", estadisticos)

# --- 3. DATOS DE UBICACIÓN ---
if not df_wind.empty:
    df_wind_estacion = df_wind[df_wind[col_estacion] == estacion_seleccionada]
    if not df_wind_estacion.empty:
        lat = df_wind_estacion[col_names['latitud']].iloc[0]
        lon = df_wind_estacion[col_names['longitud']].iloc[0]
        altura = df_wind_estacion[col_names['altura']].iloc[0]
        periodo = df_wind_estacion[col_names['periodo']].iloc[0]
    else:
        lat = lon = altura = periodo = None
else:
    lat = lon = altura = periodo = None

# --- 4. GRÁFICO PRINCIPAL ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader(f"📈 Variación Mensual de {variable_seleccionada}")
    
    if superponer and estadisticos_seleccionados:
        # --- SUPERPOSICIÓN CON ESTADÍSTICOS SELECCIONADOS ---
        fig = go.Figure()
        for est in estadisticos_seleccionados:
            df_temp = df_var[df_var[col_estadistico] == est].sort_values('Mes_num')
            # Completar meses faltantes
            df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
            df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
            df_completo = df_completo.merge(df_temp[['Mes_num', 'Valor']], on='Mes_num', how='left')
            # Agregar línea
            fig.add_trace(go.Scatter(
                x=df_completo['Mes'],
                y=df_completo['Valor'],
                mode='lines+markers',
                name=est,
                line=dict(width=2)
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
        # --- GRÁFICO INDIVIDUAL ---
        df_final = df_var[df_var[col_estadistico] == estadistico_seleccionado].sort_values('Mes_num')
        # Completar meses faltantes
        df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
        df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
        df_completo = df_completo.merge(df_final[['Mes_num', 'Valor']], on='Mes_num', how='left')
        
        fig_line = px.line(
            df_completo,
            x='Mes',
            y='Valor',
            markers=True,
            title=f"{variable_seleccionada} - {estadistico_seleccionado}",
            labels={'Mes': 'Mes', 'Valor': 'Valor'},
            template='plotly_white',
        )
        # Media anual
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
    # --- MAPA CON NOMBRE DE ESTACIÓN ---
    st.subheader(f"📍 {estacion_seleccionada}")
    if lat and lon:
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
        st.warning("Datos de ubicación no disponibles.")

# --- 5. ROSA DE LOS VIENTOS (USANDO COLUMNAS "ANUAL") ---
st.subheader("🌬️ Rosa de los Vientos")

if not df_wind.empty and not df_wind_estacion.empty:
    # Buscar columnas que contengan "ANUAL" y tengan direcciones
    columnas_viento = df_wind_estacion.columns
    # Filtrar columnas que contengan "anual" (insensible a mayúsculas)
    col_anual = [col for col in columnas_viento if 'anual' in col.lower()]
    
    if col_anual:
        # Extraer frecuencias y velocidades para cada dirección
        direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        frecuencias = []
        velocidades = []
        
        for dir in direcciones:
            # Buscar columna de frecuencia para esta dirección (que contenga "anual")
            freq_col = None
            vel_col = None
            for col in col_anual:
                if 'frecuencia' in col.lower() and dir in col:
                    freq_col = col
                if 'velocidad' in col.lower() and dir in col:
                    vel_col = col
            
            if freq_col and vel_col:
                freq_val = df_wind_estacion[freq_col].iloc[0]
                vel_val = df_wind_estacion[vel_col].iloc[0]
                frecuencias.append(freq_val if pd.notna(freq_val) else 0)
                velocidades.append(vel_val if pd.notna(vel_val) else 0)
            else:
                frecuencias.append(0)
                velocidades.append(0)
        
        # Buscar CALMA (si existe)
        calma_col = None
        for col in col_anual:
            if 'calma' in col.lower():
                calma_col = col
                break
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
            st.info("ℹ️ No se encontraron datos de viento válidos (frecuencias cero o nulas) para esta estación.")
    else:
        st.info("ℹ️ No se encontraron columnas con 'ANUAL' para datos de viento. Verifica que el archivo tenga columnas como 'Frecuencia N (ANUAL)'.")
else:
    st.info("ℹ️ Esta estación no tiene datos de viento en el archivo.")

# --- 6. OTROS DATOS ---
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
    st.info("No hay datos adicionales para esta variable.")

# --- 7. TABLA DE DATOS (opcional) ---
with st.expander("📋 Ver todos los datos de la variable seleccionada"):
    if 'df_completo' in locals():
        st.dataframe(df_completo)
    else:
        st.dataframe(df_final[['Mes', 'Valor']] if 'df_final' in locals() and not df_final.empty else pd.DataFrame())
