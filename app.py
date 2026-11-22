from io import BytesIO
from datetime import datetime
from pathlib import Path
import wave
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
    layout="wide",
)

CARPETA_BASE = Path(__file__).parent
RUTA_ESTRELLITA_RAIZ = CARPETA_BASE / "assetsestrellita_piano.mp3"
RUTA_ESTRELLITA_ASSETS = CARPETA_BASE / "assets" / "estrellita_piano.mp3"

# ---------------------------------------------------------
# Estilos suaves, botones grandes y baja carga cognitiva
# ---------------------------------------------------------
st.markdown(
    """
    <style>
    .acompanando-destacado {
        font-size: 1.32rem;
        font-weight: 600;
        line-height: 1.35;
        margin-top: 0.15rem;
        margin-bottom: 0.3rem;
    }
    .subexplicacion-rutina {
        font-size: 0.98rem;
        line-height: 1.5;
        opacity: 0.88;
        margin-bottom: 1.1rem;
    }
    .mensaje-box {
        background-color: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 14px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.75rem;
    }
    .bocina-label {
        font-size: 1.4rem;
        text-align: center;
        padding-top: 0.3rem;
    }
    /* Botones principales más grandes con emojis destacados */
    div[data-testid="stButton"] > button[kind="secondary"],
    div[data-testid="stButton"] > button[kind="primary"] {
        min-height: 4.4rem;
        font-size: 1.15rem;
        font-weight: 600;
        border-radius: 14px;
        padding: 0.75rem 1rem;
    }
    .emoji-gigante-barra {
        display: flex;
        justify-content: space-around;
        font-size: 2.35rem;
        line-height: 1.1;
        margin-bottom: 0.25rem;
        user-select: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# Estado de sesión persistente entre ambientes
# ---------------------------------------------------------
if "fase_rutina" not in st.session_state:
    st.session_state.fase_rutina = "EN_CALMA"
if "sonido_activo" not in st.session_state:
    st.session_state.sonido_activo = None  # "estrellita" | "ruido_blanco" | None
if "nombre_bebe" not in st.session_state:
    st.session_state.nombre_bebe = "Mi bebé"
if "edad_meses" not in st.session_state:
    st.session_state.edad_meses = 4
if "nombre_mama" not in st.session_state:
    st.session_state.nombre_mama = "Mamá"
if "edad_mama" not in st.session_state:
    st.session_state.edad_mama = 30
if "meta_mama" not in st.session_state:
    st.session_state.meta_mama = "Hidratación y pausas de descanso"
if "eventos_sueno" not in st.session_state:
    st.session_state.eventos_sueno = []
if "vasos_agua" not in st.session_state:
    st.session_state.vasos_agua = 0
if "ultimo_mensaje" not in st.session_state:
    st.session_state.ultimo_mensaje = (
        "Bienvenida a CUNNA. Un espacio suave para acompañar el sueño y tu descanso."
    )
if "ultimo_estado_wokwi" not in st.session_state:
    st.session_state.ultimo_estado_wokwi = None
if "ultimo_detalle_mqtt" not in st.session_state:
    st.session_state.ultimo_detalle_mqtt = None


# ---------------------------------------------------------
# Barra lateral izquierda: Perfil del bebé y Perfil de mamá
# ---------------------------------------------------------
with st.sidebar:
    st.header("👶 Perfil del Bebé")
    st.caption("Personaliza los datos para adaptar los mensajes y el resumen.")

    nombre_bebe_input = st.text_input(
        "Nombre del bebé",
        value=st.session_state.nombre_bebe,
        placeholder="Ej.: Sofía, Mateo...",
    )
    st.session_state.nombre_bebe = (
        nombre_bebe_input.strip() if nombre_bebe_input.strip() else "Mi bebé"
    )

    st.session_state.edad_meses = st.slider(
        "Edad del bebé en meses",
        min_value=0,
        max_value=24,
        value=st.session_state.edad_meses,
        key="slider_sidebar_edad",
    )

    st.divider()
    st.header("🤱 Perfil de Mamá")
    st.caption("Datos de acompañamiento y autocuidado diario.")

    nombre_mama_input = st.text_input(
        "Nombre de mamá",
        value=st.session_state.nombre_mama,
        placeholder="Ej.: Valeria, Camila...",
    )
    st.session_state.nombre_mama = (
        nombre_mama_input.strip() if nombre_mama_input.strip() else "Mamá"
    )

    st.session_state.edad_mama = st.slider(
        "Edad de mamá (años)",
        min_value=15,
        max_value=60,
        value=st.session_state.edad_mama,
        key="slider_sidebar_edad_mama",
    )

    meta_mama_input = st.text_input(
        "Enfoque de cuidado hoy",
        value=st.session_state.meta_mama,
        placeholder="Ej.: Tomar 8 vasos de agua, dormir siestas...",
    )
    st.session_state.meta_mama = (
        meta_mama_input.strip()
        if meta_mama_input.strip()
        else "Hidratación y pausas de descanso"
    )

    st.divider()
    st.markdown(f"**Bebé:** {st.session_state.nombre_bebe} ({st.session_state.edad_meses} meses)")
    st.markdown(f"**Mamá:** {st.session_state.nombre_mama} ({st.session_state.edad_mama} años)")


def _etiqueta_bebe() -> str:
    nombre = st.session_state.nombre_bebe.strip()
    return nombre if nombre and nombre != "Mi bebé" else "tu bebé"


def _etiqueta_mama() -> str:
    nombre = st.session_state.nombre_mama.strip()
    return nombre if nombre and nombre != "Mamá" else "mamá"


def texto_acompanando_bebe() -> str:
    return f"acompañando a {_etiqueta_bebe()} de {st.session_state.edad_meses} meses"


# ---------------------------------------------------------
# Funciones de audio (voz bajo demanda + sonido en loop)
# ---------------------------------------------------------
@st.cache_data(show_spinner=False)
def generar_voz_gtts(texto: str) -> bytes | None:
    try:
        tts = gTTS(text=texto, lang="es")
        buf = BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def _nota_suave(freq: float, duracion: float, sr: int = 16000, amp: float = 0.09) -> np.ndarray:
    """Genera una nota de cuna cálida con armónicos suaves y envolvente sin clics."""
    n = max(1, int(sr * duracion))
    t = np.linspace(0, duracion, n, endpoint=False)
    onda = (
        0.75 * np.sin(2 * np.pi * freq * t)
        + 0.20 * np.sin(2 * np.pi * (2 * freq) * t)
        + 0.05 * np.sin(2 * np.pi * (3 * freq) * t)
    )
    ataque = min(int(0.06 * sr), n // 3)
    liberacion = min(int(0.10 * sr), n // 3)
    env = np.ones(n)
    if ataque > 0:
        env[:ataque] = np.linspace(0.0, 1.0, ataque)
    if liberacion > 0:
        env[-liberacion:] = np.linspace(1.0, 0.0, liberacion)
    return amp * onda * env


@st.cache_data(show_spinner=False)
def generar_sonido_continuo(tipo: str, duracion_seg: float = 16.0, sr: int = 16000) -> bytes:
    """Genera audio WAV continuo en bucle para respaldo de canción de cuna o ruido blanco."""
    if tipo == "ruido_blanco":
        t = np.linspace(0, duracion_seg, int(sr * duracion_seg), endpoint=False)
        frecuencia_ciclo = 1.0 / duracion_seg
        rng = np.random.default_rng(42)
        ruido = rng.normal(0.0, 0.13, size=t.shape)
        kernel = np.ones(14) / 14.0
        onda = np.convolve(ruido, kernel, mode="same")
        modulacion = 0.88 + 0.12 * np.sin(2 * np.pi * frecuencia_ciclo * t)
        onda = onda * modulacion
    else:
        notas = [
            (261.63, 0.65),
            (261.63, 0.65),
            (392.00, 0.65),
            (392.00, 0.65),
            (440.00, 0.65),
            (440.00, 0.65),
            (392.00, 1.30),
            (349.23, 0.65),
            (349.23, 0.65),
            (329.63, 0.65),
            (329.63, 0.65),
            (293.66, 0.65),
            (293.66, 0.65),
            (261.63, 1.45),
        ]
        segmentos = [_nota_suave(f, d, sr=sr, amp=0.095) for f, d in notas]
        onda = np.concatenate(segmentos)

    pcm = np.clip(onda * 32767, -32768, 32767).astype(np.int16)
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    buf.seek(0)
    return buf.read()


def mostrar_mensaje_con_bocina(mensaje: str):
    """Muestra el mensaje escrito y un control compacto de bocina (🔊) para escucharlo si se desea."""
    col_txt, col_ico, col_aud = st.columns([6.5, 0.7, 2.8], vertical_alignment="center")
    with col_txt:
        st.markdown(f"<div class='mensaje-box'>{mensaje}</div>", unsafe_allow_html=True)
    with col_ico:
        st.markdown("<div class='bocina-label'>🔊</div>", unsafe_allow_html=True)
    with col_aud:
        audio_voz = generar_voz_gtts(mensaje)
        if audio_voz:
            st.audio(audio_voz, format="audio/mp3", autoplay=False)


def renderizar_reproductor_continuo():
    """Muestra el audio automático en loop según el estado actual de rutina/sueño."""
    if st.session_state.sonido_activo == "estrellita":
        archivo_piano = (
            RUTA_ESTRELLITA_RAIZ
            if RUTA_ESTRELLITA_RAIZ.exists()
            else RUTA_ESTRELLITA_ASSETS
            if RUTA_ESTRELLITA_ASSETS.exists()
            else None
        )
        if archivo_piano is not None:
            st.caption("⭐ Canción de cuna Estrellita al piano activa en bucle automático:")
            st.audio(
                archivo_piano.read_bytes(),
                format="audio/mp3",
                autoplay=True,
                loop=True,
            )
        else:
            st.warning(
                "No se encontró `assetsestrellita_piano.mp3` ni `assets/estrellita_piano.mp3` en el repositorio; "
                "reproduciendo melodía de respaldo."
            )
            st.audio(
                generar_sonido_continuo("estrellita"),
                format="audio/wav",
                autoplay=True,
                loop=True,
            )
    elif st.session_state.sonido_activo == "ruido_blanco":
        st.caption("🌊 Ruido blanco activo en bucle automático para el descanso:")
        st.audio(
            generar_sonido_continuo("ruido_blanco"),
            format="audio/wav",
            autoplay=True,
            loop=True,
        )


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
    st.session_state.eventos_sueno.append(
        {
            "hora": datetime.now().strftime("%H:%M"),
            "evento": tipo_evento,
        }
    )


def resumen_y_diagnostico_despertares(
    nombre_bebe: str, edad_meses: int, eventos: list[dict]
) -> tuple[str, str, str]:
    """Genera resumen, diagnóstico orientativo según edad y levantadas, y recomendación."""
    bebe = nombre_bebe.strip() if nombre_bebe.strip() and nombre_bebe != "Mi bebé" else "tu bebé"
    mama = _etiqueta_mama()
    levantadas = sum(1 for e in eventos if e["evento"] == "Despertó")
    dormidas = sum(1 for e in eventos if e["evento"] == "Bebé dormido")
    rutinas = sum(1 for e in eventos if e["evento"] == "Inicio de rutina de sueño")

    if edad_meses <= 3:
        ventana = "ventanas cortas de unos 45 a 90 minutos y despertares frecuentes por alimentación o ciclos cortos"
        umbral_alto = 5
    elif edad_meses <= 6:
        ventana = "ventanas moderadas de 1.5 a 2.5 horas con consolidación gradual"
        umbral_alto = 4
    elif edad_meses <= 12:
        ventana = "ventanas amplias de 2.5 a 3.5 horas y siestas más estructuradas"
        umbral_alto = 3
    else:
        ventana = "transición hacia 1 o 2 siestas y rutinas estables"
        umbral_alto = 2

    if len(eventos) == 0:
        resumen = f"Hoy aún no has registrado levantadas ni dormidas para {bebe} de {edad_meses} meses."
        diagnostico = (
            f"Sin registros todavía para evaluar el patrón de hoy. Referencia orientativa: {ventana}."
        )
        recomendacion = (
            f"Cuando inicie la próxima dormida de {bebe}, usa 'Comenzar rutina' y observa señales "
            f"tempranas de sueño antes de que llegue al cansancio excesivo; recuerda también cuidar a {mama}."
        )
        return resumen, diagnostico, recomendacion

    resumen = (
        f"Resumen de hoy para {bebe} de {edad_meses} meses: se han registrado {levantadas} levantadas, "
        f"{dormidas} momentos dormido y {rutinas} inicios de rutina."
    )

    if levantadas == 0 and dormidas > 0:
        diagnostico = (
            f"Patrón tranquilo hasta ahora: {bebe} ha dormido sin levantadas registradas hoy "
            f"(referencia para {edad_meses} meses: {ventana})."
        )
        recomendacion = (
            f"Mantén el entorno calmo y constante; aprovecha este respiro para que {mama} hidrate y descanse."
        )
    elif levantadas <= max(1, umbral_alto - 2):
        diagnostico = (
            f"Frecuencia moderada con {levantadas} levantadas, acorde con una etapa en la que se esperan "
            f"ajustes naturales ({ventana})."
        )
        recomendacion = (
            f"Para la próxima dormida de {bebe}, procura un cierre de rutina similar y un ambiente "
            "tranquilo con ruido blanco suave si suele ayudarle a enlazar ciclos."
        )
    elif levantadas < umbral_alto:
        diagnostico = (
            f"Se observan {levantadas} levantadas, un nivel algo activo para {edad_meses} meses "
            f"si se compara con {ventana}."
        )
        recomendacion = (
            "Revisa si la última ventana de vigilia antes de dormir fue demasiado larga o si hubo "
            "sobreestimulación antes de acostarse; procura bajar estímulos con anticipación."
        )
    else:
        diagnostico = (
            f"Alerta de sueño fragmentado: {levantadas} levantadas registradas hoy, lo cual es "
            f"frecuente o exigente para {edad_meses} meses con {ventana}."
        )
        recomendacion = (
            f"Prioriza una rutina breve y predecible en cada dormida, cuida la temperatura y luz del "
            f"espacio y procura que {mama} tenga una pausa breve de agua o descanso."
        )

    return resumen, diagnostico, recomendacion


def activar_estado_cunna(estado_mqtt: str, etiqueta_evento: str | None = None):
    st.session_state.fase_rutina = estado_mqtt
    bebe = _etiqueta_bebe()
    mama = _etiqueta_mama()

    if etiqueta_evento:
        registrar_evento_sueno(etiqueta_evento)

    if estado_mqtt == "RUTINA":
        st.session_state.sonido_activo = "estrellita"
        mensaje = (
            f"Comenzamos la rutina de sueño para {bebe}. Se activó la canción de cuna en bucle; "
            f"cuando {bebe} se duerma puedes pasar a ruido blanco."
        )
    elif estado_mqtt == "DORMIDO":
        st.session_state.sonido_activo = "ruido_blanco"
        mensaje = (
            f"{bebe.capitalize()} dormido registrado. Cambiamos automáticamente a ruido blanco en bucle "
            "para acompañar su descanso."
        )
    elif estado_mqtt == "DESPIERTO":
        st.session_state.sonido_activo = None
        mensaje = (
            f"Se registró que {bebe} se levantó. Respira profundo, {mama}; aquí tienes el registro "
            "y el resumen listos."
        )
    elif estado_mqtt == "AGUA":
        st.session_state.vasos_agua += 1
        mensaje = (
            f"¡Qué buen cuidado, {mama}! Llevas {st.session_state.vasos_agua} vasos de agua hoy. "
            "Tu bienestar también importa."
        )
    else:
        mensaje = "Estado actualizado en CUNNA."

    st.session_state.ultimo_mensaje = mensaje

    ok_envio, detalle_envio = enviar_comando_mqtt(estado=estado_mqtt, origen="cunna_streamlit")
    st.session_state.ultimo_detalle_mqtt = (ok_envio, detalle_envio)
    estado_wokwi = leer_ultimo_estado_mqtt(timeout_seg=1.5)
    if estado_wokwi is not None:
        st.session_state.ultimo_estado_wokwi = estado_wokwi


def renderizar_estado_mqtt():
    if st.session_state.ultimo_detalle_mqtt:
        ok_envio, detalle_envio = st.session_state.ultimo_detalle_mqtt
        if ok_envio:
            st.success(detalle_envio)
        else:
            st.warning(detalle_envio)

    if st.session_state.ultimo_estado_wokwi:
        st.info(f"Confirmación desde Wokwi {TOPIC_ESTADO}: {st.session_state.ultimo_estado_wokwi}")
    else:
        st.caption(
            f"Sin lectura nueva en {TOPIC_ESTADO} en este instante. "
            "Verifica que tu simulación en Wokwi esté corriendo y conectada al broker."
        )


# ---------------------------------------------------------
# Ambiente 1: Rutina de Sueño y Sonidos
# ---------------------------------------------------------
def pagina_rutina_y_sonidos():
    bebe = _etiqueta_bebe()
    st.title("🌙 CUNNA · Rutina de Sueño y Sonidos")
    st.markdown(
        f"<div class='acompanando-destacado'>Acompañando a {bebe} de {st.session_state.edad_meses} meses</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='subexplicacion-rutina'>Activa la rutina con canción de cuna en bucle, "
        "pasa a ruido blanco al dormir y escucha los mensajes solo cuando tú lo decidas.</div>",
        unsafe_allow_html=True,
    )

    col_a, col_b, col_c = st.columns(3, gap="medium")
    with col_a:
        st.markdown("<div class='emoji-gigante-barra'>🎶</div>", unsafe_allow_html=True)
        btn_rutina = st.button("Comenzar rutina", use_container_width=True)
    with col_b:
        st.markdown("<div class='emoji-gigante-barra'>💤</div>", unsafe_allow_html=True)
        btn_dormido = st.button("Bebé dormido", use_container_width=True)
    with col_c:
        st.markdown("<div class='emoji-gigante-barra'>☀️</div>", unsafe_allow_html=True)
        btn_desperto = st.button("Despertó", use_container_width=True)

    texto_comando = st.text_input(
        "O escribe qué está pasando:",
        placeholder=f"Ej.: comenzar rutina de sueño, {bebe} dormido, despertó o tengo sed",
    )

    col_audio, col_enviar = st.columns([3, 1], gap="small", vertical_alignment="bottom")
    with col_audio:
        audio_entrada = st.audio_input("O graba una nota de voz:")
    with col_enviar:
        enviar_nota = st.button("Enviar nota", type="primary", use_container_width=True)

    if audio_entrada is not None:
        st.caption("Audio recibido. Pulsa 'Enviar nota' para sincronizar.")

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

    st.divider()
    st.caption(f"Estado actual: {st.session_state.fase_rutina}")
    mostrar_mensaje_con_bocina(st.session_state.ultimo_mensaje)
    renderizar_reproductor_continuo()
    renderizar_estado_mqtt()


# ---------------------------------------------------------
# Ambiente 2: Resumen o diagnóstico / Cuidado mamá
# ---------------------------------------------------------
def pagina_monitor_y_mama():
    st.title("🤱 CUNNA · Resumen o diagnóstico / Cuidado mamá")
    st.markdown(
        f"<div class='acompanando-destacado'>Seguimiento {texto_acompanando_bebe()}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='subexplicacion-rutina'>Resumen según las veces que se ha levantado, "
        "sugerencias orientativas y cuidado de mamá.</div>",
        unsafe_allow_html=True,
    )

    st.caption(
        f"**Perfil de mamá:** {st.session_state.nombre_mama} · {st.session_state.edad_mama} años · "
        f"*Enfoque:* {st.session_state.meta_mama}"
    )

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.markdown("<div class='emoji-gigante-barra'>☀️</div>", unsafe_allow_html=True)
        if st.button("Registrar levantada", use_container_width=True):
            activar_estado_cunna("DESPIERTO", "Despertó")
    with c2:
        st.markdown("<div class='emoji-gigante-barra'>💧</div>", unsafe_allow_html=True)
        if st.button("Registrar vaso de agua Mamá", use_container_width=True):
            activar_estado_cunna("AGUA", None)

    st.divider()

    total_levantadas = sum(
        1 for e in st.session_state.eventos_sueno if e["evento"] == "Despertó"
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("Bebé y edad", f"{_etiqueta_bebe().capitalize()} · {st.session_state.edad_meses} meses")
    m2.metric("Levantadas hoy", total_levantadas)
    m3.metric("Vasos de agua Mamá", st.session_state.vasos_agua)

    mostrar_mensaje_con_bocina(st.session_state.ultimo_mensaje)
    renderizar_reproductor_continuo()

    resumen, diagnostico, recomendacion = resumen_y_diagnostico_despertares(
        st.session_state.nombre_bebe,
        st.session_state.edad_meses,
        st.session_state.eventos_sueno,
    )
    st.subheader("📋 Resumen y Diagnóstico Orientativo")
    st.write(f"**Resumen:** {resumen}")
    st.info(f"**Diagnóstico según levantadas y edad:** {diagnostico}")
    st.write(f"**Recomendación para la próxima dormida:** {recomendacion}")
    st.caption(
        "Nota: este resumen y diagnóstico son de apoyo organizativo y referencia general según edad; "
        "no constituyen diagnóstico médico ni reemplazan la orientación pediátrica."
    )

    if st.session_state.eventos_sueno:
        st.subheader("Historial de registros de hoy")
        for item in reversed(st.session_state.eventos_sueno[-8:]):
            st.write(f"- **{item['hora']}** · {item['evento']}")

    st.divider()
    st.subheader("Conexión MQTT con Wokwi")
    st.write(f"**Comandos:** {TOPIC_CMD} · **Estado:** {TOPIC_ESTADO}")
    if st.session_state.ultimo_estado_wokwi:
        st.json(st.session_state.ultimo_estado_wokwi)


pg1 = st.Page(pagina_rutina_y_sonidos, title="Rutina y Sonidos", icon="🌙")
pg2 = st.Page(
    pagina_monitor_y_mama,
    title="Resumen o diagnóstico / Cuidado mamá",
    icon="🤱",
)

nav = st.navigation([pg1, pg2])
nav.run()
