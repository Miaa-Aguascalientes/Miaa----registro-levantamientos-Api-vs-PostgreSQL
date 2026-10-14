# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
# ==========================================
from datetime import datetime, timedelta
import math
import time
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from sqlalchemy import create_engine, text
import streamlit as st

ZONA_MEXICO = ZoneInfo("America/Mexico_City")

st.set_page_config(
    page_title="Sistema Scada - Levantamientos MIAA",
    page_icon="https://www.miaa.mx/favicon.ico",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        /* Ocultar elementos predeterminados de la interfaz de Streamlit */
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* BLOQUEAR LA BARRA LATERAL PARA QUE NUNCA SE PUEDA OCULTAR O COLAPSAR */
        [data-testid="stSidebar"] {
            min-width: 280px !important;
            max-width: 320px !important;
            transform: none !important;
        }
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        button[kind="header"] {
            display: none !important;
        }
        
        /* EVITAR COMPLETAMENTE LA OPACIDAD O EFECTO GRIS CUANDO STREAMLIT SE EJECUTA O ACTUALIZA */
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], .main, .block-container {
            opacity: 1 !important;
            filter: none !important;
            pointer-events: auto !important;
        }
        [data-testid="stStatusWidget"] {
            display: none !important;
        }
        
        /* Eliminar el espacio superior por defecto de la página */
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 0rem !important;
        }
        
        header hr, .stApp > header + div hr, [data-testid="stHeader"] hr, hr {
            display: none !important;
        }
        
        .metric-card {
            background-color: #1e293b;
            border: 1px solid #334155;
            padding: 15px;
            border-radius: 8px;
            display: flex;
            align-items: center;
        }
        .metric-content {
            display: flex;
            flex-direction: column;
        }
        .metric-title {
            font-size: 12px;
            color: #94a3b8;
        }
        .metric-value {
            font-size: 20px;
            font-weight: bold;
            color: #f8fafc;
        }
        
        /* Consola con altura exacta alineada */
        .terminal-box {
            background-color: #0b0f19;
            border: 1px solid #22c55e;
            color: #22c55e;
            font-family: 'Courier New', Courier, monospace;
            padding: 15px;
            border-radius: 6px;
            height: 505px;
            overflow-y: scroll;
            font-size: 13px;
            line-height: 1.4;
        }
        
        [data-testid="stVerticalBlock"] [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #0e1322 !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
            height: 567px !important;
            overflow-y: auto !important;
            padding: 15px !important;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 2. GESTIÓN DE LOGS (CONSOLA - HORA MÉXICO)
# ==========================================
if "logs" not in st.session_state:
  st.session_state.logs = [
      f"[{datetime.now(ZONA_MEXICO).strftime('%H:%M:%S')}] Sistema inicializado"
      " correctamente (Módulo de Levantamientos). Esperando ciclo..."
  ]


def agregar_log(mensaje):
  timestamp = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
  st.session_state.logs.insert(0, f"[{timestamp}] {mensaje}")
  if len(st.session_state.logs) > 300:
    st.session_state.logs.pop()


# ==========================================
# 3. CONEXIONES Y CONSULTAS (SQL Y API)
# ==========================================
BASE_URL = "https://prelec.miaa.mx"
URL_LOGIN_CORRECTA = "/auth/login"
URL_LEVANTAMIENTOS = (
    "https://prelec.miaa.mx/msvc-tecnica/medidores/levantamientos"
)


def obtener_motor_postgres():
  pg = st.secrets["postgres"]
  connection_string = f"postgresql+psycopg2://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['database']}"
  return create_engine(connection_string)


def obtener_total_registros_levantamientos_db():
  try:
    engine_pg = obtener_motor_postgres()
    with engine_pg.connect() as conn:
      result = conn.execute(text('SELECT COUNT(*) FROM "Usuarios"."levantamientos"'))
      return result.scalar()
  except Exception as e:
    agregar_log(f"⚠️ [AVISO DB] No se pudo obtener el conteo de registros: {e}")
    return 0


@st.cache_data(ttl=300)
def obtener_token_api():
  usuario = st.secrets["api"]["usuario"]
  password = st.secrets["api"]["password"]
  url_login = BASE_URL + URL_LOGIN_CORRECTA

  for _ in range(3):
    try:
      res_login = requests.post(
          url_login,
          json={"username": usuario, "password": password},
          headers={"Content-Type": "application/json"},
          timeout=15,
      )
      if res_login.status_code == 200:
        data_login = res_login.json()
        token = data_login.get("token") or data_login.get("access_token")
        if token:
          return token
      time.sleep(2)
    except Exception:
      time.sleep(2)
  return None


def convertir_latlon_a_utm_wkt(lat, lon):
  try:
    if pd.isna(lat) or pd.isna(lon):
      return None
    lat_f = float(lat)
    lon_f = float(lon)
    if lat_f == 0.0 or lon_f == 0.0:
      return None

    try:
      from pyproj import Transformer

      transformer = Transformer.from_crs("EPSG:4326", "EPSG:32613", always_xy=True)
      x, y = transformer.transform(lon_f, lat_f)
      return f"POINT({x:.4f} {y:.4f})"
    except ImportError:
      a = 6378137.0
      eccSquared = 0.00669438
      k0 = 0.9996

      latRad = math.radians(lat_f)
      lonRad = math.radians(lon_f)

      zoneNumber = 13
      lonOrigin = (zoneNumber - 1) * 6 - 180 + 3
      lonOriginRad = math.radians(lonOrigin)

      e2 = eccSquared / (1 - eccSquared)
      N = a / math.sqrt(1 - eccSquared * math.sin(latRad) ** 2)
      T = math.tan(latRad) ** 2
      C = e2 * math.cos(latRad) ** 2
      A = math.cos(latRad) * (lonRad - lonOriginRad)

      M = a * (
          (
              1
              - eccSquared / 4
              - 3 * eccSquared**2 / 64
              - 5 * eccSquared**3 / 256
          )
          * latRad
          - (
              3 * eccSquared / 8
              + 3 * eccSquared**2 / 32
              + 45 * eccSquared**3 / 1024
          )
          * math.sin(2 * latRad)
          + (15 * eccSquared**2 / 256 + 45 * eccSquared**3 / 1024)
          * math.sin(4 * latRad)
          - (35 * eccSquared**3 / 3072) * math.sin(6 * latRad)
      )

      x = (
          k0
          * N
          * (
              A
              + (1 - T + C) * A**3 / 6
              + (5 - 18 * T + T**2 + 72 * C - 58 * e2) * A**5 / 120
          )
          + 500000.0
      )
      y = (
          k0
          * (
              M
              + N
              * math.tan(latRad)
              * (
                  A**2 / 2
                  + (5 - T + 9 * C + 4 * C**2) * A**4 / 24
                  + (61 - 58 * T + T**2 + 600 * C - 330 * e2) * A**6 / 720
              )
          )
      )

      return f"POINT({x:.4f} {y:.4f})"
  except Exception:
    return None


@st.cache_data(ttl=300)
def consultar_api_levantamientos_todos(size_lote=200):
  token = obtener_token_api()
  if not token:
    agregar_log(
        "❌ [API ERROR] No se pudo autenticar para consultar Levantamientos."
    )
    return pd.DataFrame()

  todos_los_registros = []
  page = 0
  max_paginas = 200

  while page < max_paginas:
    params = [
        ("page", page),
        ("size", size_lote),
        ("sort", "serie,asc"),
        ("sort", "predio,asc"),
    ]

    try:
      res = requests.get(
          URL_LEVANTAMIENTOS,
          headers={
              "Content-Type": "application/json",
              "Authorization": f"Bearer {token}",
          },
          params=params,
          timeout=30,
      )

      if res.status_code != 200:
        break

      data = res.json()
      lote_df = pd.DataFrame()

      if isinstance(data, list):
        lote_df = pd.DataFrame(data)
      elif isinstance(data, dict):
        for key in ["content", "data", "result", "items", "levantamientos"]:
          if key in data and isinstance(data[key], list):
            lote_df = pd.DataFrame(data[key])
            break
        if lote_df.empty:
          lote_df = pd.DataFrame([data])

      if lote_df.empty:
        break

      todos_los_registros.append(lote_df)
      if len(lote_df) < size_lote:
        break

      page += 1
    except Exception:
      break

  if not todos_los_registros:
    return pd.DataFrame()

  df_final = pd.concat(todos_los_registros, ignore_index=True)

  if not df_final.empty:
    col_api_predio = next(
        (
            c
            for c in ["predio", "predioViv", "predio_viv", "numeroPredio"]
            if c in df_final.columns
        ),
        None,
    )
    col_api_unidad = next(
        (c for c in ["unidad", "unidadViv", "unidad_viv"] if c in df_final.columns),
        None,
    )

    def construir_predio_viv(row):
      if not col_api_predio:
        return ""
      p = row[col_api_predio]
      if pd.isna(p) or str(p).strip().lower() in ["none", "nan", ""]:
        return ""
      p_str = str(p).strip()
      u = (
          row[col_api_unidad]
          if col_api_unidad and pd.notna(row[col_api_unidad])
          else 0
      )
      u_str = str(u).strip()
      if u_str.lower() in ["none", "nan", ""]:
        u_str = "0"
      return f"{p_str}-{u_str}"

    df_final["Predio_Viv"] = df_final.apply(construir_predio_viv, axis=1)

    col_lat = next(
        (
            c
            for c in ["latitud", "lat", "latitude", "y", "Latitud"]
            if c in df_final.columns
        ),
        None,
    )
    col_lon = next(
        (
            c
            for c in ["longitud", "lon", "lng", "longitude", "x", "Longitud"]
            if c in df_final.columns
        ),
        None,
    )

    if col_lat and col_lon:
      df_final["Latitud"] = pd.to_numeric(df_final[col_lat], errors="coerce")
      df_final["Longitud"] = pd.to_numeric(df_final[col_lon], errors="coerce")
      df_final["geom"] = df_final.apply(
          lambda r: convertir_latlon_a_utm_wkt(r["Latitud"], r["Longitud"]),
          axis=1,
      )
    else:
      df_final["Latitud"] = None
      df_final["Longitud"] = None
      df_final["geom"] = None

    if "id" in df_final.columns and "medidorId" not in df_final.columns:
      df_final["medidorId"] = df_final["id"]

    columnas_a_remover = [
        "uuid",
        "predio",
        "unidad",
        "usuarioId",
        "id",
        "_Ultima_actualizacion",
    ]
    df_final = df_final.drop(columns=columnas_a_remover, errors="ignore")

    df_final.insert(0, "fid", range(1, len(df_final) + 1))
    df_final["_Ultima_actualizacion"] = datetime.now(ZONA_MEXICO)

  return df_final


# ==========================================
# 4. FUNCIÓN DE SINCRONIZACIÓN (INSERCIÓN PURA SIN ACTUALIZAR EXISTENTES)
# ==========================================
def ejecutar_sincronizacion_levantamientos(
    barra_progreso_placeholder=None,
    texto_estado_placeholder=None,
    consola_placeholder=None,
):
  def actualizar_progreso(valor_pct, mensaje):
    agregar_log(mensaje)
    if consola_placeholder is not None:
      logs_html = "<br>".join(st.session_state.logs)
      consola_placeholder.markdown(
          f'<div class="terminal-box">{logs_html}</div>', unsafe_allow_html=True
      )
    if barra_progreso_placeholder is not None:
      barra_progreso_placeholder.progress(
          valor_pct, text=f"Sincronizando: {int(valor_pct * 100)}% - {mensaje}"
      )
    if texto_estado_placeholder is not None:
      texto_estado_placeholder.markdown(
          f"🔄 **{mensaje}** ({int(valor_pct * 100)}%)"
      )

  actualizar_progreso(
      0.30, "[PASO 1/2] Descargando registros de la API y calculando UTM..."
  )
  df_lev = consultar_api_levantamientos_todos(size_lote=200)

  if df_lev.empty:
    actualizar_progreso(
        1.0, "[ERROR] No se pudo obtener respuesta o datos del endpoint."
    )
    return False

  total_descargados = len(df_lev)
  actualizar_progreso(
      0.60,
      f"[PASO 2/2] {total_descargados:,} registros listos. Insertando solo los nuevos (sin tocar los existentes)...",
  )

  try:
    engine_pg = obtener_motor_postgres()

    # 1. Cargamos los datos a una tabla temporal en PostgreSQL
    temp_table_name = "tmp_levantamientos_sync"
    df_lev.to_sql(
        temp_table_name,
        con=engine_pg,
        schema="Usuarios",
        if_exists="replace",
        index=False,
        chunksize=5000,
    )

    # 2. Obtenemos las columnas de la tabla temporal excepto 'fid' para calcularlo dinámicamente
    with engine_pg.connect() as conn:
      cols_result = conn.execute(
          text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'Usuarios' 
                  AND table_name = '{temp_table_name}'
                  AND column_name != 'fid'
            """)
      )
      columnas = [row[0] for row in cols_result]

    cols_str = ", ".join([f'"{c}"' for c in columnas])
    cols_t_str = ", ".join([f't."{c}"' for c in columnas])

    # 3. Inserción estricta: Solo inserta si la serie NO existe previamente en la tabla principal.
    # Los registros que ya existan se ignoran por completo (no se actualizan, no se tocan).
    query_insert_nuevos = text(f"""
        INSERT INTO "Usuarios"."levantamientos" ("fid", {cols_str})
        SELECT 
            (SELECT COALESCE(MAX(fid), 0) FROM "Usuarios"."levantamientos") + ROW_NUMBER() OVER () AS fid,
            {cols_t_str}
        FROM "Usuarios"."{temp_table_name}" t
        WHERE NOT EXISTS (
            SELECT 1 FROM "Usuarios"."levantamientos" l 
            WHERE l.serie = t.serie
        );
    """)

    with engine_pg.begin() as conn:
      conn.execute(query_insert_nuevos)
      conn.execute(text(f'DROP TABLE IF EXISTS "Usuarios"."{temp_table_name}"'))

    actualizar_progreso(
        1.0,
        f"🎉 [CICLO EXITOSO] Sincronización completada."
        f" Se evaluaron {total_descargados:,} registros de la API. Los existentes se respetaron intactos y solo se agregaron los nuevos.",
    )
    return True
  except Exception as ex:
    actualizar_progreso(
        1.0, f"[ERROR CRÍTICO] Falló la sincronización en base de datos: {ex}"
    )
    return False


# ==========================================
# 5. TEMPORIZADOR Y RELOJ (HORA MÉXICO)
# ==========================================
def calcular_siguiente_tiempo_reloj(minutos_intervalo):
  ahora = datetime.now(ZONA_MEXICO)
  minuto_actual = ahora.minute
  segundo_actual = ahora.second
  residuo = minuto_actual % minutos_intervalo
  minutos_faltantes = (
      minutos_intervalo - residuo
      if residuo != 0
      else (0 if segundo_actual == 0 else minutos_intervalo)
  )
  if minutos_faltantes == 0 and segundo_actual > 0:
    minutos_faltantes = minutos_intervalo
  siguiente_tiempo = (
      ahora.replace(second=0, microsecond=0)
      + timedelta(minutes=minutos_faltantes)
  )
  total_segundos_hasta_siguiente = (
      siguiente_tiempo - ahora
  ).total_seconds()
  return siguiente_tiempo, int(total_segundos_hasta_siguiente)


if "is_running" not in st.session_state:
  st.session_state.is_running = False
if "next_run_time" not in st.session_state:
  st.session_state.next_run_time = None
if "intervalo_minutos_sel" not in st.session_state:
  st.session_state.intervalo_minutos_sel = 5

# ==========================================
# 6. CARGA DE DATOS PARA INDICADORES Y VISTAS
# ==========================================
total_registros_db = obtener_total_registros_levantamientos_db()
df_lev_preview = consultar_api_levantamientos_todos(size_lote=200)

total_serie_api_lev = 0
if not df_lev_preview.empty:
  if "serie" in df_lev_preview.columns:
    ts = df_lev_preview["serie"].dropna().astype(str).str.strip()
    total_serie_api_lev = ts[
        ~ts.str.lower().isin(["", "none", "nan", "null"])
    ].count()

# ==========================================
# 7. BARRA LATERAL IZQUIERDA (SIDEBAR)
# ==========================================
with st.sidebar:
  st.image(
      "https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg",
      use_container_width=True,
  )
  st.markdown("### 🚰 Panel Levantamientos MIAA")
  st.markdown("---")
  st.markdown("#### ⚙ Configuración")

  opciones_intervalo = {
      "Cada 1 minuto": 1,
      "Cada 5 minutos": 5,
      "Cada 10 minutos": 10,
      "Cada 15 minutos": 15,
      "Cada 30 minutos": 30,
      "Cada hora": 60,
  }
  intervalo_sel = st.selectbox(
      "Intervalo de sincronización", list(opciones_intervalo.keys())
  )
  minutos_seleccionados = opciones_intervalo[intervalo_sel]

  col_s1, col_s2 = st.columns(2)
  with col_s1:
    btn_iniciar = st.button("INICIAR", type="primary", use_container_width=True)
  with col_s2:
    btn_parar = st.button("PARAR", type="secondary", use_container_width=True)

  if btn_iniciar:
    st.session_state.is_running = True
    st.session_state.intervalo_minutos_sel = minutos_seleccionados
    sig_tiempo, _ = calcular_siguiente_tiempo_reloj(minutos_seleccionados)
    st.session_state.next_run_time = sig_tiempo
    agregar_log(
        f"▶ Temporizador activado. Próxima ejecución a las"
        f" {sig_tiempo.strftime('%H:%M:%S')} (Hora Centro de México)."
    )
    st.rerun()

  if btn_parar:
    st.session_state.is_running = False
    st.session_state.next_run_time = None
    agregar_log("⏹ Temporizador detenido manualmente.")
    st.rerun()

  st.markdown("---")
  if st.button("🔄 Actualizar Métricas de BD", use_container_width=True):
    st.rerun()

# ==========================================
# 8. INTERFAZ PRINCIPAL
# ==========================================
st.markdown(
    """
    <div style="text-align: center; margin-top: -20px; margin-bottom: 10px;">
        <h2 style="color: #f8fafc; font-weight: 700;">MIAA - Módulo de Levantamientos y Sincronización</h2>
    </div>
    """,
    unsafe_allow_html=True,
)

col_ind1, col_ind2, col_ind3 = st.columns(3)
with col_ind1:
  st.markdown(
      f"""
        <div class="metric-card">
            <div style="font-size: 28px; margin-right: 15px;">🎯</div>
            <div class="metric-content">
                <div class="metric-title">TOTAL LEVANTAMIENTOS API</div>
                <div class="metric-value">{len(df_lev_preview):,}</div>
            </div>
        </div>
    """,
      unsafe_allow_html=True,
  )
with col_ind2:
  st.markdown(
      f"""
        <div class="metric-card">
            <div style="font-size: 28px; margin-right: 15px;">📊</div>
            <div class="metric-content">
                <div class="metric-title">TOTAL REGISTROS TABLA LEVANTAMIENTOS (DB)</div>
                <div class="metric-value">{total_registros_db:,}</div>
            </div>
        </div>
    """,
      unsafe_allow_html=True,
  )
with col_ind3:
  st.markdown(
      f"""
        <div class="metric-card">
            <div style="font-size: 28px; margin-right: 15px;">✅</div>
            <div class="metric-content">
                <div class="metric-title">SERIES VÁLIDAS EN API</div>
                <div class="metric-value">{total_serie_api_lev:,}</div>
            </div>
        </div>
    """,
      unsafe_allow_html=True,
  )

st.markdown(
    "<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True
)

st.markdown("#### 🔄 Estado y Progreso del Sistema")
estado_ejecucion_placeholder = st.empty()
barra_progreso_placeholder = st.empty()

col_consola, col_info = st.columns([1, 1], gap="medium")
with col_consola:
  st.markdown("#### 🖥️ Consola de Registros (Tabla Levantamientos)")
  consola_placeholder = st.empty()
  logs_html = "<br>".join(st.session_state.logs)
  consola_placeholder.markdown(
      f'<div class="terminal-box">{logs_html}</div>', unsafe_allow_html=True
  )

if st.session_state.is_running and st.session_state.next_run_time:
  if st.session_state.next_run_time is None:
    sig_tiempo, _ = calcular_siguiente_tiempo_reloj(
        st.session_state.intervalo_minutos_sel
    )
    st.session_state.next_run_time = sig_tiempo

  ahora = datetime.now(ZONA_MEXICO)
  if ahora >= st.session_state.next_run_time:
    ejecutar_sincronizacion_levantamientos(
        barra_progreso_placeholder,
        estado_ejecucion_placeholder,
        consola_placeholder,
    )
    sig_tiempo, _ = calcular_siguiente_tiempo_reloj(
        st.session_state.intervalo_minutos_sel
    )
    st.session_state.next_run_time = sig_tiempo
    st.rerun()
  else:
    segundos_totales_intervalo = st.session_state.intervalo_minutos_sel * 60
    segundos_restantes = max(
        0,
        int(
            (
                st.session_state.next_run_time
                - datetime.now(ZONA_MEXICO)
            ).total_seconds()
        ),
    )
    progreso_espera = max(
        0.0,
        min(
            1.0,
            1.0 - (segundos_restantes / float(segundos_totales_intervalo)),
        ),
    )
    mins_r = segundos_restantes // 60
    secs_r = segundos_restantes % 60
    tiempo_formateado = f"{mins_r:02d}:{secs_r:02d}"

    estado_ejecucion_placeholder.markdown(
        f"⏳ **Temporizador activo.** Próxima ejecución a las"
        f" **{st.session_state.next_run_time.strftime('%H:%M:%S')}** (Restan"
        f" **{tiempo_formateado}**)"
    )
    barra_progreso_placeholder.progress(
        progreso_espera,
        text=f"Tiempo en espera — Restan {tiempo_formateado}",
    )
    time.sleep(1)
    st.rerun()
else:
  estado_ejecucion_placeholder.markdown(
      "⏸️ **Temporizador inactivo.** Presiona **INICIAR** en la barra lateral."
  )
  barra_progreso_placeholder.progress(0, text="Listo para iniciar...")

st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

with col_info:
  st.markdown("#### ℹ️ Información del Módulo")
  with st.container(border=True):
    st.markdown(
        """
            <h4 style="margin-top: 0; color: #f8fafc; font-size: 18px;">
                Gestión Exclusiva de la Tabla <code>Usuarios.levantamientos</code>
            </h4>
            <p style="font-size: 13px; color: #94a3b8; margin-bottom: 10px;">
                Este programa apunta directamente al esquema <b>Usuarios</b> y la tabla <b>levantamientos</b> en PostgreSQL con geometría nativa PostGIS <code>geometry(POINT, 32613)</code> y carga ultra rápida sin demoras.
            </p>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

# ==========================================
# 9. PESTAÑAS DE LA APLICACIÓN
# ==========================================
tab1, tab2 = st.tabs([
    "🚰 Tabla PostgreSQL: Usuarios.levantamientos",
    "🔍 Explorador API Levantamientos",
])

with tab1:
  st.markdown(
      "<p style='font-size:16px; font-weight:bold; margin-bottom:10px;'>Registros"
      " almacenados en la tabla PostgreSQL: <code>Usuarios.levantamientos</code></p>",
      unsafe_allow_html=True,
  )
  if total_registros_db > 0:
    try:
      engine_pg = obtener_motor_postgres()
      t2_filas = 50
      t2_total_pags = max(
          1,
          (total_registros_db // t2_filas)
          + (1 if total_registros_db % t2_filas > 0 else 0),
      )
      t2_pag = st.selectbox(
          "Seleccionar página", range(1, t2_total_pags + 1), key="select_pag_t2"
      )
      df_t2 = pd.read_sql(
          text(
              'SELECT * FROM "Usuarios"."levantamientos" LIMIT :lim OFFSET :off'
          ),
          con=engine_pg,
          params={"lim": t2_filas, "off": (t2_pag - 1) * t2_filas},
      )
      if "_Ultima_actualizacion" in df_t2.columns:
        df_t2_vista = df_t2.drop(columns=["_Ultima_actualizacion"])
      else:
        df_t2_vista = df_t2

      st.dataframe(df_t2_vista, use_container_width=True, height=450)
    except Exception as e:
      st.error(f"Error al cargar datos de PostgreSQL: {e}")
  else:
    st.warning("No hay registros en la tabla `Usuarios.levantamientos`.")

with tab2:
  st.subheader(
      "🔍 Explorador Completo de TODOS los Registros (Con geom UTM y fid)"
  )
  st.markdown(
      "Visualiza absolutamente todos los registros existentes en el servidor"
      " con su geometría UTM calculada en el campo `geom`."
  )

  input_busqueda_serie = st.text_input(
      "Buscar número de serie de medidor (Filtro en tiempo real)",
      value="",
      key="input_busq_levantamientos_full",
  )

  df_levantamientos_full = consultar_api_levantamientos_todos(size_lote=200)

  if df_levantamientos_full.empty:
    st.warning("No se encontraron registros en el endpoint.")
  else:
    if input_busqueda_serie.strip() != "":
      termino = input_busqueda_serie.strip().lower()
      if "serie" in df_levantamientos_full.columns:
        df_levantamientos_full = df_levantamientos_full[
            df_levantamientos_full["serie"]
            .astype(str)
            .str.lower()
            .str.contains(termino, na=False)
        ]

    st.success(
        f"¡Se cargaron y filtraron un total de"
        f" **{len(df_levantamientos_full):,}** registros con su columna"
        " `geom`!"
    )

    # ==========================================
    # 10. ANÁLISIS Y VALIDACIÓN DE SERIES DUPLICADAS
    # ==========================================
    if "serie" in df_levantamientos_full.columns:
      series_limpias = (
          df_levantamientos_full["serie"].dropna().astype(str).str.strip()
      )
      series_limpias = series_limpias[
          ~series_limpias.str.lower().isin(["", "none", "nan", "null"])
      ]
      conteo_series = series_limpias.value_counts()
      series_duplicadas = conteo_series[conteo_series > 1]

      if not series_duplicadas.empty:
        st.error(
            f"⚠️ **¡Atención! Se detectaron {len(series_duplicadas)}"
            " números de serie de medidor duplicados.**"
        )
        df_dup_detalle = df_levantamientos_full[
            df_levantamientos_full["serie"]
            .astype(str)
            .str.strip()
            .isin(series_duplicadas.index)
        ].sort_values(by="serie")

        with st.expander(
            "🔎 Ver Detalle de Registros con Series Duplicadas", expanded=False
        ):
          if "_Ultima_actualizacion" in df_dup_detalle.columns:
            df_dup_vista = df_dup_detalle.drop(
                columns=["_Ultima_actualizacion"]
            )
          else:
            df_dup_vista = df_dup_detalle
          st.dataframe(df_dup_vista, use_container_width=True, height=250)
      else:
        st.success(
            "✅ **Validación exitosa:** No existen números de serie de medidor"
            " repetidos en los registros mostrados."
        )

    if "_Ultima_actualizacion" in df_levantamientos_full.columns:
      df_vista_full = df_levantamientos_full.drop(
          columns=["_Ultima_actualizacion"]
      )
    else:
      df_vista_full = df_levantamientos_full

    st.dataframe(df_vista_full, use_container_width=True, height=500)

    with st.container(border=True):
      st.markdown(
          "#### ⚙ Sincronización Manual hacia la Tabla"
          " `Usuarios.levantamientos`"
      )
      st.markdown(
          "Ejecuta la sincronización inmediata para guardar estos datos en"
          " tu base de datos."
      )
      if st.button(
          "Sincronizar a la Tabla 'Usuarios.levantamientos'",
          key="btn_sinc_levantamientos_manual",
          type="primary",
      ):
        with st.spinner("Sincronizando datos en base de datos..."):
          exito = ejecutar_sincronizacion_levantamientos()
          if exito:
            st.success("¡Sincronización completada con éxito!")
            st.rerun()
          else:
            st.error("Ocurrió un error durante la sincronización.")
