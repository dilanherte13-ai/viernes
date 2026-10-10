"""
Viernes - Asistente personal en la nube (Versión Final Definitiva)
"""
import os
import sqlite3
import datetime
import base64
import streamlit as st
import streamlit.components.v1 as components
from groq import Groq
from duckduckgo_search import DDGS

st.set_page_config(page_title="Viernes", page_icon="🛰️", layout="centered")

# ===== CONFIGURACIÓN =====
MODELO_CHAT = "llama-3.3-70b-versatile"
MODELO_VISION = "llama-3.2-11b-vision-preview"
MODELO_AUDIO = "whisper-large-v3-turbo"
ARCHIVO_BD = "viernes_memoria.db"
USUARIO = "jefe"
CONTRASENA = "Viernes2026"
MAX_TURNOS = 10

PERSONALIDAD = (
    "Eres Viernes (F.R.I.D.A.Y.), la IA personal del usuario, sucesora de J.A.R.V.I.S. "
    "Hablas en español neutro, con tono sereno, cercano y un humor seco ocasional. "
    "Tratas al usuario de 'jefe'. Eres directa, eficiente y cálida. "
    "Cuando resuelvas problemas matemáticos, SIEMPRE muestra el paso a paso. "
    "Si no sabes algo, lo dices con honestidad. No inventas datos."
)

# ===== CLIENTE GROQ =====
@st.cache_resource
def get_groq():
    return Groq(api_key=st.secrets["GROQ_API_KEY"])

# ===== BASE DE DATOS =====
def init_db():
    with sqlite3.connect(ARCHIVO_BD) as c:
        cur = c.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS historial (id INTEGER PRIMARY KEY AUTOINCREMENT, rol TEXT, contenido TEXT, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS recuerdos (id INTEGER PRIMARY KEY AUTOINCREMENT, dato TEXT UNIQUE, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.commit()

def guardar_msg(rol, contenido):
    with sqlite3.connect(ARCHIVO_BD) as c:
        c.execute("INSERT INTO historial (rol, contenido) VALUES (?, ?)", (rol, contenido))
        c.commit()

def get_historial(limite=20):
    with sqlite3.connect(ARCHIVO_BD) as c:
        cur = c.execute("SELECT rol, contenido FROM historial ORDER BY id DESC LIMIT ?", (limite,))
        return [{"role": r, "content": t} for r, t in reversed(cur.fetchall())]

def guardar_recuerdo(dato):
    try:
        with sqlite3.connect(ARCHIVO_BD) as c:
            c.execute("INSERT INTO recuerdos (dato) VALUES (?)", (dato,))
            c.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def get_recuerdos():
    with sqlite3.connect(ARCHIVO_BD) as c:
        return [r[0] for r in c.execute("SELECT dato FROM recuerdos").fetchall()]

# ===== VOZ (navegador, gratis) =====
def hablar(texto):
    texto = texto.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${").replace("\n", " ")[:600]
    components.html(f"""
    <script>
    try {{
        speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(`{texto}`);
        u.lang = 'es-ES'; u.rate = 1.0; u.pitch = 0.9;
        const v = speechSynthesis.getVoices().find(x => x.lang.startsWith('es'));
        if (v) u.voice = v;
        speechSynthesis.speak(u);
    }} catch(e) {{}}
    </script>
    """, height=0)

# ===== MICRÓFONO (Groq Whisper, gratis) =====
def transcribir(audio_bytes, groq_client):
    try:
        t = groq_client.audio.transcriptions.create(
            file=("audio.wav", audio_bytes),
            model=MODELO_AUDIO,
            language="es"
        )
        return t.text.strip()
    except Exception as e:
        return f"[Error de audio: {e}]"

# ===== BÚSQUEDA Y VISIÓN =====
def buscar_internet(consulta):
    try:
        with DDGS() as d:
            res = [r for r in d.text(consulta, max_results=3)]
        if not res:
            return "No encontré información sobre eso."
        return "Encontré esto:\n" + "\n".join([f"- {r['title']}: {r['body']}" for r in res])
    except Exception as e:
        return f"Error: {e}"

def analizar_imagen(img_bytes, prompt, groq_client):
    try:
        b64 = base64.b64encode(img_bytes).decode('utf-8')
        r = groq_client.chat.completions.create(
            model=MODELO_VISION,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]}],
            max_tokens=500
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"Error al ver la imagen: {e}"

# ===== RESPUESTA =====
def responder(prompt, groq_client, img_bytes=None):
    p = prompt.lower().strip()

    if p.startswith("recuerda que "):
        dato = prompt[12:].strip()
        return f"Anotado, jefe: «{dato}»" if guardar_recuerdo(dato) else "Ya lo tenía anotado, jefe."

    if img_bytes:
        return analizar_imagen(img_bytes, prompt, groq_client)

    if p.startswith("busca ") or "en internet" in p:
        q = prompt.replace("busca", "", 1).replace("en internet", "").strip()
        return buscar_internet(q)

    recuerdos = get_recuerdos()
    historial = get_historial(MAX_TURNOS)
    mensajes = [{"role": "system", "content": PERSONALIDAD}]
    if recuerdos:
        mensajes.append({"role": "system", "content": "Recuerdos del jefe:\n" + "\n".join(f"- {r}" for r in recuerdos)})
    mensajes.extend(historial)
    mensajes.append({"role": "user", "content": prompt})

    try:
        stream = groq_client.chat.completions.create(
            model=MODELO_CHAT, messages=mensajes, stream=True, temperature=0.5, max_tokens=1500
        )
        completo = ""
        for chunk in stream:
            d = chunk.choices[0].delta.content
            if d:
                completo += d
                yield d
        guardar_msg("assistant", completo)
    except Exception as e:
        yield f"Problema, jefe: {e}"

# ===== INTERFAZ =====
def main():
    init_db()
    groq_client = get_groq()

    # --- LOGIN SIMPLE ---
    if "logueado" not in st.session_state:
        st.session_state.logueado = False

    if not st.session_state.logueado:
        st.title("🛰️ Viernes")
        st.caption("Acceso restringido")
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Entrar"):
            if u == USUARIO and p == CONTRASENA:
                st.session_state.logueado = True
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
        st.stop()

    # --- APP (ya logueado) ---
    st.sidebar.success("Bienvenido, jefe")
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.logueado = False
        st.rerun()

    voz_on = st.sidebar.toggle("🔊 Responder en voz alta", value=False)

    st.sidebar.markdown("---")
    st.sidebar.subheader("🧠 Recuerdos")
    recs = get_recuerdos()
    if recs:
        for r in recs:
            st.sidebar.caption(f"- {r}")
        if st.sidebar.button("Borrar recuerdos"):
            with sqlite3.connect(ARCHIVO_BD) as c:
                c.execute("DELETE FROM recuerdos")
                c.commit()
            st.rerun()
    else:
        st.sidebar.caption("Nada aún. Dile: «recuerda que...»")

    st.sidebar.markdown("---")
    st.sidebar.subheader("📸 Imagen")
    img_file = st.sidebar.file_uploader("Sube una foto", type=["jpg", "jpeg", "png"])
    img_bytes = img_file.getvalue() if img_file else None
    if img_file:
        st.sidebar.image(img_file, use_container_width=True)

    st.title("🛰️ Viernes")
    st.caption("Tu asistente personal · disponible 24/7")

    for m in get_historial(50):
        av = "🧑" if m["role"] == "user" else "🛰️"
        with st.chat_message(m["role"], avatar=av):
            st.markdown(m["content"])

    # --- MICRÓFONO ---
    with st.expander("🎤 Hablar con Viernes (toca para grabar)"):
        audio = st.audio_input("Graba tu mensaje")
        if audio is not None and st.button("📤 Enviar audio"):
            with st.spinner("Escuchando..."):
                texto = transcribir(audio.getvalue(), groq_client)
            if texto and not texto.startswith("[Error"):
                st.success(f"Dijiste: «{texto}»")
                st.session_state["prompt_pendiente"] = texto
                st.rerun()
            else:
                st.error(texto)

    prompt = st.chat_input("Escríbele a Viernes...")

    # Procesar audio pendiente
    if "prompt_pendiente" in st.session_state:
        prompt = st.session_state.pop("prompt_pendiente")

    if img_bytes and not prompt:
        prompt = "Describe lo que ves en esta imagen."

    if prompt:
        with st.chat_message("user", avatar="🧑"):
            st.markdown(prompt)
            if img_bytes:
                st.image(img_bytes, width=300)
        guardar_msg("user", prompt)

        with st.chat_message("assistant", avatar="🛰️"):
            caja = st.empty()
            resp = ""
            for t in responder(prompt, groq_client, img_bytes):
                resp += t
                caja.markdown(resp + "▌")
            caja.markdown(resp)
        if voz_on and resp:
            hablar(resp)

if __name__ == "__main__":
    main()