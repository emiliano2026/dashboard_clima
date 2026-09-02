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
    """Busca una columna que coincida con alguno de los patrones (insensible a mayúsculas, tildes, espacios)."""
    columnas_norm = {normalizar_nombre(col): col for col in df.columns}
    for patron in patrones:
        patron_norm = normalizar_nombre(patron)
        # Primero buscar coincidencia exacta
        if patron_norm in columnas_norm:
            return columnas_norm[patron_norm]
        # Luego buscar coincidencia parcial
        for col_norm, col_real in columnas_norm.items():
            if patron_norm in col_norm or col_norm in patron_norm:
                return col_real
    return None

def extraer_direcciones(df_row):
    """Extrae frecuencias y velocidades para las 8 direcciones desde una fila de viento."""
    direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    frecuencias = []
    velocidades = []
    
    for dir in direcciones:
        # Buscar columna de frecuencia y velocidad para esta dirección
        freq_col = buscar_columna(df_row, [f'frecuencia {dir}', f'frec {dir}'])
        vel_col = buscar_columna(df_row, [f'velocidad promedio {dir}', f'vel {dir}'])
        
        if freq_col and freq_col in df_row.columns:
            freq_val = df_row[freq_col].iloc[0] if not df_row[freq_col].isna().all() else np.nan
        else:
            freq_val = np.nan
        
        if vel_col and vel_col in df_row.columns:
            vel_val = df_row[vel_col].iloc[0] if not df_row[vel_col].isna().all() else np.nan
        else:
            vel_val = np.nan
        
        frecuencias.append(freq_val if pd.notna(freq_val) else 0)
        velocidades.append(vel_val if pd.notna(vel_val) else 0)
    
    # Buscar CALMA
    calma_col = buscar_columna(df_row, ['frecuencia calma', 'calma'])
    calma_val = df_row[calma_col].iloc[0] if calma_col and calma_col in df_row.columns else np.nan
    
    return direcciones, frecuencias, velocidades, calma_val

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
    wind_cols = []
    for col in df_raw.columns:
        col_lower = col.lower()
        # Buscar columnas que contengan "frecuencia" o "velocidad promedio" (con o sin paréntesis)
        if 'frecuencia' in col_lower or 'velocidad promedio' in col_lower or 'calma' in col_lower:
            wind_cols.append(col)
    
    # Si no se encontraron, intentar con búsqueda más flexible (solo "frec" o "veloc")
    if not wind_cols:
        for col in df_raw.columns:
            col_lower = col.lower()
            if 'frec' in col_lower or 'veloc' in col_lower:
                wind_cols.append(col)
    
    # --- ID_VARS ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- DATOS DE VIENTO (se mantienen en formato ancho) ---
    df_wind = df_raw[id_vars + wind_cols].copy()
    # Reemplazar 'S/D', 'S/P' por NaN y convertir a numérico
    for col in wind_cols:
        # Reemplazar texto
        df_wind[col] = df_wind[col].replace(['S/D', 'S/P', ''], np.nan)
        # Si es texto, reemplazar coma por punto y convertir
        if df_wind[col].dtype == 'object':
            df_wind[col] = df_wind[col].str.replace(',', '.').astype(float, errors='ignore')
        df_wind[col] = pd.to_numeric(df_wind[col], errors='coerce')
    
    # --- DATOS MENSUALES (formato largo) ---
    df_long = pd.melt(
        df_raw,
        id_vars=id_vars,
        value_vars=meses_encontrados,
        var_name='Mes',
        value_name='Valor'
    )
    # Limpiar valores mensuales
    df_long['Valor'] = df_long['Valor'].replace(['S/D', 'S/P', ''], np.nan)
    if df_long['Valor'].dtype == 'object':
        df_long['Valor'] = df_long['Valor'].str.replace(',', '.').astype(float, errors='ignore')
    df_long['Valor'] = pd.to_numeric(df_long['Valor'], errors='coerce')
    
    mes_map = {m: i+1 for i, m in enumerate(meses)}
    df_long['Mes_num'] = df_long['Mes'].map(mes_map)
    
    # Limpiar nombres
    for col in ['estacion', 'variable', 'estadistico']:
        nombre_real = col_names[col]
        df_long[nombre_real] = df_long[nombre_real].str.strip()
        df_wind[nombre_real] = df_wind[nombre_real].str.strip()
    
    # Limpiar altura (extraer solo el número si viene con "m" o "msnm")
    if col_names['altura'] in df_wind.columns:
        df_wind[col_names['altura']] = df_wind[col_names['altura']].astype(str).str.extract(r'(\d+\.?\d*)').astype(float)
    
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

# Identificar la variable de viento (puede tener paréntesis y años diferentes)
variable_viento = None
pattern_viento = re.compile(r'frecuencia.*velocidad', re.IGNORECASE)
for var in variables_todas:
    if pattern_viento.search(var):
        variable_viento = var
        break
# Si no se encontró con el patrón, buscar por palabras clave
if not variable_viento:
    for var in variables_todas:
        if 'frecuencia' in var.lower() and 'velocidad' in var.lower():
            variable_viento = var
            break

variables = [v for v in variables_todas if v != variable_viento]
if not variables:
    st.warning("No hay variables disponibles (todas son de viento).")
    st.stop()

variable_seleccionada = st.sidebar.selectbox("📊 Variable", variables)

# --- ESTADÍSTICO ---
df_var = df_valid[df_valid[col_variable] == variable_seleccionada]
estadisticos = sorted(df_var[col_estadistico].unique())
estadistico_seleccionado = st.sidebar.selectbox("📈 Estadístico", estadisticos)

# --- SUPERPOSICIÓN (multiselect) ---
superponer = st.sidebar.checkbox("🔄 Superponer estadísticos")
estadisticos_a_superponer = []
if superponer:
    # Mostrar todos los estadísticos excepto "Número de años considerados" y similares
    opciones_superposicion = [e for e in estadisticos if 'años' not in e.lower() and 'diario' not in e.lower()]
    # Si no hay opciones (por ejemplo, solo "Número de años"), mostrar todos
    if not opciones_superposicion:
        opciones_superposicion = estadisticos
    estadisticos_a_superponer = st.sidebar.multiselect(
        "Selecciona los estadísticos a superponer (máximo 3)",
        opciones_superposicion,
        default=opciones_superposicion[:2] if len(opciones_superposicion) >= 2 else opciones_superposicion
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
            # Agregar línea (con connectgaps para unir puntos)
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
    # --- MAPA CON NOMBRE DE ESTACIÓN ---
    st.subheader(f"📍 {estacion_seleccionada}")
    if lat and lon:
        st.write(f"Altura: {altura:.1f} msnm" if altura else "Altura: N/D")
        st.write(f"Período: {periodo}")
        m = folium.Map(location=[float(lat), float(lon)], zoom_start=10)
        folium.Marker(
            [float(lat), float(lon)],
            popup=f"{estacion_seleccionada}<br>Altura: {altura:.1f} msnm" if altura else "",
            icon=folium.Icon(color="red", icon="cloud"),
        ).add_to(m)
        st_folium(m, width=400, height=300)
    else:
        st.warning("Datos de ubicación no disponibles.")

# --- 5. ROSA DE LOS VIENTOS ---
st.subheader("🌬️ Rosa de los Vientos")

# Verificar si existe la variable de viento
if variable_viento:
    # Obtener la fila de viento para la estación seleccionada
    df_viento_filtrado = df_wind[
        (df_wind[col_estacion] == estacion_seleccionada) &
        (df_wind[col_variable] == variable_viento)
    ]
    
    if not df_viento_filtrado.empty:
        # Tomar la primera fila (solo hay una por estación)
        df_viento_row = df_viento_filtrado.iloc[[0]]
        
        # Extraer direcciones usando la función auxiliar
        direcciones, frecuencias, velocidades, calma_val = extraer_direcciones(df_viento_row)
        
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
        st.info(f"ℹ️ No se encontraron datos de viento para {estacion_seleccionada}.")
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

# --- 7. TABLA DE DATOS (opcional) ---
with st.expander("📋 Ver todos los datos de la variable seleccionada"):
    if 'df_completo' in locals():
        st.dataframe(df_completo)
    else:
        st.dataframe(df_final[['Mes', 'Valor']] if not df_final.empty else pd.DataFrame())

# --- 8. DEPURACIÓN (mostrar columnas detectadas) ---
with st.expander("🔧 Información de depuración (solo para revisión)"):
    st.write("**Columnas de viento detectadas:**", wind_cols)
    if variable_viento:
        st.write("**Variable de viento encontrada:**", variable_viento)
        st.write("**Estadísticos disponibles para viento en esta estación:**", 
                 sorted(df_wind[df_wind[col_estacion] == estacion_seleccionada][col_estadistico].unique()))
    else:
        st.write("**No se detectó variable de viento.**")
