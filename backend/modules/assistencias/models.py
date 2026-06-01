"""Assistências module — data models."""
from enum import Enum


class AssistenciaStatus(str, Enum):
    AGUARDA_FATURACAO = "AGUARDA_FATURACAO"
    DADOS_INCOMPLETOS = "DADOS_INCOMPLETOS"
    FATURA_ANALISADA = "FATURA_ANALISADA"
    FATURA_CONFIRMADA = "FATURA_CONFIRMADA"
    ENVIADA_FUNCIONARIO = "ENVIADA_FUNCIONARIO"
    FATURADA_CONCLUIDA = "FATURADA_CONCLUIDA"
    NAO_FATURAVEL = "NAO_FATURAVEL"


# Allowed status transitions enforced server-side
ALLOWED_STATUS_TRANSITIONS = {
    "AGUARDA_FATURACAO": {"DADOS_INCOMPLETOS", "FATURA_ANALISADA", "NAO_FATURAVEL"},
    "DADOS_INCOMPLETOS": {"AGUARDA_FATURACAO", "FATURA_ANALISADA", "NAO_FATURAVEL"},
    "FATURA_ANALISADA": {"FATURA_CONFIRMADA", "AGUARDA_FATURACAO"},
    "FATURA_CONFIRMADA": {"ENVIADA_FUNCIONARIO", "FATURA_ANALISADA"},
    "ENVIADA_FUNCIONARIO": {"FATURADA_CONCLUIDA", "FATURA_CONFIRMADA"},
    "FATURADA_CONCLUIDA": {"ENVIADA_FUNCIONARIO"},  # reopen
    "NAO_FATURAVEL": {"AGUARDA_FATURACAO"},  # admin can revert
}


NON_BILLABLE_REASONS = [
    ("warranty", "Garantia"),
    ("monthly_contract", "Avença / Contrato Mensal"),
    ("internal_service", "Serviço Interno"),
    ("commercial_offer", "Oferta Comercial"),
    ("operational_error", "Erro Operacional"),
    ("other", "Outro"),
]


ADDITIONAL_PHOTO_CATEGORIES = [
    ("mounted_tires", "Pneus Montados"),
    ("tire_label", "Etiqueta do Pneu"),
    ("product_code", "Código do Produto"),
    ("full_vehicle", "Veículo Completo"),
    ("damage", "Avaria / Falha"),
    ("other", "Outro"),
]


# Audited fields (any change recorded in audit_logs[])
AUDITED_FIELDS = [
    "status", "registration_plate", "invoice_number", "invoice_total",
    "invoice_date", "invoice_customer", "invoice_nif", "non_billable_reason",
    "internal_note", "text_notes",
]


# Conversation states (Telegram bot)
STATE_IDLE = "IDLE"
STATE_WAIT_LOCATION = "WAIT_LOCATION"
STATE_WAIT_PLATE = "WAIT_PLATE"
STATE_CONFIRM_PLATE = "CONFIRM_PLATE"
STATE_EDIT_PLATE = "EDIT_PLATE"
STATE_WAIT_WORKSHEET = "WAIT_WORKSHEET"
STATE_ASK_ADDITIONAL = "ASK_ADDITIONAL"
STATE_COLLECT_ADDITIONAL = "COLLECT_ADDITIONAL"
STATE_ASK_NOTES = "ASK_NOTES"
STATE_COLLECT_TEXT_NOTES = "COLLECT_TEXT_NOTES"
STATE_COLLECT_AUDIO_NOTES = "COLLECT_AUDIO_NOTES"


MAX_ADDITIONAL_PHOTOS = 6
INACTIVITY_TIMEOUT_SEC = 1800  # 30 minutes
