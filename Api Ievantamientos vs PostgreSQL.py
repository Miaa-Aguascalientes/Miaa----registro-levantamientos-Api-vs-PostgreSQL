from datetime import datetime
import pandas as pd
import requests
from zoneinfo import ZoneInfo
import streamlit as st

ZONA_MEXICO = ZoneInfo("America/Mexico_City")

st.set_page_config(
    page_title="Prueba Conexión API MIAA",
    page_icon="https://www.miaa.mx/favicon.ico",
    layout="wide",
)

st.markdown(
    """
    <style>
        .terminal-box {
            background-color: #0b0f19;
            border: 1px solid #22c55e;
            color: #22c55e;
            font-family: 'Courier New', Courier, monospace;
            padding: 15px;
            border-radius: 6px;
            height: 350px;
            overflow-y: scroll;
            font-size: 13px;
            line-height: 1.4;
        }
    </style>
""",
    unsafe_allow_html=True,
)

BASE_URL = "https://prelec.miaa.mx"
URL_LOGIN = BASE_URL + "/auth/login"
URL_LEVANTAMIENTOS = BASE_URL + "/msvc-tecnica/medidores/levantamientos"

st.markdown(
    "### 🔌 Diagnóstico y Prueba Directa de Conexión a la API de Levantamientos"
)
st.markdown(
    "Este script realiza el proceso de autenticación con tus credenciales y"
    " ejecuta exactamente la petición GET al endpoint de levantamientos."
)

if "logs_prueba" not in st.session_state:
  st.session_state.logs_prueba = [
      f"[{datetime.now(ZONA_MEXICO).strftime('%H:%M:%S')}] Sistema listo para"
      " probar conexión."
  ]


def agregar_log_prueba(msg):
  ts = datetime.now(ZONA_MEXICO).strftime("%H:%M:%S")
  st.session_state.logs_prueba.insert(0, f"[{ts}] {msg}")


col1, col2 = st.columns([1, 1])

with col1:
  if st.button("Ejecutar Prueba de Conexión", type="primary"):
    usuario = st.secrets["api"]["usuario"]
    password = st.secrets["api"]["password"]

    agregar_log_prueba(
        f"Intentando autenticar en {URL_LOGIN} con usuario: {usuario}"
    )

    try:
      res_login = requests.post(
          URL_LOGIN,
          json={"username": usuario, "password": password},
          headers={"Content-Type": "application/json"},
          timeout=15,
      )

      agregar_log_prueba(
          f"Respuesta Login HTTP Status: {res_login.status_code}"
      )

      if res_login.status_code == 200:
        data_login = res_login.json()
        token = data_login.get("token") or data_login.get("access_token")

        if token:
          agregar_log_prueba("✅ Token obtenido exitosamente.")

          # Parámetros exactos requeridos
          params = [
              ("page", 0),
              ("size", 20),
              ("busqueda", "222606007328"),
              ("sort", "serie,asc"),
              ("sort", "predio,asc"),
          ]

          agregar_log_prueba(f"Consultando GET a {URL_LEVANTAMIENTOS}...")
          res_lev = requests.get(
              URL_LEVANTAMIENTOS,
              headers={
                  "Content-Type": "application/json",
                  "Authorization": f"Bearer {token}",
              },
              params=params,
              timeout=30,
          )

          agregar_log_prueba(
              f"Respuesta Levantamientos HTTP Status: {res_lev.status_code}"
          )
          agregar_log_prueba(f"Cuerpo de respuesta: {res_lev.text}")

          if res_lev.status_code == 200:
            st.session_state["datos_api_crudos"] = res_lev.json()
          else:
            st.session_state["datos_api_crudos"] = None
        else:
          agregar_log_prueba(
              "❌ Error: El JSON de login no devolvió ningún token válido."
          )
      else:
        agregar_log_prueba(f"❌ Error en Login: {res_lev.text if 'res_lev' in locals() else res_login.text}")
    except Exception as e:
      agregar_log_prueba(f"❌ Excepción crítica durante la petición: {e}")

st.markdown("#### 🖥️ Consola de Depuración")
logs_html = "<br>".join(st.session_state.logs_prueba)
st.markdown(
    f'<div class="terminal-box">{logs_html}</div>', unsafe_allow_html=True
)

if "datos_api_crudos" in st.session_state and st.session_state["datos_api_crudos"]:
  st.markdown("#### 📊 Datos devueltos por la API (JSON parseado)")
  st.json(st.session_state["datos_api_crudos"])
