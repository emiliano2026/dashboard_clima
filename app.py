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

def extraer_direcciones(df_row):
    """Extrae frecuencias y velocidades para las 8 direcciones desde una fila de viento."""
    direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    frecuencias = []
    velocidades = []
    
    for dir in direcciones:
        # Buscar columna de frecuencia y velocidad para esta dirección
        freq_col = buscar_columna(df_row, [f'frecuencia {dir}', f'frec {dir}'])
        vel_col = buscar_columna(df_row, [f'velocidad promedio {dir}', f'vel {dir}'])
        
        if freq_col and vel_col:
            freq_val = df_row[freq_col].iloc[0] if freq_col in df_row else np.nan
            vel_val = df_row[vel_col].iloc[0] if vel_col in df_row else np.nan
            frecuencias.append(freq_val if pd.notna(freq_val) else 0)
            velocidades.append(vel_val if pd.notna(vel_val) else 0)
        else:
            frecuencias.append(0)
            velocidades.append(0)
    
    # Buscar CALMA
    calma_col = buscar_columna(df_row, ['frecuencia calma', 'calma'])
    calma_val = df_row[calma_col].iloc[0] if calma_col and calma_col in df_row else np.nan
    
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
    
    # --- COLUMNAS DE VIENTO (búsqueda mejorada con regex) ---
    wind_cols = []
    for col in df_raw.columns:
        # Buscar columnas que contengan "Frecuencia" o "Velocidad promedio" (con o sin paréntesis)
        if re.search(r'frecuencia|velocidad\s*promedio|calma', col, re.IGNORECASE):
            wind_cols.append(col)
    
    # Si no se encontraron, intentar con búsqueda más flexible
    if not wind_cols:
        for col in df_raw.columns:
            if 'frec' in col.lower() or 'veloc' in col.lower():
                wind_cols.append(col)
    
    # --- ID_VARS ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- DATOS DE VIENTO (se mantienen en formato ancho) ---
    df_wind = df_raw[id_vars + wind_cols].copy()
    # Reemplazar 'S/D', 'S/P' por NaN y convertir a numérico (maneja comas como decimal)
    for col in wind_cols:
        df_wind[col] = df_wind[col].replace(['S/D', 'S/P', ''], np.nan)
        # Si hay comas, convertirlas a puntos (ya que decimal=',' no siempre funciona)
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
    # Mostrar solo los que son relevantes (excluir "Número de años considerados" etc.)
    opciones_superposicion = [e for e in estadisticos if 'años' not in e.lower() and 'diario' not in e.lower()]
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
                connectgaps=True  # <--- UNE LOS PUNTOS AUNQUE HAYA NaN
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
        # Conectar puntos con línea
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
        st.write(f"Altura: {altura} msnm")  # <--- SOLO "msnm"
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

# --- SELECTOR DE PERÍODO (en el área principal, no en la barra lateral) ---
if variable_viento:
    # Obtener todos los períodos disponibles para la variable de viento en esta estación
    df_viento_estacion = df_wind[
        (df_wind[col_estacion] == estacion_seleccionada) &
        (df_wind[col_variable] == variable_viento)
    ]
    if not df_viento_estacion.empty:
        periodos_disponibles = sorted(df_viento_estacion[col_estadistico].unique())
        # Filtrar solo los que son meses o Anual
        periodos_filtrados = []
        for p in periodos_disponibles:
            if p in meses or p == 'Anual':
                periodos_filtrados.append(p)
        # Si no hay "Anual", agregarlo si existe algún mes
        if 'Anual' not in periodos_filtrados and any(p in meses for p in periodos_disponibles):
            periodos_filtrados.append('Anual')
        
        if periodos_filtrados:
            # Ordenar: primero meses en orden, luego Anual
            orden = {m: i for i, m in enumerate(meses)}
            orden['Anual'] = 12
            periodos_filtrados.sort(key=lambda x: orden.get(x, 99))
            
            mes_viento_seleccionado = st.selectbox(
                "Selecciona el período para la rosa de vientos",
                periodos_filtrados,
                key="mes_viento"
            )
        else:
            st.info("ℹ️ No hay períodos disponibles para la rosa de vientos.")
            mes_viento_seleccionado = None
    else:
        st.info(f"ℹ️ No hay datos de viento para la estación {estacion_seleccionada}.")
        mes_viento_seleccionado = None
else:
    st.info("ℹ️ No se encontró la variable de viento en el archivo.")
    mes_viento_seleccionado = None

# --- GENERAR ROSA DE VIENTOS ---
if variable_viento and mes_viento_seleccionado:
    # Filtrar fila de viento para la estación, variable y período seleccionado
    df_viento_filtrado = df_wind[
        (df_wind[col_estacion] == estacion_seleccionada) &
        (df_wind[col_variable] == variable_viento) &
        (df_wind[col_estadistico] == mes_viento_seleccionado)
    ]
    
    if not df_viento_filtrado.empty:
        # Extraer direcciones usando la función auxiliar
        direcciones, frecuencias, velocidades, calma_val = extraer_direcciones(df_viento_filtrado)
        
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
            st.info("ℹ️ No hay datos de viento válidos para este período.")
    else:
        st.info(f"ℹ️ No se encontraron datos para {estacion_seleccionada} - {mes_viento_seleccionado}.")
else:
    if not variable_viento:
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

# --- OPCIONAL: DEPURACIÓN (mostrar columnas detectadas) ---
with st.expander("🔧 Información de depuración (solo para revisión)"):
    st.write("**Columnas de viento detectadas:**", wind_cols)
    if variable_viento:
        st.write("**Variable de viento encontrada:**", variable_viento)
        st.write("**Períodos disponibles para viento en esta estación:**", 
                 sorted(df_wind_estacion[col_estadistico].unique()))
    else:
        st.write("**No se detectó variable de viento.**")
