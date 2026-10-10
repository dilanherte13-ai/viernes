"""
Viernes - Asistente personal en la nube
---------------------------------------
Chat con IA en Streamlit + Groq. Se despliega en Streamlit Community Cloud
para que cualquiera pueda usarlo desde el navegador, sin tener la PC prendida.
"""
import os
import re

import streamlit as st
import streamlit.components.v1 as components

try:
    from groq import Groq
except ImportError:
    st.error("Falta instalar groq. Ejecuta: pip install groq")
    st.stop()

st.set_page_config(page_title="Viernes", page_icon="🛰️", layout="centered")

# ---------------- Configuración ----------------
MODELO = "openai/gpt-oss-120b"   # Reemplazo del modelo retirado
MAX_TURNOS = 12                       # cuántos mensajes recordar en la conversación

PERSONALIDAD = (
    "Eres Viernes (F.R.I.D.A.Y.), la inteligencia artificial personal del usuario, "
    "sucesora de J.A.R.V.I.S. Hablas en español neutro, con tono sereno, cercano y un "
    "humor seco ocasional. Tratas al usuario de 'jefe' cuando sea natural, sin exagerar. "
    "Eres directa, eficiente y cálida. Respondes en 1 a 4 frases cortas, sin markdown "
    "ni emojis, salvo que el usuario pida algo distinto. Si te piden matemáticas, "
    "resuelves paso a paso y das el resultado final claro. Si no sabes algo, lo dices "
    "con honestidad. Nunca inventas datos. Si el usuario te pide que recuerdes algo, "
    "lo confirmas brevemente. Estás disponible 24/7 desde la nube."
)


# ---------------- Estado ----------------
def init_estado():
    st.session_state.setdefault("mensajes", [])
    st.session_state.setdefault("memoria", [])
    st.session_state.setdefault("voz", False)


# ---------------- Cliente Groq ----------------
def get_client():
    try:
        key = st.secrets["GROQ_API_KEY"]
    except (KeyError, FileNotFoundError):
        key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        st.error(
            "Falta la clave GROQ_API_KEY. Agrégala en los Secrets de Streamlit "
            "o como variable de entorno."
        )
        st.stop()
    return Groq(api_key=key)


# ---------------- Voz (TTS del navegador) ----------------
def hablar(texto: str):
    texto = texto.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    texto = texto.replace("\n", " ")[:600]
    components.html(
        f"""
        <script>
        try {{
            window.speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance(`{texto}`);
            u.lang = 'es-ES';
            u.rate = 1.05;
            u.pitch = 0.95;
            const voces = speechSynthesis.getVoices();
            const esVoz = voces.find(v => v.lang.startsWith('es'));
            if (esVoz) u.voice = esVoz;
            speechSynthesis.speak(u);
        }} catch(e) {{}}
        </script>
        """,
        height=0,
    )


# ---------------- Memoria simple ----------------
RE_RECUERDA = re.compile(
    r"^\s*(?:por favor[,\s]*)?(?:recuerda|recuérdame|acuerdate de|anota|apunta|"
    r"guarda en memoria|no olvides)\s+(?:que\s+)?(.+?)[.!\s]*$",
    re.IGNORECASE,
)
RE_OLVIDA = re.compile(
    r"^\s*(?:olvida|borra|elimina)\s+(?:el recuerdo|lo de|el dato)\s+(.+?)[.!\s]*$",
    re.IGNORECASE,
)


def procesar_memoria(texto: str):
    m = RE_RECUERDA.match(texto)
    if m:
        dato = m.group(1).strip()
        if dato and dato not in st.session_state.memoria:
            st.session_state.memoria.append(dato)
        return True
    m = RE_OLVIDA.match(texto)
    if m:
        dato = m.group(1).strip().lower()
        st.session_state.memoria = [
            r for r in st.session_state.memoria if dato not in r.lower()
        ]
        return True
    return False


# ---------------- Motor de chat ----------------
def generar(mensajes):
    cliente = get_client()
    sistema = PERSONALIDAD
    if st.session_state.memoria:
        sistema += "\n\nRecuerdos guardados del usuario (úsalos solo si vienen al caso):\n"
        sistema += "\n".join(f"- {r}" for r in st.session_state.memoria)
    historial = mensajes[-MAX_TURNOS * 2:]
    entrada = [{"role": "system", "content": sistema}] + historial
    try:
        stream = cliente.chat.completions.create(
            model=MODELO,
            messages=entrada,
            stream=True,
            temperature=0.6,
            max_tokens=1200,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as e:
        yield f"Lo siento, jefe, tuve un problema al conectar con el modelo: {e}"


# ---------------- Interfaz ----------------
def main():
    init_estado()

    st.markdown("## 🛰️ Viernes")
    st.caption("Tu asistente personal en la nube · disponible desde cualquier dispositivo")

    with st.sidebar:
        st.header("⚙️ Ajustes")
        st.session_state.voz = st.toggle(
            "🔊 Responder en voz alta", value=st.session_state.voz
        )

        if st.button("🧹 Nueva conversación", use_container_width=True):
            st.session_state.mensajes = []
            st.rerun()

        st.divider()
        st.subheader("🧠 Recuerdos")
        if st.session_state.memoria:
            for i, r in enumerate(st.session_state.memoria, 1):
                st.write(f"{i}. {r}")
            if st.button("Borrar todos los recuerdos", use_container_width=True):
                st.session_state.memoria = []
                st.rerun()
        else:
            st.caption("Aún no recuerdo nada. Escríbeme «recuerda que...» y lo guardaré.")

        st.divider()
        st.caption("Viernes v1.0 · Streamlit + Groq")

    # Historial
    for m in st.session_state.mensajes:
        rol = "user" if m["role"] == "user" else "assistant"
        avatar = "🧑" if rol == "user" else "🛰️"
        with st.chat_message(rol, avatar=avatar):
            st.markdown(m["content"])

    # Entrada
    prompt = st.chat_input("Escríbele a Viernes...")
    if not prompt:
        return

    procesar_memoria(prompt)
    st.session_state.mensajes.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🛰️"):
        caja = st.empty()
        texto = ""
        for trozo in generar(st.session_state.mensajes):
            texto += trozo
            caja.markdown(texto + "▌")
        caja.markdown(texto)

    st.session_state.mensajes.append({"role": "assistant", "content": texto})
    if st.session_state.voz:
        hablar(texto)


if __name__ == "__main__":
    main()