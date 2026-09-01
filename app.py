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
    st.sidebar.image("Rosa_de_los_vientos.png", use_container_width=True)
except:
    st.sidebar.warning("Logo no encontrado. Sube 'Rosa_de_los_vientos.png'.")

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

def buscar_columna_por_patron(df, patrones):
    """Busca una columna cuyo nombre contenga alguna de las palabras clave (sin importar mayúsculas/tildes)"""
    for col in df.columns:
        col_norm = normalizar_nombre(col)
        for patron in patrones:
            patron_norm = normalizar_nombre(patron)
            if patron_norm in col_norm:
                return col
    return None

def buscar_columnas_por_patron(df, patrones):
    """Devuelve todas las columnas que contengan alguna de las palabras clave"""
    columnas = []
    for col in df.columns:
        col_norm = normalizar_nombre(col)
        for patron in patrones:
            patron_norm = normalizar_nombre(patron)
            if patron_norm in col_norm:
                columnas.append(col)
                break
    return columnas

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
    
    # Leer CSV con decimal coma
    df_raw = pd.read_csv(output, delimiter=sep, skipinitialspace=True, 
                         encoding='utf-8', decimal=',')
    df_raw.columns = df_raw.columns.str.strip()
    
    # --- MAPEO DE COLUMNAS CLAVE (metadatos) ---
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
        encontrada = buscar_columna_por_patron(df_raw, patrones)
        if encontrada:
            col_names[key] = encontrada
        else:
            st.error(f"❌ No se encontró la columna para '{key}'. Columnas disponibles: {list(df_raw.columns)}")
            st.stop()
    
    # --- MESES ---
    meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    meses_encontrados = [m for m in meses if m in df_raw.columns]
    
    # --- IDENTIFICAR VARIABLE DE VIENTO ---
    # Buscar cualquier columna que contenga "Frecuencia (‰) y velocidad promedio (km/h) por dirección"
    # o similar, sin importar el período entre paréntesis
    variable_viento = None
    for col in df_raw[col_names['variable']].unique():
        if 'frecuencia' in col.lower() and 'velocidad promedio' in col.lower():
            variable_viento = col
            break
    
    # Si no se encuentra exactamente, buscar por palabras clave
    if not variable_viento:
        for col in df_raw[col_names['variable']].unique():
            if 'frecuencia' in col.lower() and 'velocidad' in col.lower():
                variable_viento = col
                break
    
    # --- IDENTIFICAR COLUMNAS DE VIENTO (17 columnas) ---
    # Buscar todas las columnas que contengan "Frecuencia", "Velocidad promedio" o "CALMA"
    wind_cols = buscar_columnas_por_patron(df_raw, ['frecuencia', 'velocidad promedio', 'calma'])
    
    # También buscar específicamente las direcciones (N, NE, E, SE, S, SW, W, NW)
    direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    for dir in direcciones:
        # Buscar Frecuencia + dirección y Velocidad promedio + dirección
        for col in df_raw.columns:
            col_norm = normalizar_nombre(col)
            if f'frecuencia{dir}' in col_norm or f'velocidadpromedio{dir}' in col_norm:
                if col not in wind_cols:
                    wind_cols.append(col)
    
    # --- ID_VARS ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- DATOS DE VIENTO (formato ancho) ---
    # Tomamos todas las filas que corresponden a la variable de viento
    if variable_viento:
        df_wind_raw = df_raw[df_raw[col_names['variable']] == variable_viento].copy()
        # Nos quedamos solo con las columnas de interés
        columnas_wind = id_vars + wind_cols
        # Asegurar que todas las columnas existan
        columnas_wind = [c for c in columnas_wind if c in df_wind_raw.columns]
        df_wind = df_wind_raw[columnas_wind].copy()
    else:
        df_wind = pd.DataFrame()
        wind_cols = []
    
    # Limpiar valores de viento: reemplazar 'S/D', 'S/P' por NaN
    for col in wind_cols:
        if col in df_wind.columns:
            df_wind[col] = pd.to_numeric(df_wind[col].replace(['S/D', 'S/P', ''], np.nan), errors='coerce')
    
    # --- DATOS MENSUALES (formato largo) para todas las variables EXCEPTO viento ---
    # Excluir la variable de viento
    variables_no_viento = [v for v in df_raw[col_names['variable']].unique() if v != variable_viento]
    df_no_viento = df_raw[df_raw[col_names['variable']].isin(variables_no_viento)]
    
    df_long = pd.melt(
        df_no_viento,
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
    
    return df_long, df_wind, wind_cols, col_names, meses, variable_viento

# --- CARGAR DATOS ---
df_long, df_wind, wind_cols, col_names, meses, variable_viento = load_data()
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

# --- SUPERPOSICIÓN (multiselect) ---
superponer = st.sidebar.checkbox("🔄 Superponer estadísticos")
estadisticos_a_superponer = []
if superponer:
    estadisticos_a_superponer = st.sidebar.multiselect(
        "Selecciona los estadísticos a superponer (máximo 3)",
        estadisticos,
        default=estadisticos[:2] if len(estadisticos) >= 2 else estadisticos
    )

# --- SELECTOR DE MES PARA ROSA DE VIENTOS ---
# Solo si existen datos de viento y la variable está presente
if variable_viento and not df_wind.empty:
    # Filtrar por estación seleccionada
    df_wind_estacion = df_wind[df_wind[col_estacion] == estacion_seleccionada]
    if not df_wind_estacion.empty:
        # Obtener estadísticos (meses o Anual) disponibles para esta estación
        estadisticos_viento = sorted(df_wind_estacion[col_estadistico].unique())
        # Filtrar los que son meses o Anual
        opciones_viento = []
        for est in estadisticos_viento:
            if est in meses or est == 'Anual':
                opciones_viento.append(est)
        if opciones_viento:
            # Asegurar que 'Anual' esté primero
            if 'Anual' in opciones_viento:
                opciones_viento.remove('Anual')
                opciones_viento = ['Anual'] + sorted(opciones_viento)
            mes_viento_seleccionado = st.sidebar.selectbox("🌬️ Mes para rosa de vientos", opciones_viento)
        else:
            mes_viento_seleccionado = None
            st.sidebar.info("No hay meses disponibles para rosa de vientos.")
    else:
        mes_viento_seleccionado = None
        st.sidebar.info("Esta estación no tiene datos de viento.")
else:
    mes_viento_seleccionado = None

# --- 3. DATOS DE UBICACIÓN ---
df_wind_estacion = df_wind[df_wind[col_estacion] == estacion_seleccionada] if not df_wind.empty else pd.DataFrame()
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

# --- 5. ROSA DE LOS VIENTOS ---
st.subheader("🌬️ Rosa de los Vientos")

if variable_viento and mes_viento_seleccionado and not df_wind.empty:
    # Filtrar fila de viento para la estación y mes seleccionado
    df_viento_filtrado = df_wind[
        (df_wind[col_estacion] == estacion_seleccionada) &
        (df_wind[col_estadistico] == mes_viento_seleccionado)
    ]
    
    if not df_viento_filtrado.empty:
        # Extraer direcciones y sus valores usando las columnas detectadas
        direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        frecuencias = []
        velocidades = []
        
        for dir in direcciones:
            # Buscar columna de frecuencia y velocidad para esta dirección
            freq_col = buscar_columna_por_patron(df_viento_filtrado, [f'frecuencia {dir}', f'frec {dir}'])
            vel_col = buscar_columna_por_patron(df_viento_filtrado, [f'velocidad promedio {dir}', f'vel {dir}'])
            
            if freq_col and vel_col:
                freq_val = df_viento_filtrado[freq_col].iloc[0]
                vel_val = df_viento_filtrado[vel_col].iloc[0]
                frecuencias.append(freq_val if pd.notna(freq_val) else 0)
                velocidades.append(vel_val if pd.notna(vel_val) else 0)
            else:
                frecuencias.append(0)
                velocidades.append(0)
        
        # Buscar CALMA
        calma_col = buscar_columna_por_patron(df_viento_filtrado, ['frecuencia calma', 'calma'])
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
                title=f"Rosa de Vientos - {estacion_seleccionada} ({mes_viento_seleccionado})",
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
            st.info("ℹ️ No hay datos de viento válidos para este mes/estación.")
    else:
        st.info(f"ℹ️ No se encontraron datos de viento para {estacion_seleccionada} - {mes_viento_seleccionado}.")
else:
    if variable_viento:
        st.info("ℹ️ Selecciona un mes en la barra lateral para ver la rosa de vientos.")
    else:
        st.info("ℹ️ No hay datos de viento disponibles en el archivo.")

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
