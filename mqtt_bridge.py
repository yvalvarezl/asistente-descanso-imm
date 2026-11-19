import json
import time
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish

BROKER = "broker.mqttdashboard.com"
PORT = 1883
TOPIC_CMD = "pausa_yos/cmd"
TOPIC_ESTADO = "pausa_yos/estado"


def enviar_comando_mqtt(estado: str, origen: str = "streamlit") -> tuple[bool, str]:
    payload = json.dumps({
        "estado": estado,
        "origen": origen,
        "ts": int(time.time())
    })
    try:
        publish.single(
            topic=TOPIC_CMD,
            payload=payload,
            hostname=BROKER,
            port=PORT,
            qos=0
        )
        return True, f"Enviado a {TOPIC_CMD}: {payload}"
    except Exception as exc:
        return False, f"Error al publicar en MQTT: {exc}"


def leer_ultimo_estado_mqtt(timeout_seg: float = 1.5) -> dict | None:
    resultado = {"data": None}

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(TOPIC_ESTADO, qos=0)

    def on_message(client, userdata, msg):
        try:
            raw = msg.payload.decode("utf-8", errors="ignore")
            parsed = json.loads(raw)
            resultado["data"] = parsed
        except Exception:
            resultado["data"] = {"raw": msg.payload.decode("utf-8", errors="ignore")}
        client.disconnect()

    client = mqtt.Client(client_id=f"st-listener-{int(time.time() * 1000) % 100000}")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, keepalive=10)
        fin = time.time() + timeout_seg
        while time.time() < fin and resultado["data"] is None:
            client.loop(timeout=0.2)
        client.disconnect()
    except Exception:
        return None

    return resultado["data"]
