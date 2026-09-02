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

# --- LOGO IIPAC EN LA BARRA LATERAL ---
try:
    st.sidebar.image("LogoIIPAC.jpg", use_container_width=True)
except:
    st.sidebar.warning("Logo no encontrado. Asegúrate de subir 'LogoIIPAC.jpg'.")

# --- TÍTULO PRINCIPAL ---
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

def convertir_valores(series):
    """
    Convierte una serie de pandas a numérico, manejando:
    - Coma como separador decimal (',')
    - Textos como 'S/D', 'S/P', '' como NaN
    - Cualquier otro texto no numérico como NaN
    """
    if series.dtype == 'object':
        # Reemplazar textos no numéricos
        series = series.str.replace(',', '.', regex=False)
        series = series.replace(['S/D', 'S/P', ''], np.nan)
        # Convertir a numérico, forzando errores a NaN
        series = pd.to_numeric(series, errors='coerce')
    else:
        # Si ya es numérico, solo asegurar que no haya problemas
        series = pd.to_numeric(series, errors='coerce')
    return series

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
    
    # Leer todo como texto para controlar la conversión manualmente
    df_raw = pd.read_csv(output, delimiter=sep, skipinitialspace=True, 
                         encoding='utf-8', dtype=str, keep_default_na=False)
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
    
    # --- COLUMNAS DE VIENTO ---
    wind_cols = []
    for col in df_raw.columns:
        col_lower = col.lower()
        if 'frecuencia' in col_lower or 'velocidad promedio' in col_lower or 'calma' in col_lower:
            wind_cols.append(col)
    
    # --- ID_VARS ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- DATOS DE VIENTO ---
    # Buscar la variable de viento (puede tener diferentes años)
    pattern_viento = re.compile(r'frecuencia.*velocidad', re.IGNORECASE)
    df_wind_raw = df_raw[df_raw[col_names['variable']].str.contains(pattern_viento, na=False)]
    if df_wind_raw.empty:
        pattern_viento = re.compile(r'frecuencia.*‰', re.IGNORECASE)
        df_wind_raw = df_raw[df_raw[col_names['variable']].str.contains(pattern_viento, na=False)]
    
    df_wind = df_wind_raw[id_vars + wind_cols].copy()
    # Convertir columnas de viento
    for col in wind_cols:
        if col in df_wind.columns:
            df_wind[col] = convertir_valores(df_wind[col])
    
    # --- DATOS MENSUALES (todas las filas que NO son de viento) ---
    # Identificar las filas que no son de viento
    if not df_wind_raw.empty:
        mask_wind = df_raw[col_names['variable']].isin(df_wind_raw[col_names['variable']])
    else:
        mask_wind = pd.Series([False] * len(df_raw), index=df_raw.index)
    
    df_no_wind = df_raw[~mask_wind]
    
    df_long = pd.melt(
        df_no_wind,
        id_vars=id_vars,
        value_vars=meses_encontrados,
        var_name='Mes',
        value_name='Valor'
    )
    # Convertir la columna Valor
    df_long['Valor'] = convertir_valores(df_long['Valor'])
    
    mes_map = {m: i+1 for i, m in enumerate(meses)}
    df_long['Mes_num'] = df_long['Mes'].map(mes_map)
    
    # Limpiar nombres
    for col in ['estacion', 'variable', 'estadistico']:
        nombre_real = col_names[col]
        if nombre_real in df_long.columns:
            df_long[nombre_real] = df_long[nombre_real].str.strip()
        if nombre_real in df_wind.columns:
            df_wind[nombre_real] = df_wind[nombre_real].str.strip()
    
    return df_long, df_wind, wind_cols, col_names, meses

# --- CARGAR DATOS ---
df_long, df_wind, wind_cols, col_names, meses = load_data()

# Verificar que df_long no esté vacío y que 'Valor' sea numérico
if df_long.empty:
    st.error("No se pudieron cargar datos. Verifica el archivo.")
    st.stop()

# --- 2. FILTROS ---
st.sidebar.header("🔍 Filtros")

col_estacion = col_names['estacion']
col_variable = col_names['variable']
col_estadistico = col_names['estadistico']

# --- ESTACIÓN ---
estaciones = sorted(df_long[col_estacion].unique())
estacion_seleccionada = st.sidebar.selectbox("📍 Estación", estaciones)

df_estacion = df_long[df_long[col_estacion] == estacion_seleccionada]

# Filtrar datos no nulos
df_valid = df_estacion.dropna(subset=['Valor'])

if df_valid.empty:
    st.warning(f"⚠️ No hay datos válidos para la estación **{estacion_seleccionada}**. Elige otra.")
    st.stop()

# --- VARIABLE (excluyendo la de viento) ---
variables_todas = sorted(df_valid[col_variable].unique())

# Identificar variable de viento
pattern_viento = re.compile(r'frecuencia.*velocidad', re.IGNORECASE)
variable_viento = None
for var in variables_todas:
    if pattern_viento.search(var):
        variable_viento = var
        break

# Variables que no son de viento
variables = [v for v in variables_todas if v != variable_viento]
if not variables:
    st.warning("No hay variables disponibles (todas son de viento).")
    st.stop()

variable_seleccionada = st.sidebar.selectbox("📊 Variable", variables)

# --- ESTADÍSTICO ---
df_var = df_valid[df_valid[col_variable] == variable_seleccionada]
estadisticos = sorted(df_var[col_estadistico].unique())
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

# --- 3. DATOS DE UBICACIÓN ---
df_wind_estacion = df_wind[df_wind[col_estacion] == estacion_seleccionada]
if not df_wind_estacion.empty:
    lat = df_wind_estacion[col_names['latitud']].iloc[0]
    lon = df_wind_estacion[col_names['longitud']].iloc[0]
    altura_raw = str(df_wind_estacion[col_names['altura']].iloc[0])
    # Extraer solo el número
    altura_num = re.search(r'[\d.]+', altura_raw)
    altura = altura_num.group(0) if altura_num else altura_raw
    periodo = df_wind_estacion[col_names['periodo']].iloc[0]
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
            df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
            df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
            df_completo = df_completo.merge(df_temp[['Mes_num', 'Valor']], on='Mes_num', how='left')
            # Asegurar que Valor sea numérico
            df_completo['Valor'] = pd.to_numeric(df_completo['Valor'], errors='coerce')
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
        df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
        df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
        df_completo = df_completo.merge(df_final[['Mes_num', 'Valor']], on='Mes_num', how='left')
        # Asegurar que Valor sea numérico
        df_completo['Valor'] = pd.to_numeric(df_completo['Valor'], errors='coerce')
        
        # Verificar si hay al menos un dato numérico
        if df_completo['Valor'].notna().any():
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
            
            # Calcular media solo si hay al menos 2 valores no nulos
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
        else:
            st.info("ℹ️ No hay datos numéricos para graficar.")

with col2:
    # --- MAPA ---
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

# --- 5. ROSA DE LOS VIENTOS (GRÁFICO DE RADAR) ---
st.subheader("🌬️ Rosa de los Vientos")

if variable_viento:
    # Obtener los datos de viento para la estación seleccionada
    df_viento_estacion = df_wind[
        (df_wind[col_estacion] == estacion_seleccionada) &
        (df_wind[col_variable] == variable_viento)
    ]
    
    if not df_viento_estacion.empty:
        # Filtrar solo la fila con estadístico "Promedio"
        df_promedio = df_viento_estacion[df_viento_estacion[col_estadistico] == 'Promedio']
        
        if not df_promedio.empty:
            # Extraer frecuencias y velocidades para las 8 direcciones
            direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
            frecuencias = []
            velocidades = []
            
            for dir in direcciones:
                freq_col = f'Frecuencia {dir}'
                vel_col = f'Velocidad promedio {dir}'
                if freq_col in df_promedio.columns and vel_col in df_promedio.columns:
                    freq_val = df_promedio[freq_col].iloc[0]
                    vel_val = df_promedio[vel_col].iloc[0]
                    frecuencias.append(freq_val if pd.notna(freq_val) else 0)
                    velocidades.append(vel_val if pd.notna(vel_val) else 0)
                else:
                    frecuencias.append(0)
                    velocidades.append(0)
            
            # Extraer CALMA
            calma_col = 'Frecuencia CALMA'
            calma_val = df_promedio[calma_col].iloc[0] if calma_col in df_promedio.columns else 0
            calma_val = calma_val if pd.notna(calma_val) else 0
            
            # Cerrar el polígono (repetir el primer valor al final)
            direcciones_closed = direcciones + [direcciones[0]]
            frecuencias_closed = frecuencias + [frecuencias[0]]
            velocidades_closed = velocidades + [velocidades[0]]
            
            # Crear gráfico de radar con dos líneas
            fig_radar = go.Figure()
            
            # Línea de Frecuencia (azul)
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
            
            # Línea de Velocidad (roja)
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
            
            # Agregar punto de CALMA en el centro
            if calma_val > 0:
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
                    radialaxis=dict(
                        visible=True,
                        tickfont=dict(size=10),
                        gridcolor='lightgray'
                    ),
                    angularaxis=dict(
                        direction='clockwise',
                        period=8,
                        tickfont=dict(size=12)
                    )
                ),
                title=f"Rosa de Vientos - {estacion_seleccionada} (Promedio anual)",
                template='plotly_white',
                legend=dict(orientation='h', y=1.1)
            )
            
            st.plotly_chart(fig_radar, use_container_width=True)
            
            if calma_val > 0:
                st.metric("Frecuencia CALMA (‰)", f"{calma_val:.1f}")
        else:
            st.info("ℹ️ No se encontró el estadístico 'Promedio' para la rosa de vientos.")
    else:
        st.info(f"ℹ️ No hay datos de viento para la estación {estacion_seleccionada}.")
else:
    st.info("ℹ️ La variable de viento no está disponible en esta base de datos.")

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

# --- 7. TABLA DE DATOS ---
with st.expander("📋 Ver todos los datos de la variable seleccionada"):
    if 'df_completo' in locals() and not df_completo.empty:
        st.dataframe(df_completo)
    elif 'df_final' in locals() and not df_final.empty:
        st.dataframe(df_final[['Mes', 'Valor']])
    else:
        st.info("No hay datos para mostrar.")

# --- 8. DEPURACIÓN ---
with st.expander("🔧 Información de depuración"):
    st.write("**Columnas de viento detectadas:**", wind_cols)
    if variable_viento:
        st.write("**Variable de viento encontrada:**", variable_viento)
        st.write("**Estadísticos de viento disponibles:**", sorted(df_wind[col_estadistico].unique()))
    else:
        st.write("**No se detectó variable de viento.**")
    # Verificar tipos
    st.write("**Tipo de la columna 'Valor' en df_long:**", df_long['Valor'].dtype)
    st.write("**Primeras filas de df_long:**")
    st.dataframe(df_long.head())
