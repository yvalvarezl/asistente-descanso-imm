from io import BytesIO
import streamlit as st
from gtts import gTTS
from mqtt_bridge import (
    enviar_comando_mqtt,
    leer_ultimo_estado_mqtt,
    TOPIC_CMD,
    TOPIC_ESTADO,
)

st.set_page_config(
    page_title="Asistente de Descanso y Cuidado",
    page_icon="🌿",
    layout="centered",
)

# Estado de sesión compartido entre páginas
if "vasos_agua" not in st.session_state:
    st.session_state.vasos_agua = 0
if "estado_actual" not in st.session_state:
    st.session_state.estado_actual = "ENFOQUE"
if "ultimo_mensaje" not in st.session_state:
    st.session_state.ultimo_mensaje = (
        "Listas para trabajar con calma. Recuerda tomar agua y hacer pausas."
    )
if "ultimo_estado_wokwi" not in st.session_state:
    st.session_state.ultimo_estado_wokwi = None


def hablar_texto(texto: str) -> bytes | None:
    try:
        tts = gTTS(text=texto, lang="es")
        buf = BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def detectar_intencion(texto: str) -> str:
    t = texto.lower()
    if any(k in t for k in ["agua", "sed", "hidratar", "tomar"]):
        return "AGUA"
    if any(
        k in t for k in ["descans", "estres", "cansad", "pausa", "agotad", "respir"]
    ):
        return "PAUSA"
    return "ENFOQUE"


def responder_y_sincronizar(estado: str, texto_usuario: str = ""):
    st.session_state.estado_actual = estado

    if estado == "PAUSA":
        mensaje = (
            "Respira profundo, suelta los hombros y tómate unos minutos de descanso. "
            "Vas muy bien, no tienes que resolverlo todo de golpe."
        )
    elif estado == "AGUA":
        st.session_state.vasos_agua += 1
        mensaje = (
            f"¡Buen recordatorio! Tómate un vaso de agua. "
            f"Llevas {st.session_state.vasos_agua} vaso(s) registrado(s) hoy."
        )
    else:
        mensaje = (
            "Volvemos a modo enfoque. Elige una tarea pequeña y avanza con tranquilidad."
        )

    st.session_state.ultimo_mensaje = mensaje
    ok, detalle_envio = enviar_comando_mqtt(estado=estado, origen="streamlit")
    estado_wokwi = leer_ultimo_estado_mqtt(timeout_seg=1.5)
    st.session_state.ultimo_estado_wokwi = estado_wokwi

    st.markdown(f"**Mensaje:** {mensaje}")
    audio_bytes = hablar_texto(mensaje)
    if audio_bytes:
        st.audio(audio_bytes, format="audio/mp3")

    if ok:
        st.success(detalle_envio)
    else:
        st.warning(detalle_envio)

    if estado_wokwi:
        st.info(f"Respuesta desde Wokwi ({TOPIC_ESTADO}): {estado_wokwi}")
    else:
        st.caption(
            f"Aún no se leyó confirmación en {TOPIC_ESTADO}. "
            "Asegúrate de tener la simulación de Wokwi corriendo y conectada al broker."
        )


def pagina_pausa_y_animo():
    st.title("🌿 Ambiente 1: Pausa y Ánimo")
    st.write(
        "Cuéntame cómo te sientes mientras estudias o trabajas. "
        "Recibirás un mensaje en texto y audio, y se enviará la señal a Wokwi."
    )

    texto_estado = st.text_input(
        "Escribe cómo te sientes o qué necesitas:",
        placeholder="Ej.: estoy estresada, necesito descansar o tengo sed",
    )

    audio_grabado = st.audio_input("O graba un audio con tu voz:")
    if audio_grabado is not None:
        st.caption(
            "Audio capturado. Escribe o selecciona una acción abajo para sincronizar el estado."
        )

    col1, col2 = st.columns(2)
    with col1:
        enviar_texto = st.button("Enviar estado", use_container_width=True)
    with col2:
        pedir_pausa_rapida = st.button(
            "Necesito descansar", use_container_width=True
        )

    if enviar_texto:
        intencion = detectar_intencion(texto_estado)
        responder_y_sincronizar(intencion, texto_estado)
    elif pedir_pausa_rapida:
        responder_y_sincronizar("PAUSA", "necesito descansar")

    st.divider()
    st.subheader("Estado actual")
    st.write(f"**Modo activo:** {st.session_state.estado_actual}")
    st.write(f"**Último mensaje:** {st.session_state.ultimo_mensaje}")
    if st.session_state.ultimo_estado_wokwi:
        st.json(st.session_state.ultimo_estado_wokwi)


def pagina_agua_y_enfoque():
    st.title("💧 Ambiente 2: Agua y Enfoque")
    st.write(
        "Control rápido para hidratarte y volver a concentrarte con confirmación por voz y Wokwi."
    )

    st.metric("Vasos de agua registrados", st.session_state.vasos_agua)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Registrar vaso de agua", use_container_width=True):
            responder_y_sincronizar("AGUA", "registrar vaso de agua")
    with col2:
        if st.button("Volver a Modo Enfoque", use_container_width=True):
            responder_y_sincronizar("ENFOQUE", "volver a modo enfoque")

    st.divider()
    st.subheader("Sincronización con Wokwi")
    st.write(f"**Tópico comandos:** `{TOPIC_CMD}`")
    st.write(f"**Tópico respuesta:** `{TOPIC_ESTADO}`")
    if st.session_state.ultimo_estado_wokwi:
        st.json(st.session_state.ultimo_estado_wokwi)
    else:
        st.caption(
            "Pulsa uno de los dos botones para enviar un estado y consultar la respuesta de Wokwi."
        )


pg1 = st.Page(pagina_pausa_y_animo, title="Pausa y Ánimo", icon="🌿")
pg2 = st.Page(pagina_agua_y_enfoque, title="Agua y Enfoque", icon="💧")

nav = st.navigation([pg1, pg2])
nav.run()
