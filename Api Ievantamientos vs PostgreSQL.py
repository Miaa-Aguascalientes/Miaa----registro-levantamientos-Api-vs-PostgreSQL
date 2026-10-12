# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
# ==========================================
from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from sqlalchemy import create_engine, text
import streamlit as st

ZONA_MEXICO = ZoneInfo("America/Mexico_City")

st.set_page_config(
    page_title="Sistema Scada",
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
      " correctamente. Esperando ciclo de ejecución..."
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
URL_INSTALACIONES = "https://prelec.miaa.mx/msvc-tecnica/medidores/instalaciones"
URL_LEVANTAMIENTOS = (
    "https://prelec.miaa.mx/msvc-tecnica/medidores/levantamientos"
)


def obtener_motor_postgres():
  pg = st.secrets["postgres"]
  connection_string = f"postgresql+psycopg2://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['database']}"
  return create_engine(connection_string)


@st.cache_data(ttl=600)
def obtener_total_registros():
  try:
    engine_pg = obtener_motor_postgres()
    with engine_pg.connect() as conn:
      result = conn.execute(
          text('SELECT COUNT(*) FROM "Usuarios"."usuarios_miaa_conmedidor"')
      )
      return result.scalar()
  except Exception as e:
    agregar_log(f"⚠️ [AVISO DB] No se pudo obtener el conteo de registros: {e}")
    return 0


@st.cache_data(ttl=60)
def obtener_total_etapa_1():
  try:
    engine_pg = obtener_motor_postgres()
    with engine_pg.connect() as conn:
      result = conn.execute(
          text(
              'SELECT COUNT(*) FROM "Usuarios"."usuarios_miaa_conmedidor"'
              " WHERE etapa = '1'"
          )
      )
      return result.scalar() or 0
  except Exception as e:
    agregar_log(f"⚠️ [AVISO DB] No se pudo obtener el conteo de etapa 1: {e}")
    return 0


@st.cache_data(ttl=60)
def obtener_total_etapa_2():
  try:
    engine_pg = obtener_motor_postgres()
    with engine_pg.connect() as conn:
      result = conn.execute(
          text(
              'SELECT COUNT(*) FROM "Usuarios"."usuarios_miaa_conmedidor"'
              " WHERE etapa = '2'"
          )
      )
      return result.scalar() or 0
  except Exception as e:
    agregar_log(f"⚠️ [AVISO DB] No se pudo obtener el conteo de etapa 2: {e}")
    return 0


@st.cache_data(ttl=60)
def cargar_pagina_usuarios_db(limit=50, offset=0):
  try:
    engine_pg = obtener_motor_postgres()
    query = text(
        'SELECT * FROM "Usuarios"."usuarios_miaa_conmedidor" LIMIT :lim OFFSET'
        " :off"
    )
    return pd.read_sql(
        query, con=engine_pg, params={"lim": limit, "off": offset}
    )
  except Exception as e:
    agregar_log(f"❌ [ERROR DB] Error al cargar página de PostgreSQL: {e}")
    return pd.DataFrame()


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


@st.cache_data(ttl=300)
def cargar_datos_api():
  """Conecta con la API de instalaciones de MIAA con reintentos automáticos."""
  token = obtener_token_api()
  if not token:
    st.error("Error de Autenticación o la API no responde tras varios intentos.")
    return pd.DataFrame()

  max_intentos = 3
  data = None
  es_exitoso = False

  for intento in range(1, max_intentos + 1):
    try:
      res_inst = requests.get(
          URL_INSTALACIONES,
          headers={
              "Content-Type": "application/json",
              "Authorization": f"Bearer {token}",
          },
          timeout=45,
      )

      if res_inst.status_code == 503:
        agregar_log(
            f"⚠️ [AVISO API] Intento {intento}/{max_intentos}: El servicio de"
            " técnica devolvió 503. Reintentando..."
        )
        time.sleep(3)
        continue

      if res_inst.status_code != 200:
        return pd.DataFrame()

      data = res_inst.json()
      es_exitoso = True
      break
    except requests.exceptions.RequestException:
      time.sleep(3)

  if not es_exitoso or data is None:
    return pd.DataFrame()

  df = pd.DataFrame()
  if isinstance(data, list):
    df = pd.DataFrame(data)
  elif isinstance(data, dict):
    for key in ["data", "result", "items", "instalaciones"]:
      if key in data and isinstance(data[key], list):
        df = pd.DataFrame(data[key])
        break
    if df.empty:
      df = pd.DataFrame([data])

  if not df.empty:
    if "numeroCliente" in df.columns:
      df["Cliente"] = df["numeroCliente"]
    elif "numero_cliente" in df.columns:
      df["Cliente"] = df["numero_cliente"]
    elif "numCliente" in df.columns:
      df["Cliente"] = df["numCliente"]

    col_api_predio = next(
        (
            c
            for c in ["predio", "predioViv", "predio_viv", "numeroPredio"]
            if c in df.columns
        ),
        None,
    )
    col_api_unidad = next(
        (c for c in ["unidad", "unidadViv", "unidad_viv"] if c in df.columns),
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

    df["Predio_Viv"] = df.apply(construir_predio_viv, axis=1)

  return df


def consultar_api_levantamientos(busqueda=""):
  """Consulta el endpoint específico de levantamientos con parámetros de paginación y búsqueda por serie."""
  token = obtener_token_api()
  if not token:
    return pd.DataFrame()

  params = {
      "page": 0,
      "size": 50,
      "busqueda": busqueda,
      "sort": ["serie,asc", "predio,asc"],
  }

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
    if res.status_code == 200:
      data = res.json()
      df = pd.DataFrame()
      if isinstance(data, list):
        df = pd.DataFrame(data)
      elif isinstance(data, dict):
        for key in ["content", "data", "result", "items", "levantamientos"]:
          if key in data and isinstance(data[key], list):
            df = pd.DataFrame(data[key])
            break
        if df.empty:
          df = pd.DataFrame([data])
      return df
  except Exception as e:
    agregar_log(f"❌ [API LEVANTAMIENTOS] Error en consulta: {e}")

  return pd.DataFrame()


# ==========================================
# 4. FUNCIÓN DE CRUCE ULTRA RÁPIDO (STAGING + SQL)
# ==========================================
def ejecutar_sincronizacion_automatica(
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
          valor_pct,
          text=f"Progreso de ejecución: {int(valor_pct * 100)}% - {mensaje}",
      )
    if texto_estado_placeholder is not None:
      texto_estado_placeholder.markdown(
          f"🔄 **{mensaje}** ({int(valor_pct * 100)}%)"
      )
    time.sleep(0.05)

  actualizar_progreso(
      0.15,
      "[PASO 1/4] Conectando con API de instalaciones para descargar registros...",
  )
  df_filtrado = cargar_datos_api()

  if df_filtrado.empty:
    actualizar_progreso(
        1.0, "[ERROR] No se pudo obtener respuesta o datos válidos de la API."
    )
    return False

  total_descargados = len(df_filtrado)
  actualizar_progreso(
      0.35,
      f"[PASO 2/4] API OK. {total_descargados:,} registros descargados."
      " Preparando tabla temporal en PostgreSQL...",
  )

  try:
    engine_pg = obtener_motor_postgres()
    df_staging = df_filtrado.copy()
    if "Predio_Viv" not in df_staging.columns:
      return False

    df_staging["Predio_Viv_clean"] = (
        df_staging["Predio_Viv"].astype(str).str.strip()
    )

    actualizar_progreso(
        0.55,
        "[PASO 3/4] Cargando datos de la API a la tabla temporal (Staging)"
        " en PostgreSQL...",
    )
    df_staging.to_sql(
        "_staging_api_instalaciones",
        con=engine_pg,
        schema="Usuarios",
        if_exists="replace",
        index=False,
        chunksize=5000,
    )

    actualizar_progreso(
        0.75,
        "[PASO 4/4] Ejecutando actualización masiva (UPDATE FROM JOIN) en"
        " PostgreSQL...",
    )
    query_update_masivo = text("""
            UPDATE "Usuarios"."usuarios_miaa_conmedidor" AS u
            SET 
                "_Serie" = COALESCE(s.serie, u."_Serie"),
                "_Colonia" = COALESCE(s.colonia, u."_Colonia"),
                "_Domicilio" = COALESCE(s.domicilio, u."_Domicilio"),
                "_Instalador" = COALESCE(s."usuarioNombre", u."_Instalador"),
                "_Tipo_instalador" = CASE 
                    WHEN TRIM(CAST(s."usuarioExterno" AS TEXT)) IN ('true', 'True', '1', 'YES', 'yes', 'S', 's', 'TRUE') THEN 'Externo'
                    ELSE 'MIAA'
                END,
                "_Lectura_actual" = CASE 
                    WHEN s."lecturaActual" IS NOT NULL AND TRIM(CAST(s."lecturaActual" AS TEXT)) NOT IN ('', 'none', 'nan', 'null') 
                    THEN CAST(s."lecturaActual" AS DOUBLE PRECISION)
                    ELSE u."_Lectura_actual"
                END,
                "_Fecha_registro" = CASE 
                    WHEN s."fechaRegistro" IS NOT NULL AND TRIM(CAST(s."fechaRegistro" AS TEXT)) NOT IN ('', 'none', 'nan', 'null') 
                    THEN CAST(s."fechaRegistro" AS TIMESTAMP WITH TIME ZONE)
                    ELSE u."_Fecha_registro"
                END,
                "_Fecha_instalacion" = CASE 
                    WHEN s."fechaInstalacion" IS NOT NULL AND TRIM(CAST(s."fechaInstalacion" AS TEXT)) NOT IN ('', 'none', 'nan', 'null') 
                    THEN CAST(s."fechaInstalacion" AS TIMESTAMP WITH TIME ZONE)
                    ELSE u."_Fecha_instalacion"
                END,
                "_Ultima_actualizacion" = :tiempo_actual,
                etapa = '2'
            FROM "Usuarios"."_staging_api_instalaciones" AS s
            WHERE TRIM(CAST(u."Predio_Viv" AS TEXT)) = s."Predio_Viv_clean"
              AND s."Predio_Viv_clean" NOT IN ('none', 'nan', '', 'nat', '0', 'null', 'None', 'NaN');
        """)

    with engine_pg.connect() as conn:
      result_up = conn.execute(
          query_update_masivo,
          {"tiempo_actual": datetime.now(ZONA_MEXICO)},
      )
      conn.commit()
      filas_actualizadas = (
          result_up.rowcount if hasattr(result_up, "rowcount") else 0
      )
      conn.execute(
          text('DROP TABLE IF EXISTS "Usuarios"."_staging_api_instalaciones"')
      )
      conn.commit()

    actualizar_progreso(
        1.0,
        f"🎉 [CICLO EXITOSO] Sincronización completada. Registros actualizados:"
        f" {filas_actualizadas:,}.",
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
total_registros_db = obtener_total_registros()
total_etapa_1_db = obtener_total_etapa_1()
total_etapa_2_db = obtener_total_etapa_2()
df_filtrado = cargar_datos_api()

total_serie_api = 0
if not df_filtrado.empty:
  if "serie" in df_filtrado.columns:
    ts = df_filtrado["serie"].dropna().astype(str).str.strip()
    total_serie_api = ts[
        ~ts.str.lower().isin(["", "none", "nan", "null"])
    ].count()

total_serie_pg_lleno = 0
try:
  engine_pg = obtener_motor_postgres()
  with engine_pg.connect() as conn:
    res_serie_pg = conn.execute(
        text("""
            SELECT COUNT(*) FROM "Usuarios"."usuarios_miaa_conmedidor" 
            WHERE "_Serie" IS NOT NULL 
              AND TRIM(CAST("_Serie" AS TEXT)) != '' 
              AND LOWER(TRIM(CAST("_Serie" AS TEXT))) NOT IN ('none', 'nan', 'null')
        """)
    )
    total_serie_pg_lleno = res_serie_pg.scalar()
except Exception:
  total_serie_pg_lleno = 0

# ==========================================
# 7. BARRA LATERAL IZQUIERDA (SIDEBAR)
# ==========================================
with st.sidebar:
  st.image(
      "https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg",
      use_container_width=True,
  )
  st.markdown("### 🚰 Panel de Control MIAA")
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
        f" {sig_tiempo.strftime('%H:%M:%S')}."
    )
    st.rerun()

  if btn_parar:
    st.session_state.is_running = False
    st.session_state.next_run_time = None
    agregar_log("⏹ Temporizador detenido manualmente.")
    st.rerun()

# ==========================================
# 8. INTERFAZ PRINCIPAL
# ==========================================
st.markdown(
    """
    <div style="text-align: center; margin-top: -20px; margin-bottom: 10px;">
        <h2 style="color: #f8fafc; font-weight: 700;">MIAA - Sistema de Registros e Instalaciones</h2>
    </div>
    """,
    unsafe_allow_html=True,
)

col_ind1, col_ind2, col_ind3, col_ind4 = st.columns(4)
with col_ind1:
  st.markdown(
      f"""
        <div class="metric-card">
            <div style="font-size: 28px; margin-right: 15px;">🎯</div>
            <div class="metric-content">
                <div class="metric-title">REGISTROS API CON SERIE</div>
                <div class="metric-value">{total_serie_api:,}</div>
            </div>
        </div>
    """,
      unsafe_allow_html=True,
  )
with col_ind2:
  st.markdown(
      f"""
        <div class="metric-card">
            <div style="font-size: 28px; margin-right: 15px;">✅</div>
            <div class="metric-content">
                <div class="metric-title">POSTGRESQL (_SERIE LLENO)</div>
                <div class="metric-value">{total_serie_pg_lleno:,}</div>
            </div>
        </div>
    """,
      unsafe_allow_html=True,
  )
with col_ind3:
  st.markdown(
      f"""
        <div class="metric-card">
            <div style="font-size: 28px; margin-right: 15px;">🔢</div>
            <div class="metric-content">
                <div class="metric-title">MEDIDORES ETAPA 1 / 2</div>
                <div class="metric-value" style="font-size: 16px; margin-top: 2px;">1: {total_etapa_1_db:,} | 2: {total_etapa_2_db:,}</div>
            </div>
        </div>
    """,
      unsafe_allow_html=True,
  )
with col_ind4:
  porcentaje_cobertura = (
      min(100.0, (total_serie_pg_lleno / total_serie_api) * 100)
      if total_serie_api > 0
      else 0.0
  )
  st.markdown(
      f"""
        <div class="metric-card">
            <div style="font-size: 28px; margin-right: 15px;">📊</div>
            <div class="metric-content">
                <div class="metric-title">SINCRONIZACIÓN</div>
                <div class="metric-value">{porcentaje_cobertura:.1f}%</div>
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

col_consola, col_limpieza = st.columns([1, 1], gap="medium")
with col_consola:
  st.markdown("#### 🖥️ Consola de Registros del Sistema")
  consola_placeholder = st.empty()
  logs_html = "<br>".join(st.session_state.logs)
  consola_placeholder.markdown(
      f'<div class="terminal-box">{logs_html}</div>', unsafe_allow_html=True
  )

if st.session_state.is_running and st.session_state.next_run_time:
  ahora = datetime.now(ZONA_MEXICO)
  if ahora >= st.session_state.next_run_time:
    ejecutar_sincronizacion_automatica(
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

with col_limpieza:
  st.markdown("#### &nbsp;")
  with st.container(border=True):
    st.markdown(
        """
            <h4 style="margin-top: 0; color: #f8fafc; font-size: 18px; display: flex; align-items: center;">
                🧹 <span style="margin-left: 8px;">Limpieza Masiva de Campos</span>
            </h4>
          """,
        unsafe_allow_html=True,
    )
    campos_disponibles = [
        "_Serie",
        "_Colonia",
        "_Domicilio",
        "_Instalador",
        "_Tipo_instalador",
        "_Lectura_actual",
        "_Fecha_registro",
        "_Fecha_instalacion",
        "_Ultima_actualizacion",
        "etapa",
    ]
    campos_a_limpiar_masivo = []
    cols_check = st.columns(2)
    for i, campo in enumerate(campos_disponibles):
      with cols_check[i % 2]:
        if st.checkbox(f"Vaciar {campo}", key=f"chk_masivo_{campo}"):
          campos_a_limpiar_masivo.append(campo)

    confirmar_masivo = st.checkbox(
        "⚠️ Confirmo vaciar masivamente estos campos en TODA la tabla",
        key="chk_confirmar_masivo",
    )
    if st.button(
        "Ejecutar Limpieza Masiva",
        type="primary",
        key="btn_ejecutar_masivo",
        use_container_width=True,
    ):
      if not campos_a_limpiar_masivo or not confirmar_masivo:
        st.error(
            "Selecciona al menos un campo y marca la casilla de confirmación."
        )
      else:
        try:
          engine_pg = obtener_motor_postgres()
          set_sql = ", ".join(
              [f'"{campo}" = NULL' for campo in campos_a_limpiar_masivo]
          )
          with engine_pg.connect() as conn_up:
            conn_up.execute(
                text(
                    f'UPDATE "Usuarios"."usuarios_miaa_conmedidor" SET {set_sql}'
                )
            )
            conn_up.commit()
          st.success("¡Campos vaciados correctamente en todos los registros!")
          st.rerun()
        except Exception as e:
          st.error(f"Error: {e}")

st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

# ==========================================
# 9. PESTAÑAS DE LA APLICACIÓN
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs([
    "🚰 Panel Principal",
    "📋 Tablas de Datos",
    "🛠️ Medidores Inteligentes",
    "🔍 API Levantamientos",
])

with tab1:
  st.markdown(
      "<p style='font-size:16px; font-weight:bold; margin-bottom:10px;'>Gestión"
      ' de Tabla PostgreSQL: usuarios_miaa_conmedidor</p>',
      unsafe_allow_html=True,
  )
  if total_registros_db > 0:
    c_m1, c_m2, c_m3 = st.columns(3)
    with c_m1:
      st.markdown(
          f"""
                <div class="metric-card">
                    <div class="metric-content">
                        <div class="metric-title">Total Registros (PG)</div>
                        <div class="metric-value">{total_registros_db:,}</div>
                    </div>
                </div>
            """,
          unsafe_allow_html=True,
      )
    with c_m2:
      st.markdown(
          """
                <div class="metric-card">
                    <div class="metric-content">
                        <div class="metric-title">Estado de Carga</div>
                        <div class="metric-value" style="font-size: 15px; margin-top: 5px;">Consola en Vivo (Staging SQL)</div>
                    </div>
                </div>
            """,
          unsafe_allow_html=True,
      )
    with c_m3:
      st.markdown(
          """
                <div class="metric-card">
                    <div class="metric-content">
                        <div class="metric-title">Rendimiento</div>
                        <div class="metric-value" style="font-size: 15px; margin-top: 5px;">Ultra Rápido (Servidor DB)</div>
                    </div>
                </div>
            """,
          unsafe_allow_html=True,
      )

with tab2:
  st.subheader(
      "🚰 Tabla 1: usuarios_miaa_conmedidor (PostgreSQL - Bloques SQL)"
  )
  if total_registros_db > 0:
    t2_filas = 50
    t2_total_pags = max(
        1,
        (total_registros_db // t2_filas)
        + (1 if total_registros_db % t2_filas > 0 else 0),
    )
    t2_pag = st.selectbox(
        "Seleccionar página", range(1, t2_total_pags + 1), key="select_pag_t2"
    )
    df_t2 = cargar_pagina_usuarios_db(limit=t2_filas, offset=(t2_pag - 1) * t2_filas)
    st.dataframe(df_t2, use_container_width=True, height=350)
  else:
    st.warning("No hay datos cargados de PostgreSQL.")

with tab3:
  st.subheader("🛠 Gestión de la tabla: medidores_inteligentes")
  with st.container(border=True):
    st.markdown("#### 🔢 Asignar Etapa 1 a todos los registros")
    if st.button(
        "Establecer etapa = 1 en toda la tabla",
        type="primary",
        key="btn_etapa_1_mi",
    ):
      try:
        engine_pg = obtener_motor_postgres()
        with engine_pg.connect() as conn:
          conn.execute(
              text('UPDATE "Medidores"."medidores_inteligentes" SET etapa = \'1\'')
          )
          conn.commit()
        st.success("¡Etapa 1 asignada correctamente a medidores_inteligentes!")
        st.rerun()
      except Exception as e:
        st.error(f"Error: {e}")

with tab4:
  st.subheader(
      "🔍 Explorador y Consulta del Endpoint de Levantamientos de MIAA"
  )
  st.markdown(
      "Consulta directamente los registros devueltos por el endpoint"
      " `/msvc-tecnica/medidores/levantamientos`, aplicando filtros por número"
      " de serie o predio."
  )

  col_busq1, col_busq2 = st.columns([3, 1])
  with col_busq1:
    input_busqueda_serie = st.text_input(
        "Buscar por Serie o Predio",
        value="222606007328",
        key="input_busq_levantamientos",
    )
  with col_busq2:
    st.markdown("<br>", unsafe_allow_html=True)
    btn_consultar_api_lev = st.button(
        "Consultar API", type="primary", use_container_width=True
    )

  if btn_consultar_api_lev or input_busqueda_serie:
    with st.spinner("Consultando endpoint de levantamientos..."):
      df_levantamientos_res = consultar_api_levantamientos(
          busqueda=input_busqueda_serie
      )

      if df_levantamientos_res.empty:
        st.warning(
            "No se encontraron registros en el endpoint para el filtro"
            f" especificado: `{input_busqueda_serie}`"
        )
      else:
        st.success(
            f"Se encontraron **{len(df_levantamientos_res):,}** registros"
            " disponibles en el endpoint."
        )
        st.dataframe(df_levantamientos_res, use_container_width=True, height=450)

        with st.container(border=True):
          st.markdown(
              "#### ⚙ Automatización e Inserción a PostgreSQL (Próximamente)"
          )
          st.markdown(
              "Aquí podrás activar la sincronización automática de este"
              " endpoint hacia tu base de datos con base en el intervalo de"
              " tiempo configurado en la barra lateral."
          )
          if st.button(
              "Guardar/Sincronizar Levantamientos en PostgreSQL",
              key="btn_sinc_levantamientos",
          ):
            st.info(
                "La estructura de inserción automática para este endpoint está"
                " lista para ser vinculada a tu esquema de PostgreSQL."
            )
