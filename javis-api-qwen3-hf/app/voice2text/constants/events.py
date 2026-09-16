from enum import Enum

class TranscriptionWsServerEvent(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    FINAL = "final"
    TURN_END = "turn_end"
    SESSION_STOPPED = "session_stopped"
    PING = "ping"
    PONG = "pong"
    PONG_MS = "pong_ms"
    TIME_START_ACK = "time_start_ack"
    SONIOX_RECONNECTING = "soniox_reconnecting"
    SONIOX_RECONNECTED = "soniox_reconnected"
    ERROR = "error"
    WAKE_WORD = "wake_word"
