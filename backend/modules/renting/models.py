"""Renting module — data models."""
from enum import Enum


class RentingStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


# Allowed status transitions enforced server-side
ALLOWED_STATUS_TRANSITIONS = {
    "draft": {"in_progress"},
    "in_progress": {"completed"},
    "completed": {"in_progress"},  # allow re-opening if needed
}

# Fields tracked in the audit history (subset of RentingUpdate)
AUDITED_FIELDS = [
    "driver_name", "driver_phone", "renting_company", "license_plate", "km",
    "service_type", "service_type_label", "subtype", "adblue_liters",
    "description", "puncture_wheel", "puncture_wheel_label",
    "proposed_tires", "authorization_number", "status",
]


# Wheel positions in collection order
WHEEL_POSITIONS = ["FE", "FD", "TD", "TE"]
WHEEL_LABELS = {
    "FE": "Frente Esquerda",
    "FD": "Frente Direita",
    "TD": "Trás Direita",
    "TE": "Trás Esquerda",
}

# Service types offered after wheel collection (full tire flow)
SERVICE_TYPES = [
    ("2_front", "2 pneus frente"),
    ("2_rear", "2 pneus trás"),
    ("4_tires", "4 pneus"),
    ("puncture", "Furo"),
    ("inspection", "Verificação"),
    ("other", "Outro"),
]

# Service types after "Pneus" subtype selection (asked BEFORE wheel photos)
TIRE_SERVICE_TYPES = [
    ("2_front", "2 pneus frente"),
    ("2_rear", "2 pneus trás"),
    ("4_tires", "4 pneus"),
    ("puncture", "Furo"),
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
STATE_WAIT_SUBTYPE = "WAIT_SUBTYPE"
STATE_WAIT_SERVICE_TYPE = "WAIT_SERVICE_TYPE"
STATE_WAIT_PUNCTURE_WHEEL = "WAIT_PUNCTURE_WHEEL"
STATE_WAIT_PUNCTURE_OBS = "WAIT_PUNCTURE_OBS"
STATE_WAIT_OTHER_DESC = "WAIT_OTHER_DESC"
STATE_WAIT_OTHER_OBS = "WAIT_OTHER_OBS"
STATE_WAIT_ADBLUE_LITERS = "WAIT_ADBLUE_LITERS"
STATE_WAIT_ADBLUE_OBS = "WAIT_ADBLUE_OBS"
STATE_WHEEL_PHOTO_FULL = "WHEEL_PHOTO_FULL"
STATE_CONFIRM_FULL = "CONFIRM_FULL"
STATE_EDIT_FULL_SIZE = "EDIT_FULL_SIZE"
STATE_EDIT_FULL_BRAND = "EDIT_FULL_BRAND_MODEL"
STATE_EDIT_FULL_LOAD_SPEED = "EDIT_FULL_LOAD_SPEED"
STATE_WHEEL_PHOTO_DOT = "WHEEL_PHOTO_DOT"
STATE_CONFIRM_DOT = "CONFIRM_DOT"
STATE_EDIT_DOT = "EDIT_DOT"
STATE_WHEEL_PHOTO_TREAD = "WHEEL_PHOTO_TREAD"
STATE_CONFIRM_TREAD = "CONFIRM_TREAD"
STATE_EDIT_TREAD = "EDIT_TREAD"
STATE_CONFIRM_WHEEL = "CONFIRM_WHEEL"
STATE_EDIT_WHEEL = "EDIT_WHEEL"
STATE_WAIT_SERVICE = "WAIT_SERVICE"
STATE_WAIT_OBSERVATIONS = "WAIT_OBSERVATIONS"
STATE_COLLECT_OBS_TEXT = "COLLECT_OBS_TEXT"
STATE_COLLECT_OBS_AUDIO = "COLLECT_OBS_AUDIO"
