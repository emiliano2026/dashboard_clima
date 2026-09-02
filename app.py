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

def convertir_decimal(valor):
    """Convierte string con coma decimal a float, maneja S/D y S/P"""
    if isinstance(valor, (int, float)):
        return valor
    if isinstance(valor, str):
        valor = valor.strip()
        if valor in ['S/D', 'S/P', '']:
            return np.nan
        # Reemplazar coma por punto
        valor = valor.replace(',', '.')
        try:
            return float(valor)
        except:
            return np.nan
    return np.nan

# --- CARGA DE DATOS ---
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
    
    # --- ID_VARS ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- CONVERTIR TODAS LAS COLUMNAS DE MESES Y VIENTO A NUMÉRICO ---
    # Identificar columnas de viento (todas las que no son id_vars y no son meses)
    columnas_a_convertir = [col for col in df_raw.columns if col not in id_vars]
    for col in columnas_a_convertir:
        df_raw[col] = df_raw[col].apply(convertir_decimal)
    
    # --- DATOS DE VIENTO (formato ancho) ---
    # Identificar columnas de viento (las que contienen 'frecuencia' o 'velocidad')
    wind_cols = []
    for col in df_raw.columns:
        col_lower = col.lower()
        if 'frecuencia' in col_lower or 'velocidad' in col_lower or 'calma' in col_lower:
            wind_cols.append(col)
    
    # Crear DataFrame de viento con los metadatos
    df_wind = df_raw[id_vars + wind_cols].copy()
    
    # --- DATOS MENSUALES (formato largo) ---
    df_long = pd.melt(
        df_raw,
        id_vars=id_vars,
        value_vars=meses_encontrados,
        var_name='Mes',
        value_name='Valor'
    )
    # El valor ya fue convertido, pero reforzamos por si acaso
    df_long['Valor'] = df_long['Valor'].apply(convertir_decimal)
    
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
    st.warning(f"⚠️ No hay datos para la estación **{estacion_seleccionada}**. Elige otra.")
    st.stop()

# --- Excluir "Número de años considerados" de la lista de variables ---
variables_todas = sorted(df_valid[col_variable].unique())
# Identificar variable de viento para excluir también
variable_viento = None
for var in variables_todas:
    if 'frecuencia' in var.lower() and 'velocidad' in var.lower():
        variable_viento = var
        break

variables = [v for v in variables_todas if v != variable_viento]
if not variables:
    st.warning("No hay variables disponibles.")
    st.stop()

variable_seleccionada = st.sidebar.selectbox("📊 Variable", variables)

df_var = df_valid[df_valid[col_variable] == variable_seleccionada]
# --- EXCLUIR "Número de años considerados" de los estadísticos ---
estadisticos_todos = sorted(df_var[col_estadistico].unique())
estadisticos = [e for e in estadisticos_todos if e != 'Número de años considerados']
if not estadisticos:
    st.warning("No hay estadísticos disponibles (solo 'Número de años considerados').")
    st.stop()

estadistico_seleccionado = st.sidebar.selectbox("📈 Estadístico", estadisticos)

# --- SUPERPOSICIÓN ---
superponer = st.sidebar.checkbox("🔄 Superponer estadísticos")
estadisticos_seleccionados = []
if superponer:
    estadisticos_seleccionados = st.sidebar.multiselect(
        "Selecciona 2 o 3 estadísticos para comparar",
        options=estadisticos,
        default=estadisticos[:2] if len(estadisticos) >= 2 else estadisticos
    )

# --- UBICACIÓN ---
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
    
    if superponer and len(estadisticos_seleccionados) > 1:
        fig = go.Figure()
        for est in estadisticos_seleccionados:
            df_temp = df_var[df_var[col_estadistico] == est].sort_values('Mes_num')
            df_completo = pd.DataFrame({'Mes_num': range(1, 13)})
            df_completo['Mes'] = df_completo['Mes_num'].map({i+1: m for i, m in enumerate(meses)})
            df_completo = df_completo.merge(df_temp[['Mes_num', 'Valor']], on='Mes_num', how='left')
            df_completo['Valor'] = df_completo['Valor'].apply(convertir_decimal)
            fig.add_trace(go.Scatter(
                x=df_completo['Mes'],
                y=df_completo['Valor'],
                mode='lines+markers',
                name=est,
                line=dict(width=2),
                connectgaps=True
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
        df_completo['Valor'] = df_completo['Valor'].apply(convertir_decimal)
        
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

# --- ROSA DE LOS VIENTOS (VERSIÓN CON DOS TRAZAS) ---
st.subheader("🌬️ Rosa de los Vientos")

# Selector: Anual o mes específico
periodo_viento = st.selectbox(
    "Selecciona el período para la rosa de vientos",
    options=["Anual"] + meses,
    index=0
)

if not df_wind_estacion.empty and wind_cols:
    # Buscar la fila que contiene la variable de viento para esta estación
    df_wind_variable = df_wind_estacion
    if variable_viento:
        df_wind_variable = df_wind_estacion[df_wind_estacion[col_variable] == variable_viento]
    
    if not df_wind_variable.empty:
        # Direcciones
        direcciones = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        frecuencias = []
        velocidades = []
        
        for dir in direcciones:
            # Buscar columna de frecuencia y velocidad para esta dirección y período
            if periodo_viento == "Anual":
                freq_col = buscar_columna(df_wind_variable, [f'frecuencia {dir}', f'frec {dir}'])
                vel_col = buscar_columna(df_wind_variable, [f'velocidad promedio {dir}', f'vel {dir}'])
            else:
                # Para mes específico: "Frecuencia N Ene"
                freq_col = buscar_columna(df_wind_variable, [f'frecuencia {dir} {periodo_viento}', f'frec {dir} {periodo_viento}'])
                vel_col = buscar_columna(df_wind_variable, [f'velocidad promedio {dir} {periodo_viento}', f'vel {dir} {periodo_viento}'])
            
            if freq_col and vel_col:
                freq_val = df_wind_variable[freq_col].iloc[0]
                vel_val = df_wind_variable[vel_col].iloc[0]
                frecuencias.append(freq_val if pd.notna(freq_val) else 0)
                velocidades.append(vel_val if pd.notna(vel_val) else 0)
            else:
                frecuencias.append(0)
                velocidades.append(0)
        
        # CALMA
        if periodo_viento == "Anual":
            calma_col = buscar_columna(df_wind_variable, ['frecuencia calma', 'calma'])
        else:
            calma_col = buscar_columna(df_wind_variable, [f'frecuencia calma {periodo_viento}', f'calma {periodo_viento}'])
        calma_val = df_wind_variable[calma_col].iloc[0] if calma_col else np.nan
        
        if any(f > 0 for f in frecuencias):
            # Crear DataFrame
            df_wind_plot = pd.DataFrame({
                'Dirección': direcciones,
                'Frecuencia (‰)': frecuencias,
                'Velocidad (km/h)': velocidades
            })
            
            # --- GRÁFICO CON DOS TRAZAS ---
            fig_wind = go.Figure()
            
            # Barras para frecuencia
            fig_wind.add_trace(go.Barpolar(
                r=df_wind_plot['Frecuencia (‰)'],
                theta=df_wind_plot['Dirección'],
                name='Frecuencia (‰)',
                marker_color='lightskyblue',
                marker_line_color='darkblue',
                marker_line_width=1,
                opacity=0.7
            ))
            
            # Escalar velocidad para que sea visible
            max_freq = max(frecuencias) if max(frecuencias) > 0 else 1
            max_vel = max(velocidades) if max(velocidades) > 0 else 1
            escala = max_freq / max_vel if max_vel > 0 else 1
            velocidades_escaladas = [v * escala for v in velocidades]
            
            # Línea y marcadores para velocidad
            fig_wind.add_trace(go.Scatterpolar(
                r=velocidades_escaladas,
                theta=df_wind_plot['Dirección'],
                mode='markers+lines',
                name='Velocidad (km/h)',
                marker=dict(size=8, color='red', symbol='star'),
                line=dict(color='red', width=2, dash='dash')
            ))
            
            # Layout
            fig_wind.update_layout(
                polar=dict(
                    radialaxis=dict(
                        title='Frecuencia (‰)',
                        tickfont=dict(size=10),
                        range=[0, max_freq * 1.1]
                    ),
                    angularaxis=dict(
                        direction="clockwise",
                        period=8,
                        tickfont=dict(size=12)
                    )
                ),
                title=f"Rosa de Vientos - {estacion_seleccionada} ({periodo_viento})",
                template='plotly_white',
                legend=dict(x=0.9, y=1.1, orientation='h')
            )
            
            # Anotación CALMA
            if pd.notna(calma_val) and calma_val > 0:
                fig_wind.add_annotation(
                    text=f"CALMA: {calma_val:.1f} ‰",
                    xref="paper", yref="paper",
                    x=0.5, y=-0.15,
                    showarrow=False,
                    font=dict(size=12, color='darkgreen')
                )
            
            st.plotly_chart(fig_wind, use_container_width=True)
        else:
            st.info(f"ℹ️ No hay datos de viento para {periodo_viento} en esta estación.")
    else:
        st.info("ℹ️ No se encontró la variable de viento para esta estación.")
else:
    st.info("ℹ️ Esta estación no tiene datos de viento en el archivo.")

# --- OTROS DATOS (excluyendo "Número de años considerados") ---
st.subheader("📊 Otros Datos")

# Estadísticos puntuales: excluir los que son promedios y "Número de años considerados"
excluir_puntuales = ['Número de años considerados', 'Promedio', 'Máximo valor promedio', 'Mínimo valor promedio']
estadisticos_puntuales = [e for e in estadisticos if e not in excluir_puntuales]

kpi_data = {}
for est in estadisticos_puntuales:
    df_kpi = df_var[df_var[col_estadistico] == est]
    if not df_kpi.empty:
        valores = df_kpi['Valor'].dropna()
        if not valores.empty:
            kpi_data[est] = valores.iloc[0]

if kpi_data:
    cols = st.columns(len(kpi_data))
    for i, (nombre, valor) in enumerate(kpi_data.items()):
        with cols[i]:
            display = nombre.replace('valor', '').strip()
            st.metric(label=display if display else nombre, value=f"{valor:.2f}" if isinstance(valor, (int, float)) else str(valor))
else:
    st.info("No hay datos puntuales adicionales para esta variable.")

# --- TABLA DE DATOS ---
with st.expander("📋 Ver todos los datos de la variable seleccionada"):
    if 'df_completo' in locals():
        st.dataframe(df_completo)
    else:
        st.dataframe(df_final[['Mes', 'Valor']] if not df_final.empty else pd.DataFrame())
