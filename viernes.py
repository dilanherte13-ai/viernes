"""
Viernes - Asistente personal en la nube (Versión Definitiva)
------------------------------------------------------------
Incluye: micrófono (Groq Whisper), voz (navegador), memoria persistente,
visión, búsqueda en internet, matemáticas paso a paso y login.
"""
import os
import re
import sqlite3
import datetime
import base64
import streamlit as st
import streamlit.components.v1 as components
import streamlit_authenticator as stauth
from groq import Groq
from duckduckgo_search import DDGS

st.set_page_config(page_title="Viernes", page_icon="🛰️", layout="centered")

MODELO_CHAT = "llama-3.3-70b-versatile"
MODELO_VISION = "llama-3.2-11b-vision-preview"
MODELO_AUDIO = "whisper-large-v3-turbo"
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


@st.cache_resource
def inicializar_cliente():
    try:
        groq_key = st.secrets["GROQ_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error("Falta la clave GROQ_API_KEY en los Secrets de Streamlit.")
        st.stop()
    return Groq(api_key=groq_key)


def configurar_autenticacion():
    hash_password = "$2b$12$T1dDgjVeVidEcQMLUo8FnuAUlyWITzlJcUoMDOBigksdhuxeo.4BG"
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
    return stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days']
    )


def inicializar_db():
    with sqlite3.connect(ARCHIVO_BD) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS historial ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "usuario TEXT NOT NULL, rol TEXT NOT NULL, "
            "contenido TEXT NOT NULL, "
            "fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS recuerdos ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "usuario TEXT NOT NULL, dato TEXT NOT NULL UNIQUE, "
            "fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
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
            "SELECT rol, contenido FROM historial WHERE usuario = ? "
            "ORDER BY id DESC LIMIT ?",
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


def hablar_navegador(texto):
    texto = texto.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    texto = texto.replace("\n", " ")[:600]
    components.html(
        """
        <script>
        try {
            window.speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance(`%s`);
            u.lang = 'es-ES';
            u.rate = 1.0;
            u.pitch = 0.9;
            const voces = speechSynthesis.getVoices();
            const esVoz = voces.find(v => v.lang.startsWith('es'));
            if (esVoz) u.voice = esVoz;
            speechSynthesis.speak(u);
        } catch(e) {}
        </script>
        """ % texto,
        height=0,
    )


def transcribir_audio(audio_bytes, groq_client):
    try:
        transcripcion = groq_client.audio.transcriptions.create(
            file=("audio.wav", audio_bytes),
            model=MODELO_AUDIO,
            language="es"
        )
        return transcripcion.text.strip()
    except Exception as e:
        return f"[Error de audio: {e}]"


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
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }}
                ]
            }],
            max_tokens=500
        )
        return respuesta.choices[0].message.content
    except Exception as e:
        return f"Error al analizar la imagen: {e}"


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
        contexto_recuerdos = (
            "Recuerdos importantes sobre el jefe:\n"
            + "\n".join([f"- {r}" for r in recuerdos])
        )
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


def procesar_prompt(usuario, prompt_texto, groq_client, imagen_bytes, voz_activada):
    with st.chat_message("user", avatar="🧑"):
        if prompt_texto:
            st.markdown(prompt_texto)
        if imagen_bytes:
            st.image(imagen_bytes, caption="Imagen enviada", width=300)

    guardar_mensaje(usuario, "user", prompt_texto or "[Imagen enviada]")

    with st.chat_message("assistant", avatar="🛰️"):
        caja_respuesta = st.empty()
        respuesta_completa = ""
        for trozo in generar_respuesta(usuario, prompt_texto, groq_client, imagen_bytes):
            respuesta_completa += trozo
            caja_respuesta.markdown(respuesta_completa + "▌")
        caja_respuesta.markdown(respuesta_completa)

    if voz_activada and respuesta_completa:
        hablar_navegador(respuesta_completa)


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

    st.sidebar.markdown("---")
    st.sidebar.subheader("📸 Analizar imagen")
    archivo_imagen = st.sidebar.file_uploader(
        "Sube una foto para que Viernes la vea",
        type=["jpg", "jpeg", "png"]
    )
    imagen_bytes = None
    if archivo_imagen is not None:
        imagen_bytes = archivo_imagen.getvalue()
        st.sidebar.image(archivo_imagen, caption="Imagen cargada", use_container_width=True)

    st.title("🛰️ Viernes")
    st.caption("Tu asistente personal en la nube · disponible desde cualquier dispositivo")

    for mensaje in obtener_historial(username, 50):
        avatar = "🧑" if mensaje["role"] == "user" else "🛰️"
        with st.chat_message(mensaje["role"], avatar=avatar):
            st.markdown(mensaje["content"])

    with st.expander("🎤 Hablar con Viernes (toca aquí para grabar)"):
        audio_grabado = st.audio_input("Graba tu mensaje", key="audio_input_viernes")
        if audio_grabado is not None:
            if st.button("📤 Enviar audio a Viernes", key="enviar_audio"):
                with st.spinner("Transcribiendo tu voz..."):
                    texto_transcrito = transcribir_audio(audio_grabado.getvalue(), groq_client)
                if texto_transcrito and not texto_transcrito.startswith("[Error"):
                    st.success(f"Escuché: «{texto_transcrito}»")
                    procesar_prompt(username, texto_transcrito, groq_client, None, voz_activada)
                    st.rerun()
                else:
                    st.error(texto_transcrito)

    prompt_texto = st.chat_input("Escríbele a Viernes...")

    if imagen_bytes and not prompt_texto:
        prompt_texto = "Describe lo que ves en esta imagen."

    if prompt_texto:
        procesar_prompt(username, prompt_texto, groq_client, imagen_bytes, voz_activada)


if __name__ == "__main__":
    main()