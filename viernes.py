"""
Viernes - Asistente personal multiusuario (versión estable sin Supabase)
"""
import os
import sqlite3
import base64
import streamlit as st
import streamlit.components.v1 as components
from groq import Groq
from duckduckgo_search import DDGS

st.set_page_config(page_title="Viernes", page_icon="🛰️", layout="centered")

MODELO_CHAT = "openai/gpt-oss-120b"
MODELO_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"
MODELO_AUDIO = "whisper-large-v3-turbo"
MAX_TURNOS = 10

# Ruta persistente en Streamlit Cloud (no se borra tan seguido)
ARCHIVO_BD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viernes_datos.db")

USUARIOS = {
    "jefe": "Viernes2026",
    "yerley": "clave123",
}

PERSONALIDAD = (
    "Eres Viernes (F.R.I.D.A.Y.), la IA personal del usuario, sucesora de J.A.R.V.I.S. "
    "Hablas en español neutro, con tono sereno, cercano y un humor seco ocasional. "
    "Tratas al usuario de 'jefe'. Eres directa, eficiente y cálida. "
    "Cuando resuelvas problemas matemáticos, SIEMPRE muestra el paso a paso. "
    "Si no sabes algo, lo dices con honestidad. No inventas datos."
)


@st.cache_resource
def get_groq():
    return Groq(api_key=st.secrets["GROQ_API_KEY"].strip())


# ===== BASE DE DATOS =====
def init_db():
    with sqlite3.connect(ARCHIVO_BD) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            rol TEXT NOT NULL,
            contenido TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS recuerdos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            dato TEXT NOT NULL,
            UNIQUE(usuario, dato))""")
        c.commit()


def guardar_msg(usuario, rol, contenido):
    with sqlite3.connect(ARCHIVO_BD) as c:
        c.execute("INSERT INTO historial (usuario, rol, contenido) VALUES (?, ?, ?)",
                  (usuario, rol, contenido))
        c.commit()


def get_historial(usuario, limite=20):
    with sqlite3.connect(ARCHIVO_BD) as c:
        cur = c.execute("SELECT rol, contenido FROM historial WHERE usuario = ? "
                        "ORDER BY id DESC LIMIT ?", (usuario, limite))
        return [{"role": r, "content": t} for r, t in reversed(cur.fetchall())]


def guardar_recuerdo(usuario, dato):
    try:
        with sqlite3.connect(ARCHIVO_BD) as c:
            c.execute("INSERT INTO recuerdos (usuario, dato) VALUES (?, ?)", (usuario, dato))
            c.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_recuerdos(usuario):
    with sqlite3.connect(ARCHIVO_BD) as c:
        return [r[0] for r in c.execute("SELECT dato FROM recuerdos WHERE usuario = ?",
                                        (usuario,)).fetchall()]


def borrar_recuerdos(usuario):
    with sqlite3.connect(ARCHIVO_BD) as c:
        c.execute("DELETE FROM recuerdos WHERE usuario = ?", (usuario,))
        c.commit()


def borrar_historial(usuario):
    with sqlite3.connect(ARCHIVO_BD) as c:
        c.execute("DELETE FROM historial WHERE usuario = ?", (usuario,))
        c.commit()


# ===== VOZ =====
def hablar(texto):
    t = texto.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${").replace("\n", " ")[:600]
    components.html(f"""
    <script>
    try {{
        speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(`{t}`);
        u.lang = 'es-ES'; u.rate = 1.0; u.pitch = 0.9;
        const v = speechSynthesis.getVoices().find(x => x.lang.startsWith('es'));
        if (v) u.voice = v;
        speechSynthesis.speak(u);
    }} catch(e) {{}}
    </script>
    """, height=0)


def transcribir(audio_bytes, groq_client):
    try:
        t = groq_client.audio.transcriptions.create(
            file=("audio.wav", audio_bytes), model=MODELO_AUDIO, language="es")
        return t.text.strip()
    except Exception as e:
        return f"[Error de audio: {e}]"


# ===== BÚSQUEDA Y VISIÓN =====
def buscar_internet(consulta):
    try:
        with DDGS() as d:
            res = [r for r in d.text(consulta, max_results=3)]
        if not res:
            return "No encontré información."
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
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
            max_tokens=500)
        return r.choices[0].message.content
    except Exception as e:
        return f"Error al ver la imagen: {e}"


# ===== RESPUESTA =====
def responder(usuario, prompt, groq_client, img_bytes=None):
    p = prompt.lower().strip()
    if p.startswith("recuerda que "):
        dato = prompt[12:].strip()
        return f"Anotado, {usuario}: «{dato}»" if guardar_recuerdo(usuario, dato) else "Ya lo tenía anotado."
    if img_bytes:
        return analizar_imagen(img_bytes, prompt, groq_client)
    if p.startswith("busca ") or "en internet" in p:
        q = prompt.replace("busca", "", 1).replace("en internet", "").strip()
        return buscar_internet(q)

    recuerdos = get_recuerdos(usuario)
    historial = get_historial(usuario, MAX_TURNOS)
    mensajes = [{"role": "system", "content": PERSONALIDAD}]
    if recuerdos:
        mensajes.append({"role": "system", "content": "Recuerdos:\n" + "\n".join(f"- {r}" for r in recuerdos)})
    mensajes.extend(historial)
    mensajes.append({"role": "user", "content": prompt})

    try:
        stream = groq_client.chat.completions.create(
            model=MODELO_CHAT, messages=mensajes, stream=True,
            temperature=0.5, max_tokens=1500)
        completo = ""
        for chunk in stream:
            d = chunk.choices[0].delta.content
            if d:
                completo += d
                yield d
        guardar_msg(usuario, "assistant", completo)
    except Exception as e:
        yield f"Problema: {e}"


# ===== APP =====
def main():
    init_db()
    groq_client = get_groq()

    if "logueado" not in st.session_state:
        st.session_state.logueado = False

    if not st.session_state.logueado:
        st.title("🛰️ Viernes")
        st.caption("Acceso restringido")
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Entrar"):
            if u in USUARIOS and USUARIOS[u] == p:
                st.session_state.logueado = True
                st.session_state.usuario = u
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
        st.stop()

    usuario = st.session_state.usuario
    st.sidebar.success(f"👤 {usuario}")
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.logueado = False
        st.rerun()

    voz_on = st.sidebar.toggle("🔊 Responder en voz alta", value=False)

    st.sidebar.markdown("---")
    st.sidebar.subheader("🧠 Recuerdos")
    recs = get_recuerdos(usuario)
    if recs:
        for r in recs:
            st.sidebar.caption(f"- {r}")
        if st.sidebar.button("Borrar recuerdos"):
            borrar_recuerdos(usuario)
            st.rerun()
    else:
        st.sidebar.caption("Nada aún. Dile: «recuerda que...»")

    st.sidebar.markdown("---")
    st.sidebar.subheader("📸 Imagen")
    img_file = st.sidebar.file_uploader("Sube una foto", type=["jpg", "jpeg", "png"])
    img_bytes = img_file.getvalue() if img_file else None
    if img_file:
        st.sidebar.image(img_file, use_container_width=True)

    st.sidebar.markdown("---")
    if st.sidebar.button("🧹 Borrar historial"):
        borrar_historial(usuario)
        st.rerun()

    st.title("🛰️ Viernes")
    st.caption(f"Bienvenido, {usuario}")

    for m in get_historial(usuario, 50):
        av = "🧑" if m["role"] == "user" else "🛰️"
        with st.chat_message(m["role"], avatar=av):
            st.markdown(m["content"])

    with st.expander("🎤 Hablar con Viernes"):
        audio = st.audio_input("Graba tu mensaje")
        if audio is not None and st.button("📤 Enviar audio"):
            with st.spinner("Escuchando..."):
                texto = transcribir(audio.getvalue(), groq_client)
            if texto and not texto.startswith("[Error"):
                st.session_state["prompt_pendiente"] = texto
                st.rerun()
            else:
                st.error(texto)

    prompt = st.chat_input("Escríbele a Viernes...")
    if "prompt_pendiente" in st.session_state:
        prompt = st.session_state.pop("prompt_pendiente")
    if img_bytes and not prompt:
        prompt = "Describe lo que ves en esta imagen."

    if prompt:
        with st.chat_message("user", avatar="🧑"):
            st.markdown(prompt)
            if img_bytes:
                st.image(img_bytes, width=300)
        guardar_msg(usuario, "user", prompt)
        with st.chat_message("assistant", avatar="🛰️"):
            caja = st.empty()
            resp = ""
            for t in responder(usuario, prompt, groq_client, img_bytes):
                resp += t
                caja.markdown(resp + "▌")
            caja.markdown(resp)
        if voz_on and resp:
            hablar(resp)


if __name__ == "__main__":
    main()