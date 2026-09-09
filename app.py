# --- 1. CARGA DE DATOS ---
@st.cache_data
def load_data():
    # ID del archivo en Google Drive (actualizado)
    file_id = "1-WQeKO7A5_iLcS8QNIjt_iFDp2VgWEPv"
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    output = "datos_clima_smn.csv"
    
    if not os.path.exists(output):
        with st.spinner("Descargando datos desde Google Drive..."):
            gdown.download(url, output, quiet=False)
    
    # --- DETECTAR CODIFICACIÓN AUTOMÁTICAMENTE ---
    with open(output, 'rb') as f:
        raw_data = f.read()
        resultado = chardet.detect(raw_data)
        encoding = resultado['encoding'] if resultado else 'utf-8'
        # Opcional: mostrar la codificación detectada (útil para depuración)
        # st.info(f"📄 Codificación detectada: {encoding}")
    
    # Leer el archivo con la codificación detectada
    with open(output, 'r', encoding=encoding) as f:
        first_line = f.readline()
        sep = '|' if '|' in first_line else (';' if ';' in first_line else ',')
    
    # Leer el CSV con la misma codificación
    df_raw = pd.read_csv(output, delimiter=sep, skipinitialspace=True, 
                         encoding=encoding, dtype=str, keep_default_na=False)
    df_raw.columns = df_raw.columns.str.strip()
    
    # --- MAPEO DE COLUMNAS ---
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
    if 'Anual' not in df_raw.columns:
        df_raw['Anual'] = ''
    periodos = meses_encontrados + ['Anual']
    
    # --- ID_VARS ---
    id_vars = [col_names['provincia'], col_names['estacion'], col_names['latitud'], 
               col_names['longitud'], col_names['altura'], col_names['periodo'],
               col_names['variable'], col_names['estadistico']]
    
    # --- CONVERTIR TODAS LAS COLUMNAS NUMÉRICAS (meses y Anual) ---
    columnas_a_convertir = [col for col in df_raw.columns if col in meses or col == 'Anual']
    df_raw = convertir_todas_numericas(df_raw, columnas_a_convertir)
    
    # --- DETECTAR VARIABLE DE VIENTO ---
    pattern_viento = re.compile(r'frecuencia.*velocidad', re.IGNORECASE)
    mask_viento = df_raw[col_names['variable']].str.contains(pattern_viento, na=False)
    if not mask_viento.any():
        pattern_viento2 = re.compile(r'frecuencia.*‰', re.IGNORECASE)
        mask_viento = df_raw[col_names['variable']].str.contains(pattern_viento2, na=False)
    
    df_viento_raw = df_raw[mask_viento].copy()
    df_no_viento = df_raw[~mask_viento].copy()
    
    # --- DATOS DE VIENTO ---
    wind_cols = [col for col in df_viento_raw.columns if col not in id_vars]
    df_wind = df_viento_raw[id_vars + wind_cols].copy()
    df_wind = convertir_todas_numericas(df_wind, wind_cols)
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
    
    for col in ['estacion', 'variable', 'estadistico']:
        nombre_real = col_names[col]
        df_long[nombre_real] = df_long[nombre_real].str.strip()
    
    variable_viento_encontrada = None
    if not df_viento_raw.empty:
        variable_viento_encontrada = df_viento_raw[col_names['variable']].iloc[0]
    
    return df_long, df_wind, wind_cols, col_names, meses, periodos, variable_viento_encontrada
