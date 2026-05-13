"""Renting module — data models."""
from enum import Enum


class RentingStatus(str, Enum):
    DRAFT = "draft"
    COMPLETED = "completed"


# Wheel positions in collection order
WHEEL_POSITIONS = ["FE", "FD", "TD", "TE"]
WHEEL_LABELS = {
    "FE": "Frente Esquerda",
    "FD": "Frente Direita",
    "TD": "Trás Direita",
    "TE": "Trás Esquerda",
}

# Service types offered after wheel collection
SERVICE_TYPES = [
    ("2_front", "2 pneus frente"),
    ("2_rear", "2 pneus trás"),
    ("4_tires", "4 pneus"),
    ("puncture", "Furo"),
    ("inspection", "Verificação"),
    ("other", "Outro"),
]

# Conversation states (Telegram)
STATE_IDLE = "IDLE"
STATE_WAIT_DRIVER_NAME = "WAIT_DRIVER_NAME"
STATE_WAIT_DRIVER_PHONE = "WAIT_DRIVER_PHONE"
STATE_WAIT_RENTING_COMPANY = "WAIT_RENTING_COMPANY"
STATE_WAIT_PLATE_PHOTO = "WAIT_PLATE_PHOTO"
STATE_CONFIRM_PLATE = "CONFIRM_PLATE"
STATE_EDIT_PLATE = "EDIT_PLATE"
STATE_WAIT_KM_PHOTO = "WAIT_KM_PHOTO"
STATE_CONFIRM_KM = "CONFIRM_KM"
STATE_EDIT_KM = "EDIT_KM"
STATE_WHEEL_PHOTO_FULL = "WHEEL_PHOTO_FULL"
STATE_WHEEL_PHOTO_DOT = "WHEEL_PHOTO_DOT"
STATE_WHEEL_PHOTO_TREAD = "WHEEL_PHOTO_TREAD"
STATE_CONFIRM_WHEEL = "CONFIRM_WHEEL"
STATE_EDIT_WHEEL = "EDIT_WHEEL"
STATE_WAIT_SERVICE = "WAIT_SERVICE"
STATE_WAIT_OBSERVATIONS = "WAIT_OBSERVATIONS"
STATE_COLLECT_OBS_TEXT = "COLLECT_OBS_TEXT"
STATE_COLLECT_OBS_AUDIO = "COLLECT_OBS_AUDIO"
