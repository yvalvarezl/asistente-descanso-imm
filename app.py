from io import BytesIO
from datetime import datetime
import numpy as np
import streamlit as st
from gtts import gTTS
from mqtt_bridge import (
    enviar_comando_mqtt,
    leer_ultimo_estado_mqtt,
    TOPIC_CMD,
    TOPIC_ESTADO,
)

st.set_page_config(
    page_title="CUNNA · Rutina de Sueño y Cuidado",
    page_icon="🌙",
    layout="centered",
)

# ---------------------------------------------------------
# Estado de sesión persistente entre ambientes
# ---------------------------------------------------------
if "fase_rutina" not in st.session_state:
    st.session_state.fase_rutina = "EN_CALMA"
if "edad_meses" not in st.session_state:
    st.session_state.edad_meses = 4
if "eventos_sueno" not in st.session_state:
    st.session_state.eventos_sueno = []
if "vasos_agua" not in st.session_state:
    st.session_state.vasos_agua = 0
if "ultimo_mensaje" not in st.session_state:
    st.session_state.ultimo_mensaje = (
        "Bienvenida a CUNNA. Un espacio suave para acompañar el sueño del bebé y tu descanso."
    )
if "ultimo_estado_wokwi" not in st.session_state:
    st.session_state.ultimo_estado_wokwi = None


# ---------------------------------------------------------
# Funciones de audio y apoyo
# ---------------------------------------------------------
def generar_voz_gtts(texto: str) -> bytes | None:
    try:
        tts = gTTS(text=texto, lang="es")
        buf = BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def generar_sonido_ambiente(tipo: str, duracion_seg: float = 4.0, sr: int = 16000) -> bytes:
    """Genera audio WAV en memoria para arrullo suave o ruido blanco."""
    import wave

    t = np.linspace(0, duracion_seg, int(sr * duracion_seg), endpoint=False)
    if tipo == "ruido_blanco":
        # Ruido blanco suavizado con envolvente lenta
        rng = np.random.default_rng(42)
        onda = rng.normal(0.0, 0.14, size=t.shape)
        # Suavizado simple por media móvil para hacerlo menos áspero
        kernel = np.ones(12) / 12.0
        onda = np.convolve(onda, kernel, mode="same")
    else:
        # Melodía de cuna suave (acorde cálido en ondas senoidales lentas)
        nota1 = 0.08 * np.sin(2 * np.pi * 261.63 * t)  # Do4
        nota2 = 0.06 * np.sin(2 * np.pi * 329.63 * t)  # Mi4
        nota3 = 0.05 * np.sin(2 * np.pi * 392.00 * t)  # Sol4
        pulso = 0.5 + 0.5 * np.sin(2 * np.pi * 0.4 * t)
        onda = (nota1 + nota2 + nota3) * (0.4 + 0.6 * pulso)

    # Fade in / fade out para evitar chasquidos
    fade = min(int(0.25 * sr), len(onda) // 4)
    if fade > 0:
        onda[:fade] *= np.linspace(0, 1, fade)
        onda[-fade:] *= np.linspace(1, 0, fade)

    pcm = np.clip(onda * 32767, -32768, 32767).astype(np.int16)
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    buf.seek(0)
    return buf.read()


def interpretar_intencion_sueno(texto: str) -> str:
    t = texto.lower()
    if any(k in t for k in ["despert", "llor", "arriba", "alerta"]):
        return "DESPIERTO"
    if any(k in t for k in ["dormid", "durmio", "durmió", "se durmió", "ruido blanco"]):
        return "DORMIDO"
    if any(k in t for k in ["agua", "sed", "hidratar", "tomar"]):
        return "AGUA"
    return "RUTINA"


def registrar_evento_sueno(tipo_evento: str):
    st.session_state.eventos_sueno.append({
        "hora": datetime.now().strftime("%H:%M"),
        "evento": tipo_evento,
    })


def orientacion_por_edad(edad_meses: int, eventos: list[dict]) -> tuple[str, str]:
    """Devuelve diagnóstico orientativo y sugerencia práctica según edad en meses."""
    despertares = sum(1 for e in eventos if e["evento"] == "Despertó")
    dormidas = sum(1 for e in eventos if e["evento"] == "Bebé dormido")

    if edad_meses <= 3:
        ventana = "ventanas cortas (aprox. 45–90 min) y sueño fragmentado"
        sugerencia = (
            "A esta edad los ciclos de sueño son cortos y frecuentes. Prioriza señales suaves de "
            "sueño (bostezo, mirada perdida) antes de que llegue al cansancio excesivo."
        )
    elif edad_meses <= 6:
        ventana = "ventanas moderadas (aprox. 1.5–2.5 h) y consolidación gradual de siestas"
        sugerencia = (
            "Mantener una rutina nocturna breve y repetible (bajar luces, música suave y paso a "
            "ruido blanco) ayuda a asociar el cierre del día con calma."
        )
    elif edad_meses <= 12:
        ventana = "ventanas más amplias (aprox. 2.5–3.5 h) y siestas más estructuradas"
        sugerencia = (
            "Si notas despertares seguidos o resistencia a dormir, revisa si la última ventana de "
            "vigilia fue demasiado larga o corta para su ritmo actual."
        )
    else:
        ventana = "transición hacia 1–2 siestas y rutinas estables"
        sugerencia = (
            "Conserva un cierre tranquilo antes de acostarse y anticipa la transición unos minutos "
            "antes para facilitar el cambio de actividad."
        )

    if len(eventos) == 0:
        diagnostico = (
            f"Aún no hay registros hoy para un bebé de {edad_meses} mes(es). "
            f"Referencia orientativa: {ventana}."
        )
    else:
        diagnostico = (
            f"Bebé de {edad_meses} mes(es) · Registros hoy: {dormidas} dormida(s) y {despertares} despertar(es). "
            f"Referencia general: {ventana}."
        )

    return diagnostico, sugerencia


def activar_estado_cunna(estado_mqtt: str, etiqueta_evento: str | None = None):
    st.session_state.fase_rutina = estado_mqtt

    if etiqueta_evento:
        registrar_evento_sueno(etiqueta_evento)

    if estado_mqtt == "RUTINA":
        mensaje = (
            "Comenzamos la rutina de sueño. Bajamos el ritmo con música suave y calma; "
            "cuando el bebé se duerma puedes pasar a ruido blanco."
        )
    elif estado_mqtt == "DORMIDO":
        mensaje = (
            "Bebé dormido registrado. Activamos sonido ambiental suave tipo ruido blanco "
            "para acompañar su descanso."
        )
    elif estado_mqtt == "DESPIERTO":
        mensaje = (
            "Despertar registrado con cariño. Respira profundo; aquí tienes el registro listo "
            "para acompañar el momento."
        )
    elif estado_mqtt == "AGUA":
        st.session_state.vasos_agua += 1
        mensaje = (
            f"¡Qué buen cuidado! Llevas {st.session_state.vasos_agua} vaso(s) de agua hoy. "
            "Tu bienestar también importa."
        )
    else:
        mensaje = "Estado actualizado en CUNNA."

    st.session_state.ultimo_mensaje = mensaje

    ok_envio, detalle_envio = enviar_comando_mqtt(estado=estado_mqtt, origen="cunna_streamlit")
    estado_wokwi = leer_ultimo_estado_mqtt(timeout_seg=1.5)
    st.session_state.ultimo_estado_wokwi = estado_wokwi

    st.markdown(f"**Mensaje:** {mensaje}")

    audio_voz = generar_voz_gtts(mensaje)
    if audio_voz:
        st.audio(audio_voz, format="audio/mp3")

    if estado_mqtt == "RUTINA":
        st.caption("🎵 Música suave de rutina:")
        st.audio(generar_sonido_ambiente("arrullo"), format="audio/wav")
    elif estado_mqtt == "DORMIDO":
        st.caption("🌊 Ruido blanco suave para el descanso:")
        st.audio(generar_sonido_ambiente("ruido_blanco"), format="audio/wav")

    if ok_envio:
        st.success(detalle_envio)
    else:
        st.warning(detalle_envio)

    if estado_wokwi:
        st.info(f"Confirmación desde Wokwi ({TOPIC_ESTADO}): {estado_wokwi}")
    else:
        st.caption(
            f"Sin lectura nueva en {TOPIC_ESTADO} en este instante. "
            "Verifica que tu simulación en Wokwi esté corriendo y conectada al broker."
        )


# ---------------------------------------------------------
# Ambiente 1: Rutina de Sueño y Sonidos
# ---------------------------------------------------------
def pagina_rutina_y_sonidos():
    st.title("🌙 CUNNA · Rutina de Sueño y Sonidos")
    st.write(
        "Un espacio pensado para momentos con las manos ocupadas o de noche: "
        "activa la rutina, pasa a ruido blanco al dormir y recibe guía por voz y Wokwi."
    )

    st.session_state.edad_meses = st.slider(
        "Edad del bebé (en meses)",
        min_value=0,
        max_value=24,
        value=st.session_state.edad_meses,
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        btn_rutina = st.button("🎶 Comenzar rutina", use_container_width=True)
    with col_b:
        btn_dormido = st.button("💤 Bebé dormido", use_container_width=True)
    with col_c:
        btn_desperto = st.button("☀️ Despertó", use_container_width=True)

    texto_comando = st.text_input(
        "O escribe qué está pasando:",
        placeholder="Ej.: comenzar rutina de sueño, bebé dormido, despertó o tengo sed",
    )
    audio_entrada = st.audio_input("O graba una nota de voz:")
    if audio_entrada is not None:
        st.caption("Audio recibido. Pulsa 'Enviar nota' para sincronizar.")

    enviar_nota = st.button("Enviar nota", type="primary", use_container_width=True)

    st.divider()

    if btn_rutina:
        activar_estado_cunna("RUTINA", "Inicio de rutina de sueño")
    elif btn_dormido:
        activar_estado_cunna("DORMIDO", "Bebé dormido")
    elif btn_desperto:
        activar_estado_cunna("DESPIERTO", "Despertó")
    elif enviar_nota:
        intencion = interpretar_intencion_sueno(texto_comando)
        etiqueta_map = {
            "RUTINA": "Inicio de rutina de sueño",
            "DORMIDO": "Bebé dormido",
            "DESPIERTO": "Despertó",
            "AGUA": None,
        }
        activar_estado_cunna(intencion, etiqueta_map.get(intencion))
    else:
        st.write(f"**Estado actual:** `{st.session_state.fase_rutina}`")
        st.write(f"**Último mensaje:** {st.session_state.ultimo_mensaje}")


# ---------------------------------------------------------
# Ambiente 2: Monitor de Sueño y Cuidado de Mamá
# ---------------------------------------------------------
def pagina_monitor_y_mama():
    st.title("🤱 CUNNA · Monitor de Sueño y Cuidado de Mamá")
    st.write(
        "Revisa el registro de despertares y dormidas según la edad del bebé, "
        "consulta sugerencias orientativas y cuida también tu hidratación."
    )

    edad = st.slider(
        "Edad del bebé (en meses)",
        min_value=0,
        max_value=24,
        value=st.session_state.edad_meses,
        key="slider_edad_amb2",
    )
    st.session_state.edad_meses = edad

    c1, c2 = st.columns(2)
    with c1:
        if st.button("➕ Registrar despertar", use_container_width=True):
            activar_estado_cunna("DESPIERTO", "Despertó")
    with c2:
        if st.button("💧 Registrar vaso de agua (Mamá)", use_container_width=True):
            activar_estado_cunna("AGUA", None)

    st.divider()

    total_despertares = sum(
        1 for e in st.session_state.eventos_sueno if e["evento"] == "Despertó"
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("Edad del bebé", f"{st.session_state.edad_meses} meses")
    m2.metric("Despertares hoy", total_despertares)
    m3.metric("Vasos de agua (Mamá)", st.session_state.vasos_agua)

    diagnostico, sugerencia = orientacion_por_edad(
        st.session_state.edad_meses, st.session_state.eventos_sueno
    )
    st.info(f"**Lectura orientativa:** {diagnostico}")
    st.write(f"**Sugerencia para la próxima dormida:** {sugerencia}")
    st.caption(
        "Nota: esta información es de apoyo organizativo y referencia general según edad; "
        "no reemplaza la orientación de un profesional de la salud."
    )

    if st.session_state.eventos_sueno:
        st.subheader("Historial de registros de hoy")
        for item in reversed(st.session_state.eventos_sueno[-8:]):
            st.write(f"- **{item['hora']}** · {item['evento']}")

    st.divider()
    st.subheader("Conexión MQTT con Wokwi")
    st.write(f"**Comandos:** `{TOPIC_CMD}` · **Estado:** `{TOPIC_ESTADO}`")
    if st.session_state.ultimo_estado_wokwi:
        st.json(st.session_state.ultimo_estado_wokwi)


pg1 = st.Page(pagina_rutina_y_sonidos, title="Rutina y Sonidos", icon="🌙")
pg2 = st.Page(pagina_monitor_y_mama, title="Monitor y Mamá", icon="🤱")

nav = st.navigation([pg1, pg2])
nav.run()
