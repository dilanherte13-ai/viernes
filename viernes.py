"""
Viernes - Asistente personal en la nube (Versión 2.0)
------------------------------------------------------
Incluye: memoria persistente (SQLite), voz gratuita del navegador,
micrófono, análisis de imágenes, búsqueda en internet,
resolución de matemáticas paso a paso y sistema de login.
"""
import os
import re
import sqlite3
import datetime
import base64
import io

import streamlit as st
import streamlit.components.v1 as components
import streamlit_authenticator as stauth
from groq import Groq
from duckduckgo_search import DDGS

# --- 1. CONFIGURACIÓN INICIAL Y CONSTANTES ---
st.set_page_config(page_title="Viernes", page_icon="🛰️", layout="centered")

MODELO_CHAT = "llama-3.3-70b-versatile"
MODELO_VISION = "llama-3.2-11b-vision-preview"
ARCHIVO_BD = "viernes_memoria.db"
MAX_TURNOS_MEMORIA = 10

PERSONALIDAD = (
    "Eres Viernes (F.R.I.D.A.Y.), la IA personal del usuario, sucesora de J.A.R.V.I.S. "
    "Hablas en español neutro, con tono sereno, cercano y un humor seco ocasional. "
    "Tratas al usuario de 'jefe'. Eres directa, eficiente y cálida. "
    "Cuando resuelvas problemas matemáticos, SIEMPRE muestra el paso a paso, "
    "explicando cada operación con claridad y terminando con el resultado final. "
    "Si no sabes algo, lo dices con honestidad. No inventas datos."
)

# --- 2. CLIENTE DE GROQ ---
@st.cache_resource
def inicializar_cliente():
    try:
        groq_key = st.secrets["GROQ_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error("Falta la clave GROQ_API_KEY en los Secrets de Streamlit.")
        st.stop()
    return Groq(api_key=groq_key)

# --- 3. SISTEMA DE AUTENTICACIÓN ---
def configurar_autenticacion():
    # ⚠️ IMPORTANTE: Reemplaza este hash con el de TU contraseña.
    # Para generarlo, abre una terminal y ejecuta:
    # python -c "import streamlit_authenticator as stauth; print(stauth.Hasher(['TU_CONTRASEÑA']).generate())"
    hash_password = "$2b$12$ywh.WUiQv3oev.X04FhPZ 0zRblhUhs5x2aJe0YcZlehhZb0/ 03eqK" 

    config = {
        'credentials': {
            'usernames': {
                'jefe': {
                    'name': 'Jefe',
                    'password': hash_password,
                    'email': 'jefe@viernes.com'
                }
            }
        },
        'cookie': {
            'expiry_days': 30,
            'key': 'viernes_cookie_clave_secreta',
            'name': 'viernes_cookie'
        }
    }
    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days']
    )
    return authenticator

# --- 4. BASE DE DATOS (MEMORIA) ---
def inicializar_db():
    with sqlite3.connect(ARCHIVO_BD) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                rol TEXT NOT NULL,
                contenido TEXT NOT NULL,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recuerdos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                dato TEXT NOT NULL UNIQUE,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def guardar_mensaje(usuario, rol, contenido):
    with sqlite3.connect(ARCHIVO_BD) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO historial (usuario, rol, contenido) VALUES (?, ?, ?)",
            (usuario, rol, contenido)
        )
        conn.commit()

def obtener_historial(usuario, limite=20):
    with sqlite3.connect(ARCHIVO_BD) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rol, contenido FROM historial WHERE usuario = ? ORDER BY id DESC LIMIT ?",
            (usuario, limite)
        )
        filas = cursor.fetchall()
        return [{"role": rol, "content": contenido} for rol, contenido in reversed(filas)]

def guardar_recuerdo(usuario, dato):
    try:
        with sqlite3.connect(ARCHIVO_BD) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO recuerdos (usuario, dato) VALUES (?, ?)",
                (usuario, dato)
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def obtener_recuerdos(usuario):
    with sqlite3.connect(ARCHIVO_BD) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT dato FROM recuerdos WHERE usuario = ?", (usuario,))
        return [fila[0] for fila in cursor.fetchall()]

# --- 5. VOZ GRATUITA (NAVEGADOR) ---
def hablar_navegador(texto):
    texto = texto.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    texto = texto.replace("\n", " ")[:600]
    components.html(
        f"""
        <script>
        try {{
            window.speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance(`{texto}`);
            u.lang = 'es-ES';
            u.rate = 1.0;
            u.pitch = 0.9;
            const voces = speechSynthesis.getVoices();
            const esVoz = voces.find(v => v.lang.startsWith('es'));
            if (esVoz) u.voice = esVoz;
            speechSynthesis.speak(u);
        }} catch(e) {{}}
        </script>
        """,
        height=0,
    )

# --- 6. BÚSQUEDA Y VISIÓN ---
def buscar_en_internet(consulta):
    try:
        with DDGS() as ddgs:
            resultados = [r for r in ddgs.text(consulta, max_results=3)]
        if not resultados:
            return "No encontré información sobre eso en internet."
        contexto = "\n".join([f"- {r['title']}: {r['body']}" for r in resultados])
        return f"Esto es lo que encontré en internet:\n{contexto}"
    except Exception as e:
        return f"Error al buscar en internet: {e}"

def analizar_imagen(imagen_bytes, prompt, groq_client):
    try:
        base64_image = base64.b64encode(imagen_bytes).decode('utf-8')
        respuesta = groq_client.chat.completions.create(
            model=MODELO_VISION,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        }
                    ]
                }
            ],
            max_tokens=500
        )
        return respuesta.choices[0].message.content
    except Exception as e:
        return f"Error al analizar la imagen: {e}"

# --- 7. LÓGICA DE CHAT ---
def generar_respuesta(usuario, prompt_texto, groq_client, imagen_bytes=None):
    prompt_lower = prompt_texto.lower().strip()
    
    if prompt_lower.startswith("recuerda que "):
        dato = prompt_texto[12:].strip()
        if guardar_recuerdo(usuario, dato):
            return f"Entendido, jefe. Lo recordaré: «{dato}»"
        return "Ya tenía eso anotado, jefe."

    if imagen_bytes:
        return analizar_imagen(imagen_bytes, prompt_texto, groq_client)

    if prompt_lower.startswith("busca ") or "en internet" in prompt_lower:
        consulta = prompt_texto.replace("busca", "", 1).replace("en internet", "").strip()
        return buscar_en_internet(consulta)

    recuerdos = obtener_recuerdos(usuario)
    historial = obtener_historial(usuario, MAX_TURNOS_MEMORIA)
    
    mensajes = [{"role": "system", "content": PERSONALIDAD}]
    if recuerdos:
        contexto_recuerdos = "Recuerdos importantes sobre el jefe:\n" + "\n".join([f"- {r}" for r in recuerdos])
        mensajes.append({"role": "system", "content": contexto_recuerdos})
    mensajes.extend(historial)
    mensajes.append({"role": "user", "content": prompt_texto})

    try:
        stream = groq_client.chat.completions.create(
            model=MODELO_CHAT,
            messages=mensajes,
            stream=True,
            temperature=0.5,
            max_tokens=1500,
        )
        respuesta_completa = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                respuesta_completa += delta
                yield delta
        guardar_mensaje(usuario, "assistant", respuesta_completa)
    except Exception as e:
        yield f"Lo siento, jefe, tuve un problema: {e}"

# --- 8. INTERFAZ PRINCIPAL ---
def main():
    inicializar_db()
    groq_client = inicializar_cliente()
    authenticator = configurar_autenticacion()
    authenticator.login(location='main')
    name = st.session_state.get("name")
    authentication_status = st.session_state.get("authentication_status")
    username = st.session_state.get("username")

    if authentication_status is False:
        st.error('Usuario o contraseña incorrectos')
        st.stop()
    elif authentication_status is None:
        st.warning('Por favor, introduce tu usuario y contraseña')
            st.stop()

    st.sidebar.success(f"Bienvenido, {name}")
    authenticator.logout('Cerrar sesión', 'sidebar')

    st.sidebar.markdown("---")
    voz_activada = st.sidebar.toggle("🔊 Responder en voz alta", value=False)

    st.sidebar.markdown("---")
    st.sidebar.subheader("🧠 Recuerdos")
    recuerdos = obtener_recuerdos(username)
    if recuerdos:
        for r in recuerdos:
            st.sidebar.caption(f"- {r}")
        if st.sidebar.button("Borrar todos los recuerdos"):
            with sqlite3.connect(ARCHIVO_BD) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM recuerdos WHERE usuario = ?", (username,))
                conn.commit()
            st.rerun()
    else:
        st.sidebar.caption("Aún no recuerdo nada. Escríbeme «recuerda que...»")

    st.title("🛰️ Viernes")
    st.caption("Tu asistente personal en la nube · disponible desde cualquier dispositivo")

    for mensaje in obtener_historial(username, 50):
        with st.chat_message(mensaje["role"], avatar="🧑" if mensaje["role"] == "user" else "🛰️"):
            st.markdown(mensaje["content"])

    resultado = multimodal_chat_input(
        placeholder="Escríbele a Viernes o usa el micrófono...",
        enable_voice_input=True,
        voice_recognition_method="web_speech",
        voice_language="es-ES",
        key="chat_input_principal"
    )

    if resultado:
        prompt_texto = resultado.get("text", "")
        imagen_bytes = None
        if resultado.get("files"):
            file_info = resultado["files"][0]
            if file_info.get('data'):
                try:
                    base64_data = file_info['data'].split(',')[1]
                    imagen_bytes = base64.b64decode(base64_data)
                except Exception:
                    st.warning("Hubo un problema al procesar la imagen.")
        
        if prompt_texto or imagen_bytes:
            with st.chat_message("user", avatar="🧑"):
                if prompt_texto:
                    st.markdown(prompt_texto)
                if imagen_bytes:
                    st.image(imagen_bytes, caption="Imagen enviada", width=300)
            
            guardar_mensaje(username, "user", prompt_texto or "[Imagen enviada]")

            with st.chat_message("assistant", avatar="🛰️"):
                caja_respuesta = st.empty()
                respuesta_completa = ""
                for trozo in generar_respuesta(username, prompt_texto, groq_client, imagen_bytes):
                    respuesta_completa += trozo
                    caja_respuesta.markdown(respuesta_completa + "▌")
                caja_respuesta.markdown(respuesta_completa)
            
            if voz_activada and respuesta_completa:
                hablar_navegador(respuesta_completa)

if __name__ == "__main__":
    main()