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
    st.sidebar.warning("Logo no encontrado. Sube el archivo 'LogoIIPAC.jpg' al repositorio.")

st.title("📊 Dashboard Datos Clima IIPAC")
st.caption("Fuente: Servicio Meteorológico Nacional (SMN)")

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

def buscar_columna(df, patrones, exacto=False):
    """
    Busca una columna que coincida con alguno de los patrones.
    Si exacto=True, busca coincidencia exacta después de normalizar.
    Si exacto=False, busca que el patrón esté contenido.
    """
    columnas_norm = {normalizar_nombre(col): col for col in df.columns}
    for patron in patrones:
        patron_norm = normalizar_nombre(patron)
        if exacto:
            if patron_norm in columnas_norm:
                return columnas_norm[patron_norm]
        else:
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
    
    # --- COLUMNAS DE VIENTO (búsqueda mejorada) ---
    # Buscar columnas que contengan "Frecuencia", "Velocidad promedio" o "CALMA"
    wind_cols = []
    keywords = ['frecuencia', 'velocidad promedio', 'calma']
    for col in df_raw.columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in keywords):
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
    
    # --- DATOS DE VIENTO ---
    # IMPORTANTE: Filtrar solo la fila con estadístico "Anual" o similar
    # Buscar el nombre de la columna de estadístico
    col_estadistico = col_names['estadistico']
    # Buscar filas que contengan "Anual" en el estadístico (puede ser "Anual", "anual", etc.)
    df_wind_raw = df_raw[id_vars + wind_cols].copy()
    # Filtrar por estadístico que contenga "anual" o "Anual"
    anual_mask = df_wind_raw[col_estadistico].str.contains('anual', case=False, na=False)
    if anual_mask.any():
        df_wind_filtered = df_wind_raw[anual_mask].copy()
    else:
        # Si no hay "Anual", tomar la primera fila (pero advertir)
        st.warning("No se encontró la fila con estadístico 'Anual' para los datos de viento. Se tomará la primera fila disponible.")
        df_wind_filtered = df_wind_raw.iloc[[0]].copy()
    
    # Reemplazar 'S/D', 'S/P' por NaN
    for col in wind_cols:
        df_wind_filtered[col] = pd.to_numeric(df_wind_filtered[col].replace(['S/D', 'S/P', ''], np.nan), errors='coerce')
    
    # Guardar el DataFrame filtrado de viento
    df_wind = df_wind_filtered
    
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

# --- SUPERPOSICIÓN: multiselect de estadísticos ---
# Mostrar checkbox para activar superposición
superponer = st.sidebar.checkbox("🔄 Superponer estadísticos")
if superponer:
    # Selección múltiple de estadísticos (mínimo 2, máximo 4)
    estadisticos_seleccionados = st.sidebar.multiselect(
        "Elige los estadísticos a superponer",
        options=estadisticos,
        default=estadisticos[:2] if len(estadisticos) >= 2 else estadisticos
    )
else:
    # Selección única (para el gráfico principal)
    estadistico_seleccionado = st.sidebar.selectbox("📈 Estadístico", estadisticos)

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
    
    if superponer and len(estadisticos_seleccionados) >= 2:
        # --- SUPERPOSICIÓN: mostrar solo los estadísticos seleccionados ---
        fig = go.Figure()
        for est in estadisticos_seleccionados:
            df_temp = df_var[df_var[col_estadistico] == est].sort_values('Mes_num')
            # Completar meses faltantes con NaN
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
            title=f"{variable_seleccionada} - Comparativa de estadísticos seleccionados",
            xaxis_title="Mes",
            yaxis_title="Valor",
            template='plotly_white',
            legend_title="Estadístico"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    else:
        # --- GRÁFICO INDIVIDUAL (un solo estadístico) ---
        if not superponer:
            est_actual = estadistico_seleccionado
        else:
            # Si superponer está activado pero no hay suficientes seleccionados, usar el primero
            est_actual = estadisticos_seleccionados[0] if estadisticos_seleccionados else estadisticos[0]
        
        df_final = df_var[df_var[col_estadistico] == est_actual].sort_values('Mes_num')
        # Completar meses faltantes
        df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
        df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
        df_completo = df_completo.merge(df_final[['Mes_num', 'Valor']], on='Mes_num', how='left')
        
        fig_line = px.line(
            df_completo,
            x='Mes',
            y='Valor',
            markers=True,
            title=f"{variable_seleccionada} - {est_actual}",
            labels={'Mes': 'Mes', 'Valor': 'Valor'},
            template='plotly_white',
        )
        # Media anual (solo si hay al menos 2 valores)
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

# --- 5. ROSA DE LOS VIENTOS (MEJORADA) ---
st.subheader("🌬️ Rosa de los Vientos")

# Verificar que existan columnas de viento
if wind_cols and not df_wind_estacion.empty:
    # Extraer direcciones y buscar columnas correspondientes
    direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    frecuencias = []
    velocidades = []
    
    for dir in direcciones:
        # Buscar columna de frecuencia y velocidad para esta dirección
        # Usamos búsqueda flexible (contenga 'frecuencia' + dir, y 'velocidad promedio' + dir)
        freq_col = buscar_columna(df_wind_estacion, [f'frecuencia {dir}', f'frec {dir}', f'{dir} frecuencia'])
        vel_col = buscar_columna(df_wind_estacion, [f'velocidad promedio {dir}', f'vel {dir}', f'{dir} velocidad'])
        
        if freq_col and vel_col:
            freq_val = df_wind_estacion[freq_col].iloc[0]
            vel_val = df_wind_estacion[vel_col].iloc[0]
            frecuencias.append(freq_val if pd.notna(freq_val) else 0)
            velocidades.append(vel_val if pd.notna(vel_val) else 0)
        else:
            # Si no se encuentra, buscar cualquier columna que tenga 'frecuencia' y dir como parte
            # (a veces los nombres pueden ser "Frecuencia N (‰)")
            for col in df_wind_estacion.columns:
                if 'frec' in col.lower() and dir.lower() in col.lower():
                    freq_col = col
                    break
            for col in df_wind_estacion.columns:
                if 'veloc' in col.lower() and dir.lower() in col.lower():
                    vel_col = col
                    break
            if freq_col and vel_col:
                freq_val = df_wind_estacion[freq_col].iloc[0]
                vel_val = df_wind_estacion[vel_col].iloc[0]
                frecuencias.append(freq_val if pd.notna(freq_val) else 0)
                velocidades.append(vel_val if pd.notna(vel_val) else 0)
            else:
                frecuencias.append(0)
                velocidades.append(0)
    
    # Buscar CALMA
    calma_col = buscar_columna(df_wind_estacion, ['frecuencia calma', 'calma'])
    calma_val = df_wind_estacion[calma_col].iloc[0] if calma_col else np.nan
    
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
        st.info("ℹ️ No se encontraron datos de viento válidos para esta estación.")
        # Mostrar columnas de viento detectadas para depuración
        with st.expander("🔍 Ver columnas de viento detectadas"):
            st.write("Columnas de viento en el archivo:", wind_cols)
            st.write("Datos de viento para esta estación:", df_wind_estacion[wind_cols].head())
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

# --- 7. TABLA DE DATOS ---
with st.expander("📋 Ver todos los datos de la variable seleccionada"):
    if 'df_completo' in locals():
        st.dataframe(df_completo)
    elif 'df_final' in locals():
        st.dataframe(df_final[['Mes', 'Valor']] if not df_final.empty else pd.DataFrame())
