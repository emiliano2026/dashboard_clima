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

def convertir_numerico(series):
    """Convierte una serie a numérico, manejando comas como decimales y valores no válidos."""
    if series.dtype == 'object':
        # Reemplazar comas por puntos y eliminar caracteres no numéricos
        series = series.astype(str).str.replace(',', '.', regex=False)
        series = series.str.replace('S/D', '', regex=False).str.replace('S/P', '', regex=False)
        series = series.str.strip()
        # Reemplazar cadenas vacías con NaN
        series = series.replace('', np.nan)
    return pd.to_numeric(series, errors='coerce')

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
    
    # Leer CSV como texto para manejar decimales
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
    
    # --- MESES Y PERÍODOS ---
    meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    meses_encontrados = [m for m in meses if m in df_raw.columns]
    # Agregar 'Anual' si existe, o crearlo
    if 'Anual' not in df_raw.columns:
        # Si no existe, lo creamos como columna vacía (no se usará)
        df_raw['Anual'] = ''
    periodos = meses_encontrados + ['Anual']
    
    # --- ID_VARS ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- DETECTAR VARIABLE DE VIENTO ---
    # Buscar en la columna 'variable' cualquier fila que contenga 'frecuencia' y 'velocidad'
    pattern_viento = re.compile(r'frecuencia.*velocidad', re.IGNORECASE)
    # También buscar por '‰' que aparece en el nombre
    mask_viento = df_raw[col_names['variable']].str.contains(pattern_viento, na=False)
    if not mask_viento.any():
        # Si no, buscar por 'Frecuencia (‰)'
        pattern_viento2 = re.compile(r'frecuencia.*‰', re.IGNORECASE)
        mask_viento = df_raw[col_names['variable']].str.contains(pattern_viento2, na=False)
    
    # Separar datos de viento y no viento
    df_viento_raw = df_raw[mask_viento].copy()
    df_no_viento = df_raw[~mask_viento].copy()
    
    # --- DATOS DE VIENTO (formato ancho) ---
    # Todas las columnas que no son id_vars son períodos (meses + Anual)
    wind_cols = [col for col in df_viento_raw.columns if col not in id_vars]
    df_wind = df_viento_raw[id_vars + wind_cols].copy()
    
    # Convertir todas las columnas de viento a numérico
    for col in wind_cols:
        df_wind[col] = convertir_numerico(df_wind[col])
    
    # Limpiar nombres de estación, variable, estadístico
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
    
    # Limpiar nombres
    for col in ['estacion', 'variable', 'estadistico']:
        nombre_real = col_names[col]
        df_long[nombre_real] = df_long[nombre_real].str.strip()
    
    # Guardar la variable de viento encontrada (si existe)
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
            df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
            df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
            df_completo = df_completo.merge(df_temp[['Mes_num', 'Valor']], on='Mes_num', how='left')
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

# --- 5. ROSA DE VIENTOS Y OTROS DATOS ---
st.subheader("🌬️ Rosa de los Vientos")

# --- SELECTOR DE PERÍODO PARA VIENTO ---
if variable_viento and not df_wind.empty:
    # Filtrar datos de viento para la estación seleccionada
    df_wind_estacion = df_wind[df_wind[col_estacion] == estacion_seleccionada]
    
    if not df_wind_estacion.empty:
        # Períodos disponibles: columnas que están en 'periodos' y existen en df_wind_estacion
        periodos_disponibles = [p for p in periodos if p in df_wind_estacion.columns]
        if periodos_disponibles:
            # Ordenar: meses primero, luego Anual
            orden = {m: i for i, m in enumerate(meses)}
            orden['Anual'] = 12
            periodos_disponibles.sort(key=lambda x: orden.get(x, 99))
            
            periodo_viento = st.selectbox(
                "Selecciona el período para la rosa de vientos",
                periodos_disponibles,
                key="periodo_viento"
            )
        else:
            st.info("ℹ️ No hay períodos disponibles (meses o Anual) en los datos de viento.")
            periodo_viento = None
    else:
        st.info(f"ℹ️ No hay datos de viento para la estación {estacion_seleccionada}.")
        periodo_viento = None
else:
    st.info("ℹ️ La variable de viento no está disponible en esta base de datos.")
    periodo_viento = None

# --- GENERAR ROSA DE VIENTOS (columna izquierda) ---
col_wind, col_otros = st.columns([2, 1])

with col_wind:
    if variable_viento and periodo_viento and not df_wind_estacion.empty:
        # Extraer frecuencias y velocidades para cada dirección
        direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        frecuencias = []
        velocidades = []
        
        for dir in direcciones:
            # Buscar fila de Frecuencia
            freq_row = df_wind_estacion[
                (df_wind_estacion[col_estadistico] == f'Frecuencia {dir}')
            ]
            vel_row = df_wind_estacion[
                (df_wind_estacion[col_estadistico] == f'Velocidad promedio {dir}')
            ]
            
            if not freq_row.empty and not vel_row.empty:
                freq_val = freq_row[periodo_viento].iloc[0]
                vel_val = vel_row[periodo_viento].iloc[0]
                frecuencias.append(freq_val if pd.notna(freq_val) else 0)
                velocidades.append(vel_val if pd.notna(vel_val) else 0)
            else:
                frecuencias.append(0)
                velocidades.append(0)
        
        # CALMA
        calma_row = df_wind_estacion[
            (df_wind_estacion[col_estadistico] == 'Frecuencia CALMA')
        ]
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
                template='plotly_dark',
                title=f"Rosa de Vientos - {estacion_seleccionada} ({periodo_viento})",
                hover_data={'Velocidad (km/h)': True},
                barmode='relative'
            )
            fig_wind.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, tickfont=dict(size=12), gridcolor='rgba(255,255,255,0.2)'),
                    angularaxis=dict(direction="clockwise", period=8, tickfont=dict(size=14, color='white'))
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

# --- 6. OTROS DATOS (columna derecha) ---
with col_otros:
    st.subheader("📊 Otros Datos")
    
    kpi_estadisticos = ['Número de años considerados', 'Máximo valor diario', 'Mínimo valor diario']
    kpi_data = {}
    for est in kpi_estadisticos:
        if est in estadisticos:
            df_kpi = df_var[df_var[col_estadistico] == est]
            if not df_kpi.empty:
                # Convertir a numérico y eliminar NaN
                valores = pd.to_numeric(df_kpi['Valor'], errors='coerce').dropna()
                if not valores.empty:
                    kpi_data[est] = valores.mean()
    
    if kpi_data:
        for nombre, valor in kpi_data.items():
            display = nombre.replace('valor', '').strip()
            st.metric(label=display if display else nombre, value=f"{valor:.1f}")
    else:
        st.info("No hay datos adicionales para esta variable.")

# --- 7. TABLA DE DATOS ---
with st.expander("📋 Ver todos los datos de la variable seleccionada"):
    if 'df_completo' in locals():
        st.dataframe(df_completo)
    else:
        st.dataframe(df_final[['Mes', 'Valor']] if not df_final.empty else pd.DataFrame())
