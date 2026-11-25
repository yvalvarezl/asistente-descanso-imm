from datetime import datetime
from io import BytesIO
from pathlib import Path
from gtts import gTTS
import streamlit as st
from mqtt_bridge import (
    TOPIC_CMD,
    TOPIC_ESTADO,
    enviar_comando_mqtt,
    leer_ultimo_estado_mqtt,
)

st.set_page_config(
    page_title="CUNNA · Rutina de Sueño y Cuidado",
    page_icon="🌙",
    layout="wide",
)

CARPETA_BASE = Path(__file__).parent
RUTA_ESTRELLITA = (
    CARPETA_BASE / "assetsestrellita_piano.mp3"
    if (CARPETA_BASE / "assetsestrellita_piano.mp3").exists()
    else CARPETA_BASE / "assets" / "estrellita_piano.mp3"
)

st.markdown(
    """
    <style>
    .box-card {
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 12px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.75rem;
    }
    .emoji-top {
        text-align: center;
        font-size: 2.2rem;
        line-height: 1.1;
    }
    div[data-testid="stButton"] > button {
        min-height: 3.6rem;
        border-radius: 12px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Estado de sesión
defaults = {
    "fase_rutina": "EN_CALMA",
    "sonido_activo": False,
    "nombre_bebe": "Mi bebé",
    "edad_meses": 10,
    "nombre_mama": "Mamá",
    "edad_mama": 30,
    "eventos_sueno": [],
    "vasos_agua": 0,
    "mostrar_historial": False,
    "transcripcion_voz": None,
    "error_voz": None,
    "ultimo_mensaje": "Bienvenida a CUNNA. Un espacio suave para acompañar el sueño y tu descanso.",
    "ultimo_estado_wokwi": None,
    "ultimo_detalle_mqtt": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Barra lateral
with st.sidebar:
    st.header("👶 Perfil del Bebé")
    b_input = st.text_input("Nombre del bebé", value=st.session_state.nombre_bebe)
    st.session_state.nombre_bebe = b_input.strip() or "Mi bebé"
    st.session_state.edad_meses = st.slider("Edad (meses)", 0, 24, st.session_state.edad_meses)

    st.divider()
    st.header("🤱 Perfil de Mamá")
    m_input = st.text_input("Nombre de mamá", value=st.session_state.nombre_mama)
    st.session_state.nombre_mama = m_input.strip() or "Mamá"
    st.session_state.edad_mama = st.slider("Edad de mamá", 15, 60, st.session_state.edad_mama)


def bebe_lbl() -> str:
    n = st.session_state.nombre_bebe.strip()
    return n if n and n != "Mi bebé" else "tu bebé"


def mama_lbl() -> str:
    n = st.session_state.nombre_mama.strip()
    return n if n and n != "Mamá" else "Mamá"


def transcribir_voz(audio_file) -> tuple[str | None, str | None]:
    if audio_file is None:
        return None, "No se grabó ningún audio."
    try:
        import speech_recognition as sr

        r = sr.Recognizer()
        with sr.AudioFile(BytesIO(audio_file.getvalue())) as src:
            data = r.record(src)
        return r.recognize_google(data, language="es-CO").strip(), None
    except Exception as exc:
        return None, f"No se pudo transcribir el audio: {exc}"


@st.cache_data(show_spinner=False)
def voz_gtts(texto: str) -> bytes | None:
    try:
        buf = BytesIO()
        gTTS(text=texto, lang="es").write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def mostrar_mensaje_y_audio(mensaje: str):
    c1, c2 = st.columns([7, 3], vertical_alignment="center")
    c1.markdown(f"<div class='box-card'>{mensaje}</div>", unsafe_allow_html=True)
    audio = voz_gtts(mensaje)
    if audio:
        c2.audio(audio, format="audio/mp3")


def mostrar_reproductor():
    if not st.session_state.sonido_activo:
        return
    if RUTA_ESTRELLITA.exists():
        st.caption("⭐ Estrellita al piano en bucle:")
        st.audio(RUTA_ESTRELLITA.read_bytes(), format="audio/mp3", autoplay=True, loop=True)
    else:
        st.warning("No se encontró el archivo MP3 de Estrellita en el repositorio.")
    if st.button("⏹️ Detener sonido", key="stop_audio"):
        st.session_state.sonido_activo = False
        st.rerun()


def registrar_evento(tipo: str):
    ahora = datetime.now()
    st.session_state.eventos_sueno.append(
        {
            "fecha": ahora.strftime("%Y-%m-%d"),
            "hora": ahora.strftime("%I:%M:%S %p"),
            "ts": ahora,
            "evento": tipo,
        }
    )


def detectar_intencion(texto: str) -> str:
    t = texto.lower()
    if any(k in t for k in ["despert", "llor", "arriba", "levant"]):
        return "DESPIERTO"
    if any(k in t for k in ["dormid", "durmi", "descans"]):
        return "DORMIDO"
    if any(k in t for k in ["agua", "sed", "hidrat"]):
        return "AGUA"
    return "RUTINA"


def activar_estado(estado: str, etiqueta_evento: str | None = None):
    st.session_state.fase_rutina = estado
    bebe, mama = bebe_lbl(), mama_lbl()
    if etiqueta_evento:
        registrar_evento(etiqueta_evento)

    mensajes = {
        "RUTINA": f"Iniciamos la rutina de sueño para {bebe} y activamos la canción de cuna.",
        "DORMIDO": f"{bebe.capitalize()} dormido registrado. Acompañando su descanso.",
        "DESPIERTO": f"Se registró que {bebe} despertó. Ánimo, {mama}.",
        "AGUA": None,
    }
    if estado == "AGUA":
        st.session_state.vasos_agua += 1
        st.session_state.ultimo_mensaje = (
            f"¡Bien hecho, {mama}! Llevas {st.session_state.vasos_agua} vasos de agua hoy."
        )
    else:
        st.session_state.sonido_activo = estado in ("RUTINA", "DORMIDO")
        st.session_state.ultimo_mensaje = mensajes.get(estado, "Estado actualizado.")

    st.session_state.ultimo_detalle_mqtt = enviar_comando_mqtt(
        estado=estado, origen="cunna_streamlit"
    )
    estado_wk = leer_ultimo_estado_mqtt(timeout_seg=1.5)
    if estado_wk is not None:
        st.session_state.ultimo_estado_wokwi = estado_wk


def analizar_sueno(edad: int, eventos: list[dict]) -> dict:
    bebe, mama = bebe_lbl(), mama_lbl()
    if edad <= 3:
        ventana, lim = "45–90 min", 35
    elif edad <= 6:
        ventana, lim = "1.5–2.5 h", 40
    elif edad <= 12:
        ventana, lim = "2.5–3.5 h", 45
    else:
        ventana, lim = "3–4.5 h", 45

    ordenados = sorted(
        [(e["ts"], e["evento"]) for e in eventos if isinstance(e.get("ts"), datetime)],
        key=lambda x: x[0],
    )
    desp = [dt for dt, ev in ordenados if ev == "Despertó"]
    dorm = [dt for dt, ev in ordenados if ev == "Bebé dormido"]

    if not ordenados:
        return {
            "ventana": ventana,
            "estado": "Sin registros",
            "resumen": f"Aún no hay registros hoy para {bebe}.",
            "observacion": f"Referencia habitual para {edad} meses: {ventana}.",
            "sugerencia": f"Registra rutinas, dormidas y despertares de {bebe} para observar su ritmo.",
        }

    intervalos = [(desp[i] - desp[i - 1]).total_seconds() / 60 for i in range(1, len(desp))]
    cortos = [m for m in intervalos if m <= lim]
    resumen = f"Hoy: {len(desp)} despertares y {len(dorm)} dormidas para {bebe}."

    if cortos:
        return {
            "ventana": ventana,
            "estado": "Despertares seguidos",
            "resumen": resumen,
            "observacion": f"Se detectó un intervalo corto ({int(round(min(cortos)))} min) entre despertares.",
            "sugerencia": f"Revisa el ambiente y el cansancio previo de {bebe}; {mama}, toma un respiro breve.",
        }
    return {
        "ventana": ventana,
        "estado": "Ritmo estable",
        "resumen": resumen,
        "observacion": f"Sin despertares repetidos muy seguidos. Referencia para {edad} meses: {ventana}.",
        "sugerencia": f"Mantén rutinas tranquilas para {bebe} y recuerda hidratarte, {mama}.",
    }


def evaluar_agua(vasos: int) -> tuple[str, str]:
    mama = mama_lbl()
    if vasos == 0:
        return f"⚠️ Sin vasos registrados ({vasos}/8)", f"{mama}, aún no registras agua hoy."
    if vasos < 4:
        return f"🟡 Hidratación baja ({vasos}/8)", f"{mama}, llevas {vasos} vasos; intenta tomar un poco más."
    if vasos < 8:
        return f"💧 Buen avance ({vasos}/8)", f"¡Muy bien, {mama}! Llevas {vasos} de 8 vasos."
    return f"✅ Meta cumplida ({vasos}/8+)", f"¡Excelente hidratación hoy, {mama}!"


# Ambiente 1
def pagina_rutina():
    bebe = bebe_lbl()
    st.title("🌙 CUNNA · Rutina de Sueño y Sonidos")
    st.caption(f"Acompañando a {bebe} ({st.session_state.edad_meses} meses)")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("<div class='emoji-top'>🎶</div>", unsafe_allow_html=True)
        b_rut = st.button("Comenzar rutina", use_container_width=True)
    with c2:
        st.markdown("<div class='emoji-top'>💤</div>", unsafe_allow_html=True)
        b_dor = st.button("Bebé dormido", use_container_width=True)
    with c3:
        st.markdown("<div class='emoji-top'>☀️</div>", unsafe_allow_html=True)
        b_des = st.button("Despertó", use_container_width=True)

    txt = st.text_input("O escribe qué está pasando:", placeholder=f"Ej.: {bebe} dormido o despertó")
    col_v, col_b = st.columns([3, 1], vertical_alignment="bottom")
    audio_in = col_v.audio_input("O graba una nota de voz:")
    enviar = col_b.button("Enviar nota", type="primary", use_container_width=True)

    if b_rut:
        activar_estado("RUTINA", "Inicio de rutina de sueño")
    elif b_dor:
        activar_estado("DORMIDO", "Bebé dormido")
    elif b_des:
        activar_estado("DESPIERTO", "Despertó")
    elif enviar:
        texto_final = txt.strip()
        if audio_in is not None:
            voz_txt, err = transcribir_voz(audio_in)
            st.session_state.transcripcion_voz = voz_txt
            st.session_state.error_voz = err
            if voz_txt and not texto_final:
                texto_final = voz_txt
        if not texto_final and audio_in is None:
            st.session_state.error_voz = "Escribe un mensaje o graba una nota de voz."
        else:
            intent = detectar_intencion(texto_final or "rutina")
            ev_map = {
                "RUTINA": "Inicio de rutina de sueño",
                "DORMIDO": "Bebé dormido",
                "DESPIERTO": "Despertó",
            }
            activar_estado(intent, ev_map.get(intent))

    st.divider()
    st.caption(f"Estado actual: {st.session_state.fase_rutina}")
    if st.session_state.transcripcion_voz:
        st.info(f"🗣️ Dijiste: “{st.session_state.transcripcion_voz}”")
    elif st.session_state.error_voz:
        st.warning(st.session_state.error_voz)

    mostrar_mensaje_y_audio(st.session_state.ultimo_mensaje)
    mostrar_reproductor()

    if st.session_state.ultimo_detalle_mqtt:
        ok, det = st.session_state.ultimo_detalle_mqtt
        (st.success if ok else st.warning)(det)
    if st.session_state.ultimo_estado_wokwi:
        st.info(f"Wokwi ({TOPIC_ESTADO}): {st.session_state.ultimo_estado_wokwi}")


# Ambiente 2
def pagina_mama():
    bebe, mama = bebe_lbl(), mama_lbl()
    st.title("🤱 CUNNA · Mamá · Historial y cuidado")
    st.subheader(f"{mama} · {st.session_state.edad_mama} años")

    analisis = analizar_sueno(st.session_state.edad_meses, st.session_state.eventos_sueno)
    m1, m2 = st.columns(2)
    m1.metric("Ventana de referencia", analisis["ventana"])
    m2.metric("Lectura de hoy", analisis["estado"])

    st.write(f"**Resumen:** {analisis['resumen']}")
    st.info(f"**Qué se observa:** {analisis['observacion']}")
    st.write(f"**Para la próxima dormida:** {analisis['sugerencia']}")
    st.caption("Referencia organizativa general; no reemplaza orientación médica.")

    hoy = datetime.now().strftime("%Y-%m-%d")
    ev_hoy = [e for e in st.session_state.eventos_sueno if e.get("fecha") == hoy]
    ev_otros = [e for e in st.session_state.eventos_sueno if e.get("fecha") != hoy]

    st.markdown("**🕒 Registros de hoy:**")
    if ev_hoy:
        for item in reversed(ev_hoy):
            st.write(f"- **{item['hora']}** · {item['evento']}")
    else:
        st.caption("Sin registros hoy.")

    estado_agua, msg_agua = evaluar_agua(st.session_state.vasos_agua)
    resumen_txt = "\n".join(
        [
            f"CUNNA - Resumen ({hoy}) | Bebé: {bebe} ({st.session_state.edad_meses}m) | Mamá: {mama}",
            f"Ventana: {analisis['ventana']} | Estado: {analisis['estado']}",
            analisis["resumen"],
            analisis["observacion"],
            analisis["sugerencia"],
            "Registros de hoy:",
            *[f"- {e['hora']} · {e['evento']}" for e in ev_hoy],
            f"Agua: {st.session_state.vasos_agua} vasos ({estado_agua})",
        ]
    )

    b1, b2, b3 = st.columns(3)
    lbl_hist = "🙈 Ocultar historial" if st.session_state.mostrar_historial else "📜 Ver historial"
    if b1.button(lbl_hist, use_container_width=True):
        st.session_state.mostrar_historial = not st.session_state.mostrar_historial
        st.rerun()
    if b2.button("🧹 Limpiar hoy", use_container_width=True):
        st.session_state.eventos_sueno = ev_otros
        st.rerun()
    b3.download_button(
        "📥 Descargar .txt",
        data=resumen_txt,
        file_name=f"resumen_cunna_{hoy}.txt",
        mime="text/plain",
        use_container_width=True,
    )

    if st.session_state.mostrar_historial:
        st.markdown("#### 📜 Historial completo")
        for item in reversed(st.session_state.eventos_sueno):
            st.write(f"- {item.get('fecha', '')} · **{item['hora']}** · {item['evento']}")

    st.divider()
    st.subheader(f"💧 Hidratación de {mama}")
    ca1, ca2 = st.columns([1, 2], vertical_alignment="center")
    ca1.metric("Vasos hoy", f"{st.session_state.vasos_agua} 💧")
    if ca1.button("+1 Vaso de agua", type="primary", use_container_width=True):
        activar_estado("AGUA")
        st.rerun()
    ca2.markdown(f"**{estado_agua}**")
    ca2.write(msg_agua)

    st.divider()
    mostrar_mensaje_y_audio(st.session_state.ultimo_mensaje)
    st.caption(f"MQTT → Cmd: {TOPIC_CMD} | Estado: {TOPIC_ESTADO}")


nav = st.navigation(
    [
        st.Page(pagina_rutina, title="Rutina y Sonidos", icon="🌙"),
        st.Page(pagina_mama, title="Mamá · Historial y cuidado", icon="🤱"),
    ]
)
nav.run()
