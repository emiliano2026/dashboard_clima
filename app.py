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

# --- LOGO DEL IIPAC (original) ---
try:
    st.sidebar.image("LogoIIPAC.jpg", use_container_width=True)
except:
    st.sidebar.warning("Logo no encontrado. Sube 'LogoIIPAC.jpg' al repositorio.")

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
    
    # Leer CSV con manejo de decimales (coma como separador decimal)
    df_raw = pd.read_csv(output, delimiter=sep, skipinitialspace=True, 
                         encoding='utf-8', decimal=',')
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
    
    # --- COLUMNAS DE VIENTO (búsqueda mejorada) ---
    # Buscar cualquier columna que tenga 'frecuencia' O 'velocidad'
    wind_cols = []
    for col in df_raw.columns:
        col_lower = col.lower()
        if 'frecuencia' in col_lower or 'velocidad' in col_lower:
            wind_cols.append(col)
    
    # También buscar 'calma'
    calma_col = buscar_columna(df_raw, ['calma'])
    if calma_col and calma_col not in wind_cols:
        wind_cols.append(calma_col)
    
    # --- ID_VARS ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- DATOS DE VIENTO (se mantienen en formato ancho) ---
    df_wind = df_raw[id_vars + wind_cols].copy()
    for col in wind_cols:
        df_wind[col] = pd.to_numeric(df_wind[col].replace(['S/D', 'S/P', ''], np.nan), errors='coerce')
    
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

# --- ESTACIÓN ---
estaciones = sorted(df_long[col_estacion].unique())
estacion_seleccionada = st.sidebar.selectbox("📍 Estación", estaciones)

df_estacion = df_long[df_long[col_estacion] == estacion_seleccionada]
df_valid = df_estacion.dropna(subset=['Valor'])

if df_valid.empty:
    st.warning(f"⚠️ No hay datos para la estación **{estacion_seleccionada}**. Elige otra.")
    st.stop()

# --- VARIABLE (excluyendo la de viento) ---
variables_todas = sorted(df_valid[col_variable].unique())
# Identificar variable de viento (contiene 'frecuencia' y 'velocidad')
variable_viento = None
for var in variables_todas:
    if 'frecuencia' in var.lower() and 'velocidad' in var.lower():
        variable_viento = var
        break

# Si no se encuentra por nombre, buscar por columnas de viento
if not variable_viento and wind_cols:
    # Buscar en df_wind alguna fila que tenga columnas de viento
    for est in estaciones:
        df_temp = df_wind[df_wind[col_estacion] == est]
        if not df_temp.empty:
            for var in df_temp[col_variable].unique():
                if any(col in wind_cols for col in df_temp.columns):
                    variable_viento = var
                    break
        if variable_viento:
            break

variables = [v for v in variables_todas if v != variable_viento]
if not variables:
    st.warning("No hay variables disponibles (todas son de viento).")
    st.stop()

variable_seleccionada = st.sidebar.selectbox("📊 Variable", variables)

# --- ESTADÍSTICO ---
df_var = df_valid[df_valid[col_variable] == variable_seleccionada]
estadisticos = sorted(df_var[col_estadistico].unique())

# Asegurar que 'Promedio' esté siempre en la lista (si existe en los datos)
if 'Promedio' in estadisticos:
    default_estadistico = 'Promedio'
else:
    default_estadistico = estadisticos[0] if estadisticos else None

estadistico_seleccionado = st.sidebar.selectbox("📈 Estadístico", estadisticos, index=estadisticos.index(default_estadistico) if default_estadistico in estadisticos else 0)

# --- SUPERPOSICIÓN (multiselect) ---
superponer = st.sidebar.checkbox("🔄 Superponer estadísticos")
estadisticos_a_superponer = []
if superponer:
    # Por defecto, seleccionar 'Promedio' si existe, y otro
    default_selection = [est for est in ['Promedio', 'Máximo valor promedio', 'Mínimo valor promedio'] if est in estadisticos]
    if not default_selection and len(estadisticos) >= 2:
        default_selection = estadisticos[:2]
    estadisticos_a_superponer = st.sidebar.multiselect(
        "Selecciona los estadísticos a superponer (máximo 3)",
        estadisticos,
        default=default_selection[:3]
    )

# --- 3. DATOS DE UBICACIÓN ---
df_wind_estacion = df_wind[df_wind[col_estacion] == estacion_seleccionada]
if not df_wind_estacion.empty:
    lat = df_wind_estacion[col_names['latitud']].iloc[0]
    lon = df_wind_estacion[col_names['longitud']].iloc[0]
    altura = df_wind_estacion[col_names['altura']].iloc[0]
    periodo = df_wind_estacion[col_names['periodo']].iloc[0]
else:
    lat = lon = altura = periodo = None

# --- 4. GRÁFICO PRINCIPAL ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader(f"📈 Variación Mensual de {variable_seleccionada}")
    
    if superponer and len(estadisticos_a_superponer) > 1:
        # --- SUPERPOSICIÓN MANUAL ---
        fig = go.Figure()
        for est in estadisticos_a_superponer:
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

# --- 5. ROSA DE LOS VIENTOS ---
st.subheader("🌬️ Rosa de los Vientos")

# --- Selector de período para la rosa de vientos (dentro de la sección) ---
periodos_viento = ['Anual'] + meses
periodo_seleccionado = st.selectbox("Selecciona el período para la rosa de vientos", periodos_viento, key="periodo_viento")

# Verificar si existe la variable de viento y hay datos
if variable_viento:
    # Filtrar fila de viento para la estación y período seleccionado
    if periodo_seleccionado == 'Anual':
        df_viento_filtrado = df_wind[
            (df_wind[col_estacion] == estacion_seleccionada) &
            (df_wind[col_variable] == variable_viento) &
            (df_wind[col_estadistico] == 'Anual')
        ]
    else:
        df_viento_filtrado = df_wind[
            (df_wind[col_estacion] == estacion_seleccionada) &
            (df_wind[col_variable] == variable_viento) &
            (df_wind[col_estadistico] == periodo_seleccionado)
        ]
    
    if not df_viento_filtrado.empty:
        # Extraer direcciones y sus valores
        direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        frecuencias = []
        velocidades = []
        
        for dir in direcciones:
            # Buscar columnas de frecuencia y velocidad para esta dirección
            freq_col = buscar_columna(df_viento_filtrado, [f'frecuencia {dir}', f'frec {dir}'])
            vel_col = buscar_columna(df_viento_filtrado, [f'velocidad promedio {dir}', f'vel {dir}'])
            
            if freq_col and vel_col:
                freq_val = df_viento_filtrado[freq_col].iloc[0]
                vel_val = df_viento_filtrado[vel_col].iloc[0]
                frecuencias.append(freq_val if pd.notna(freq_val) else 0)
                velocidades.append(vel_val if pd.notna(vel_val) else 0)
            else:
                frecuencias.append(0)
                velocidades.append(0)
        
        # Buscar CALMA
        calma_col = buscar_columna(df_viento_filtrado, ['frecuencia calma', 'calma'])
        calma_val = df_viento_filtrado[calma_col].iloc[0] if calma_col else np.nan
        
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
                title=f"Rosa de Vientos - {estacion_seleccionada} ({periodo_seleccionado})",
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
            st.info("ℹ️ No hay datos de viento válidos para este período.")
    else:
        st.info(f"ℹ️ No se encontraron datos de viento para {estacion_seleccionada} - {periodo_seleccionado}.")
else:
    st.info("ℹ️ No se detectó la variable de viento en el archivo. Verifica que existan columnas con 'Frecuencia' y 'Velocidad'.")

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
        st.dataframe(df_final[['Mes', 'Valor']] if not df_final.empty else pd.DataFrame())
