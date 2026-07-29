"""MQTT 게이트웨이 — 대회 필수 파이프라인 02(RPi 게이트웨이) 충족.

토픽:
  peakbridge/demo/telemetry  ESP32 → 서버 (QoS0, 페이로드는 HTTP와 동일 JSON)
  peakbridge/demo/config     서버 → ESP32 (retained=True, QoS1)
                             → ESP32 재부팅·재접속 시 즉시 최신 config 수신 보장

기동 조건: 환경변수 MQTT_BROKER가 설정된 경우에만 백그라운드 스레드로 접속.
미설정이면 서버는 HTTP-only 모드로 완전히 동작한다 (합숙 전 개발·리허설에 충분).
브로커 접속 실패는 경고 로그만 남기고 서버를 절대 죽이지 않는다.
"""

import json
import logging
import os
import threading
from typing import Any, Callable

import adapters

logger = logging.getLogger("mqtt_gateway")

TOPIC_TELEMETRY = "peakbridge/demo/telemetry"
TOPIC_CONFIG = "peakbridge/demo/config"
# 1회성 명령(SOC 리셋 등) — config와 달리 retained 금지: 재부팅한 보드가
# 과거 명령을 다시 받아 실행하면 안 된다.
TOPIC_COMMAND = "peakbridge/demo/command"

# 구성 B(팀원A 3-노드) 흡수 — 기본 ON. 끄려면 LEGACY_ADAPTER=0
LEGACY_ENABLED = os.environ.get("LEGACY_ADAPTER", "1") != "0"

_client: Any = None
_thread: threading.Thread | None = None
_connected = False
_enabled = False
_broker = ""
_port = 1883


def status() -> dict[str, Any]:
    return {"enabled": _enabled, "connected": _connected, "broker": _broker, "port": _port}


def start(ingest: Callable[[dict], Any], get_config: Callable[[], dict]) -> None:
    """MQTT_BROKER가 있을 때만 접속. ingest는 HTTP와 공유하는 저장 함수."""
    global _client, _thread, _enabled, _broker, _port

    _broker = os.environ.get("MQTT_BROKER", "").strip()
    if not _broker:
        logger.info("MQTT_BROKER 미설정 — HTTP-only 모드로 동작합니다.")
        return

    _port = int(os.environ.get("MQTT_PORT", "1883"))

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        logger.warning("paho-mqtt 미설치 — MQTT 비활성. HTTP-only 모드로 계속합니다.")
        return

    _enabled = True

    def on_connect(client, userdata, flags, rc, *args):
        global _connected
        if rc == 0:
            _connected = True
            logger.info("MQTT 브로커 접속 성공: %s:%s", _broker, _port)
            client.subscribe(TOPIC_TELEMETRY, qos=0)
            if LEGACY_ENABLED:
                # 구성 B의 건물별 토픽까지 함께 구독 (peakbridge/<building>/**)
                client.subscribe(adapters.TOPIC_LEGACY_WILDCARD, qos=0)
                logger.info("레거시 3-노드 어댑터 구독: %s", adapters.TOPIC_LEGACY_WILDCARD)
            # 기동 시 1회 현재 config를 retained로 발행
            try:
                publish_config(get_config())
            except Exception as exc:  # noqa: BLE001
                logger.warning("기동 시 config 발행 실패: %s", exc)
        else:
            _connected = False
            logger.warning("MQTT 접속 실패 (rc=%s)", rc)

    def on_disconnect(client, userdata, rc, *args):
        global _connected
        _connected = False
        logger.warning("MQTT 연결 끊김 (rc=%s) — 자동 재접속 대기", rc)

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("MQTT 페이로드 파싱 실패: %s", exc)
            return
        try:
            if msg.topic == TOPIC_TELEMETRY:
                # 구성 A: 완결 페이로드 — HTTP 핸들러와 동일한 저장 경로를 그대로 사용한다.
                ingest(payload)
            elif LEGACY_ENABLED:
                # 구성 B: 조각난 3-노드 메시지 → 어댑터가 canonical 행으로 합쳐 같은 경로로 저장
                adapters.handle(msg.topic, payload, ingest)
        except Exception as exc:  # noqa: BLE001
            logger.warning("MQTT 텔레메트리 저장 실패 (%s): %s", msg.topic, exc)

    try:
        # paho 2.x / 1.x 양쪽 호환
        try:
            _client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            _client = mqtt.Client()
        _client.on_connect = on_connect
        _client.on_disconnect = on_disconnect
        _client.on_message = on_message
        # 재접속 백오프 (무한 재시도하되 폭주 금지)
        _client.reconnect_delay_set(min_delay=1, max_delay=30)
        _client.connect_async(_broker, _port, keepalive=60)
        _thread = threading.Thread(target=_client.loop_forever, daemon=True)
        _thread.start()
        logger.info("MQTT 게이트웨이 시작 (브로커 %s:%s)", _broker, _port)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MQTT 게이트웨이 시작 실패 — HTTP-only로 계속: %s", exc)
        _enabled = False


def publish_config(cfg: dict[str, Any]) -> None:
    """config를 retained·QoS1로 발행. MQTT 비활성이면 조용히 무시."""
    if not (_enabled and _client):
        return
    try:
        _client.publish(TOPIC_CONFIG, json.dumps(cfg, ensure_ascii=False), qos=1, retain=True)
        logger.info("config retained 발행: %s", cfg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("config 발행 실패: %s", exc)


def publish_command(cmd: dict[str, Any]) -> bool:
    """1회성 명령을 QoS1·비retained로 발행. 발행 시도 성공 여부 반환."""
    if not (_enabled and _client):
        return False
    try:
        _client.publish(TOPIC_COMMAND, json.dumps(cmd, ensure_ascii=False), qos=1, retain=False)
        logger.info("command 발행: %s", cmd)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("command 발행 실패: %s", exc)
        return False


def stop() -> None:
    global _connected
    if _client:
        try:
            _client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    _connected = False
