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

# --- LOGO ---
try:
    st.sidebar.image("LogoIIPAC.jpg", use_container_width=True)
except:
    st.sidebar.warning("Logo no encontrado. Sube 'LogoIIPAC.jpg'.")

st.title("📊 Dashboard Datos Clima IIPAC")
st.caption("Fuente: Servicio Meteorológico Nacional (SMN)")

# --- FUNCIONES AUXILIARES ---
def normalizar(nombre):
    nombre = nombre.strip()
    nombre = re.sub(r'[áÁ]', 'a', nombre)
    nombre = re.sub(r'[éÉ]', 'e', nombre)
    nombre = re.sub(r'[íÍ]', 'i', nombre)
    nombre = re.sub(r'[óÓ]', 'o', nombre)
    nombre = re.sub(r'[úÚ]', 'u', nombre)
    nombre = re.sub(r'[ñÑ]', 'n', nombre)
    return re.sub(r'[^a-z0-9]', '', nombre.lower())

def buscar_columna(df, patrones):
    col_norm = {normalizar(col): col for col in df.columns}
    for p in patrones:
        p_norm = normalizar(p)
        for cn, cr in col_norm.items():
            if p_norm in cn or cn in p_norm:
                return cr
    return None

# --- CARGA DE DATOS ---
@st.cache_data
def load_data():
    file_id = "1-XZ-eYH7iyxJpaWerNaBERy_joHr4lLJ"
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    output = "datos_clima_smn.csv"
    
    if not os.path.exists(output):
        with st.spinner("Descargando datos..."):
            gdown.download(url, output, quiet=False)
    
    # Detectar separador
    with open(output, 'r', encoding='utf-8') as f:
        first = f.readline()
        sep = '|' if '|' in first else (';' if ';' in first else ',')
    
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
            st.error(f"❌ No se encontró columna para '{key}'. Columnas: {list(df_raw.columns)}")
            st.stop()
    
    # --- MESES ---
    meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    meses_encontrados = [m for m in meses if m in df_raw.columns]
    
    # --- COLUMNAS DE VIENTO (detección mejorada) ---
    # Buscar todas las columnas que contengan "frecuencia" o "velocidad"
    wind_cols = []
    for col in df_raw.columns:
        col_lower = col.lower()
        if 'frecuencia' in col_lower or 'velocidad promedio' in col_lower or 'calma' in col_lower:
            wind_cols.append(col)
    
    # Si no se encontraron, buscar por "frec" o "veloc"
    if not wind_cols:
        for col in df_raw.columns:
            if 'frec' in col.lower() or 'veloc' in col.lower():
                wind_cols.append(col)
    
    # --- ID_VARS ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- DATOS DE VIENTO (se mantiene sin transformar) ---
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
    
    # Limpiar nombres de texto
    for col in ['estacion', 'variable', 'estadistico']:
        nombre_real = col_names[col]
        df_long[nombre_real] = df_long[nombre_real].str.strip()
        df_wind[nombre_real] = df_wind[nombre_real].str.strip()
    
    return df_long, df_wind, wind_cols, col_names, meses

# --- CARGAR ---
df_long, df_wind, wind_cols, col_names, meses = load_data()
if df_long.empty:
    st.stop()

# --- FILTROS ---
st.sidebar.header("🔍 Filtros")

col_estacion = col_names['estacion']
col_variable = col_names['variable']
col_estadistico = col_names['estadistico']

estaciones = sorted(df_long[col_estacion].unique())
estacion_seleccionada = st.sidebar.selectbox("📍 Estación", estaciones)

df_estacion = df_long[df_long[col_estacion] == estacion_seleccionada]
df_valid = df_estacion.dropna(subset=['Valor'])

if df_valid.empty:
    st.warning(f"⚠️ No hay datos para {estacion_seleccionada}. Elige otra.")
    st.stop()

variables = sorted(df_valid[col_variable].unique())
variable_seleccionada = st.sidebar.selectbox("📊 Variable", variables)

df_var = df_valid[df_valid[col_variable] == variable_seleccionada]
estadisticos = sorted(df_var[col_estadistico].unique())
estadistico_seleccionado = st.sidebar.selectbox("📈 Estadístico", estadisticos)

# --- SUPERPOSICIÓN: multiselect ---
st.sidebar.markdown("---")
st.sidebar.subheader("🔄 Superposición de Estadísticos")
superponer = st.sidebar.checkbox("Activar superposición")
estadisticos_superponer = []
if superponer and len(estadisticos) > 1:
    estadisticos_superponer = st.sidebar.multiselect(
        "Selecciona estadísticos a superponer",
        options=estadisticos,
        default=estadisticos[:2]  # Por defecto los dos primeros
    )

# --- DATOS DE UBICACIÓN ---
df_wind_estacion = df_wind[df_wind[col_estacion] == estacion_seleccionada]
if not df_wind_estacion.empty:
    lat = df_wind_estacion[col_names['latitud']].iloc[0]
    lon = df_wind_estacion[col_names['longitud']].iloc[0]
    altura = df_wind_estacion[col_names['altura']].iloc[0]
    periodo = df_wind_estacion[col_names['periodo']].iloc[0]
else:
    lat = lon = altura = periodo = None

# --- GRÁFICO PRINCIPAL ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader(f"📈 Variación Mensual de {variable_seleccionada}")
    
    if superponer and estadisticos_superponer:
        fig = go.Figure()
        for est in estadisticos_superponer:
            df_temp = df_var[df_var[col_estadistico] == est].sort_values('Mes_num')
            df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
            df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
            df_completo = df_completo.merge(df_temp[['Mes_num', 'Valor']], on='Mes_num', how='left')
            fig.add_trace(go.Scatter(
                x=df_completo['Mes'],
                y=df_completo['Valor'],
                mode='lines+markers',
                name=est,
                line=dict(width=2)
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

# --- ROSA DE LOS VIENTOS (con selección de período) ---
st.subheader("🌬️ Rosa de los Vientos")

# Detectar si hay datos de viento
if not df_wind_estacion.empty and wind_cols:
    # --- IDENTIFICAR PERÍODOS DISPONIBLES (ANUAL y meses) ---
    periodos_disponibles = ['ANUAL']
    # Buscar columnas que tengan sufijos de mes (ej: "Frecuencia N Ene")
    # Para simplificar, asumimos que las columnas anuales NO tienen sufijo de mes
    # y las mensuales SÍ lo tienen.
    for mes in meses:
        # Verificar si existe al menos una columna con ese mes como sufijo
        if any(mes in col for col in wind_cols):
            periodos_disponibles.append(mes)
    
    # Si solo hay ANUAL, no mostrar selector de mes
    if len(periodos_disponibles) == 1:
        periodo_seleccionado = 'ANUAL'
    else:
        periodo_seleccionado = st.selectbox(
            "Selecciona el período para la rosa de vientos",
            options=periodos_disponibles,
            index=0
        )
    
    # --- EXTRAER DATOS PARA EL PERÍODO SELECCIONADO ---
    direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    frecuencias = []
    velocidades = []
    
    for dir in direcciones:
        # Construir nombres de columnas según el período
        if periodo_seleccionado == 'ANUAL':
            freq_col_name = f'Frecuencia {dir}'
            vel_col_name = f'Velocidad promedio {dir}'
        else:
            freq_col_name = f'Frecuencia {dir} {periodo_seleccionado}'
            vel_col_name = f'Velocidad promedio {dir} {periodo_seleccionado}'
        
        # Buscar la columna exacta (puede tener variaciones)
        freq_col = buscar_columna(df_wind_estacion, [freq_col_name, f'frec {dir} {periodo_seleccionado}'])
        vel_col = buscar_columna(df_wind_estacion, [vel_col_name, f'vel {dir} {periodo_seleccionado}'])
        
        if freq_col and vel_col:
            freq_val = df_wind_estacion[freq_col].iloc[0]
            vel_val = df_wind_estacion[vel_col].iloc[0]
            frecuencias.append(freq_val if pd.notna(freq_val) else 0)
            velocidades.append(vel_val if pd.notna(vel_val) else 0)
        else:
            frecuencias.append(0)
            velocidades.append(0)
    
    # Buscar CALMA
    if periodo_seleccionado == 'ANUAL':
        calma_col_name = 'Frecuencia CALMA'
    else:
        calma_col_name = f'Frecuencia CALMA {periodo_seleccionado}'
    calma_col = buscar_columna(df_wind_estacion, [calma_col_name, 'calma'])
    calma_val = df_wind_estacion[calma_col].iloc[0] if calma_col else np.nan
    
    # --- GENERAR ROSA DE VIENTOS ---
    if any(f > 0 for f in frecuencias):
        df_wind_plot = pd.DataFrame({
            'Dirección': direcciones,
            'Frecuencia (‰)': frecuencias,
            'Velocidad (km/h)': velocidades
        })
        
        # Crear gráfico polar con barras
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
        
        # Mostrar CALMA si existe
        if pd.notna(calma_val) and calma_val > 0:
            st.metric("Frecuencia CALMA (‰)", f"{calma_val:.1f}")
    else:
        st.info(f"ℹ️ No hay datos de viento para el período {periodo_seleccionado} en esta estación.")
else:
    st.info("ℹ️ Esta estación no tiene datos de viento en el archivo.")

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
    st.info("No hay datos adicionales para esta variable.")

# --- TABLA DE DATOS ---
with st.expander("📋 Ver todos los datos de la variable seleccionada"):
    if 'df_completo' in locals():
        st.dataframe(df_completo)
    else:
        st.dataframe(df_final[['Mes', 'Valor']] if not df_final.empty else pd.DataFrame())
