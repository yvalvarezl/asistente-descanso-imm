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
    .nombre-mama-destacado {
        font-size: 1.85rem;
        font-weight: 700;
        line-height: 1.2;
        margin-top: 0.2rem;
        margin-bottom: 0.35rem;
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
    st.session_state.edad_meses = 10
if "nombre_mama" not in st.session_state:
    st.session_state.nombre_mama = "Mamá"
if "edad_mama" not in st.session_state:
    st.session_state.edad_mama = 30
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

    st.divider()
    st.markdown(f"**Bebé:** {st.session_state.nombre_bebe} ({st.session_state.edad_meses} meses)")
    st.markdown(f"**Mamá:** {st.session_state.nombre_mama} ({st.session_state.edad_mama} años)")


def _etiqueta_bebe() -> str:
    nombre = st.session_state.nombre_bebe.strip()
    return nombre if nombre and nombre != "Mi bebé" else "tu bebé"


def _etiqueta_mama() -> str:
    nombre = st.session_state.nombre_mama.strip()
    return nombre if nombre and nombre != "Mamá" else "Mamá"


def _titulo_mama_grande() -> str:
    nombre = st.session_state.nombre_mama.strip()
    if nombre and nombre != "Mamá":
        return f"🤱 {nombre} · {st.session_state.edad_mama} años"
    return f"🤱 Mamá · {st.session_state.edad_mama} años"


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
    ahora = datetime.now()
    st.session_state.eventos_sueno.append(
        {
            "fecha": ahora.strftime("%Y-%m-%d"),
            "hora": ahora.strftime("%H:%M"),
            "ts": ahora.isoformat(),
            "evento": tipo_evento,
        }
    )


def _parsear_ts(evento: dict) -> datetime | None:
    if "ts" in evento:
        try:
            return datetime.fromisoformat(evento["ts"])
        except ValueError:
            pass
    try:
        hoy = datetime.now().strftime("%Y-%m-%d")
        fecha_str = evento.get("fecha", hoy)
        hora_str = evento.get("hora", "00:00")
        return datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def analizar_ventanas_y_sueno(
    nombre_bebe: str, edad_meses: int, eventos: list[dict]
) -> dict:
    """Evalúa ventanas de sueño y despertares seguidos con texto simple y claro."""
    bebe = nombre_bebe.strip() if nombre_bebe.strip() and nombre_bebe != "Mi bebé" else "tu bebé"
    mama = _etiqueta_mama()

    if edad_meses <= 3:
        ventana_destacada = "45–90 min"
        ventana_texto = "ventanas cortas (entre 45 y 90 minutos)"
        rafaga_corta_min = 35
    elif edad_meses <= 6:
        ventana_destacada = "1.5–2.5 h"
        ventana_texto = "ventanas moderadas (entre 1 hora y media y 2 horas y media)"
        rafaga_corta_min = 40
    elif edad_meses <= 12:
        ventana_destacada = "2.5–3.5 h"
        ventana_texto = "ventanas de 2 horas y media a 3 horas y media"
        rafaga_corta_min = 45
    else:
        ventana_destacada = "3–4.5 h"
        ventana_texto = "ventanas más amplias (entre 3 y 4 horas y media)"
        rafaga_corta_min = 45

    eventos_con_dt = []
    for ev in eventos:
        dt = _parsear_ts(ev)
        if dt is not None:
            eventos_con_dt.append((dt, ev["evento"]))
    eventos_con_dt.sort(key=lambda x: x[0])

    despertares_dt = [dt for dt, tipo in eventos_con_dt if tipo == "Despertó"]
    dormidas_dt = [dt for dt, tipo in eventos_con_dt if tipo == "Bebé dormido"]

    intervalos_despertares = [
        (despertares_dt[i] - despertares_dt[i - 1]).total_seconds() / 60.0
        for i in range(1, len(despertares_dt))
    ]
    rafagas_cortas = [m for m in intervalos_despertares if m <= rafaga_corta_min]
    menor_intervalo = min(intervalos_despertares) if intervalos_despertares else None

    ultimo_dt, ultimo_tipo = eventos_con_dt[-1] if eventos_con_dt else (None, None)
    mins_desde_ultimo = (
        (datetime.now() - ultimo_dt).total_seconds() / 60.0 if ultimo_dt else None
    )

    if not eventos_con_dt:
        return {
            "ventana_destacada": ventana_destacada,
            "estado_corto": "Sin registros aún",
            "resumen": f"Hoy todavía no has registrado despertares ni dormidas para {bebe}.",
            "diagnostico": (
                f"Para {edad_meses} meses, la referencia habitual es {ventana_texto}. "
                "Lo más importante es ver qué tan seguidos ocurren los despertares y cómo van las ventanas."
            ),
            "recomendacion": (
                f"Anota cuándo empieza la rutina, cuándo se duerme {bebe} y cuándo despierta para ver "
                "si el descanso es continuo o se corta muy rápido."
            ),
        }

    estado_actual = ""
    if ultimo_tipo == "Despertó" and mins_desde_ultimo is not None:
        estado_actual = f" Ahora lleva cerca de {int(round(mins_desde_ultimo))} minutos despierto/a."
    elif ultimo_tipo == "Bebé dormido" and mins_desde_ultimo is not None:
        estado_actual = f" Ahora lleva cerca de {int(round(mins_desde_ultimo))} minutos dormido/a."

    resumen = (
        f"Hoy se han registrado {len(despertares_dt)} despertares y {len(dormidas_dt)} dormidas "
        f"para {bebe}.{estado_actual}"
    )

    if rafagas_cortas:
        estado_corto = "Despertares muy seguidos"
        diagnostico = (
            f"Se notan despertares muy seguidos (uno de ellos a los {int(round(menor_intervalo))} minutos). "
            f"Que {bebe} se levante dos veces en poco tiempo —como media hora— no suele ser ideal en esta etapa "
            f"({ventana_texto}) y puede indicar que el descanso se está cortando antes de tiempo."
        )
        recomendacion = (
            f"Revisa si {bebe} llegó muy cansado a dormir, si el cuarto está tranquilo o si algún estímulo "
            f"lo despertó pronto; {mama}, toma un respiro breve y observa si vuelve a repetirse."
        )
    elif len(despertares_dt) >= 2 and menor_intervalo is not None and menor_intervalo < 75:
        estado_corto = "Intervalos cortos"
        diagnostico = (
            f"Hubo un despertar en un lapso corto ({int(round(menor_intervalo))} minutos entre levantadas). "
            f"Para {edad_meses} meses, la referencia general es {ventana_texto}."
        )
        recomendacion = (
            f"Cuida que {bebe} no pase demasiado despierto antes de la próxima siesta y mantén un cierre de rutina tranquilo."
        )
    else:
        estado_corto = "Ritmo tranquilo"
        diagnostico = (
            f"Por ahora no se ven despertares repetidos en intervalos muy cortos. "
            f"Referencia general para {edad_meses} meses: {ventana_texto}."
        )
        recomendacion = (
            f"Sigue con un ritmo suave y predecible para {bebe}, y aprovecha las pausas para que {mama} tome agua y descanse."
        )

    return {
        "ventana_destacada": ventana_destacada,
        "estado_corto": estado_corto,
        "resumen": resumen,
        "diagnostico": diagnostico,
        "recomendacion": recomendacion,
    }


def evaluar_hidratacion_y_autocuidado(vasos: int, nombre_mama: str) -> tuple[str, str, str]:
    """Evalúa el estado de hidratación según vasos registrados y ofrece recomendaciones para mamá."""
    mama = nombre_mama.strip() if nombre_mama.strip() and nombre_mama != "Mamá" else "Mamá"
    meta_diaria = 8

    if vasos == 0:
        estado = f"⚠️ Aún no has registrado vasos de agua hoy ({vasos}/{meta_diaria})."
        mensaje = (
            f"{mama}, te estás hidratando mal por ahora: llevas 0 vasos registrados. "
            "Tener una botella cerca ayuda mucho cuando estás pendiente del bebé."
        )
        recomendaciones = (
            "• Toma 1 vaso de agua ahora mismo mientras revisas el resumen.\n"
            "• Deja un vaso o termo visible donde sueles sentarte con tu bebé.\n"
            "• Acompaña tu hidratación con un snack sencillo y una respiración pausada."
        )
    elif vasos < 4:
        estado = f"🟡 Hidratación baja por ahora ({vasos}/{meta_diaria} vasos)."
        mensaje = (
            f"{mama}, vas empezando, pero aún te estás hidratando poco ({vasos} de {meta_diaria} vasos). "
            "Un par de sorbos más entre rutinas marcarán la diferencia."
        )
        recomendaciones = (
            f"• Proponte completar al menos {4 - vasos} vasos más antes de la tarde/noche.\n"
            "• Toma agua justo después de cada despertar o cambio de rutina.\n"
            "• Si sientes cansancio acumulado, estira hombros y cuello por 1 minuto."
        )
    elif vasos < meta_diaria:
        estado = f"💧 Hidratación en buen camino ({vasos}/{meta_diaria} vasos)."
        mensaje = (
            f"¡Muy bien, {mama}! Te estás hidratando bien: llevas {vasos} vasos registrados y estás "
            f"a {meta_diaria - vasos} de tu meta diaria de {meta_diaria}."
        )
        recomendaciones = (
            f"• Sigue así: vas por buen ritmo con {vasos} vasos.\n"
            "• Aprovecha los momentos de calma del bebé para beber un vaso más.\n"
            "• Recuerda comer algo nutritivo y darte un pequeño respiro mental."
        )
    else:
        estado = f"✅ ¡Excelente hidratación hoy! ({vasos}/{meta_diaria}+ vasos)."
        mensaje = (
            f"¡Qué gran cuidado, {mama}! Te estás hidratando muy bien con {vasos} vasos registrados hoy. "
            "Cuidarte también es sostener a tu bebé."
        )
        recomendaciones = (
            "• Mantén este hábito constante durante el resto del día.\n"
            "• Prioriza el descanso cuando el bebé duerma si tienes pendientes no urgentes.\n"
            "• Pide apoyo si necesitas una pausa real para comer o descansar."
        )

    return estado, mensaje, recomendaciones


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
            "y el resumen de ventanas listos."
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
    bebe = _etiqueta_bebe()
    mama = _etiqueta_mama()

    st.title("🤱 CUNNA · Resumen o diagnóstico / Cuidado mamá")
    st.markdown(
        f"<div class='nombre-mama-destacado'>{_titulo_mama_grande()}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='subexplicacion-rutina'>{mama}, lo estás haciendo muy bien 💛 · "
        f"A continuación verás cómo van las ventanas y el descanso de {bebe} ({st.session_state.edad_meses} meses) "
        "y un espacio pensado para tu hidratación y cuidado.</div>",
        unsafe_allow_html=True,
    )

    analisis = analizar_ventanas_y_sueno(
        st.session_state.nombre_bebe,
        st.session_state.edad_meses,
        st.session_state.eventos_sueno,
    )

    m1, m2 = st.columns(2)
    m1.metric("Ventana de referencia", analisis["ventana_destacada"])
    m2.metric("Lectura de hoy", analisis["estado_corto"])

    st.subheader(f"📋 Ventanas y Resumen del Sueño de {bebe.capitalize()}")
    st.write(f"**Resumen:** {analisis['resumen']}")
    st.info(f"**Qué se observa:** {analisis['diagnostico']}")
    st.write(f"**Para la próxima dormida:** {analisis['recomendacion']}")
    st.caption(
        "Nota: orientación organizativa y de referencia general según edad; "
        "no constituye diagnóstico médico ni reemplaza la orientación pediátrica."
    )

    if st.session_state.eventos_sueno:
        st.caption("Últimos registros de hoy:")
        for item in reversed(st.session_state.eventos_sueno[-6:]):
            st.write(f"- **{item['hora']}** · {item['evento']}")

    st.divider()

    # Registro de vasos de agua de mamá + diagnóstico de hidratación y recomendaciones a la par
    st.subheader(f"💧 Hidratación y Cuidado de {mama}")
    col_agua_reg, col_agua_eval = st.columns([1, 1.5], gap="large")

    with col_agua_reg:
        st.metric("Vasos de agua hoy", f"{st.session_state.vasos_agua} 💧")
        st.markdown("<div class='emoji-gigante-barra'>💧</div>", unsafe_allow_html=True)
        if st.button("+1 Vaso de agua", type="primary", use_container_width=True):
            activar_estado_cunna("AGUA", None)
            st.rerun()

    estado_hidra, msg_hidra, recs_mama = evaluar_hidratacion_y_autocuidado(
        st.session_state.vasos_agua, st.session_state.nombre_mama
    )
    with col_agua_eval:
        st.markdown(f"**Estado de hidratación:** {estado_hidra}")
        st.write(msg_hidra)
        st.markdown("**Recomendaciones para ti:**")
        st.markdown(recs_mama)

    st.divider()
    mostrar_mensaje_con_bocina(st.session_state.ultimo_mensaje)
    renderizar_reproductor_continuo()

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
