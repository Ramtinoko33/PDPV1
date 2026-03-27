"""
Services package - Business logic layer.
"""
from .auth_service import (
    check_login_rate_limit,
    record_login_failure,
    clear_login_attempts,
)
from .sla_service import (
    compute_sla_due,
    compute_sla_due_simple,
    check_ticket_overdue,
    calculate_sla_elapsed_minutes,
    add_business_minutes,
    calculate_business_minutes_between,
    load_sla_config_from_db,
    load_holidays_from_db,
    is_holiday,
    BUSINESS_HOURS,
    SLA_TARGETS_MINUTES,
    SLA_DEFAULT_MINUTES,
    SLA_USE_BUSINESS_HOURS,
    SLA_PAUSE_ON_AGUARDA_CLIENTE,
    HOLIDAYS,
    RECURRING_HOLIDAYS,
)
from .storage_service import (
    init_storage,
    put_object,
    get_object,
    get_storage_client,
    is_storage_available,
    UPLOAD_DIR,
    APP_NAME,
)
from .ticket_service import (
    generate_ticket_number,
    log_status_change,
    log_quote_change,
    get_or_create_reply_token,
    REJECTION_REASON_CODES,
)
from .notification_service import (
    create_notification,
    notify_supervisors,
    send_web_push_to_user,
    set_vapid_keys_valid,
    get_vapid_keys_valid,
    set_vapid_keys,
    get_vapid_public_key,
)

__all__ = [
    # Auth
    "check_login_rate_limit",
    "record_login_failure",
    "clear_login_attempts",
    # SLA
    "compute_sla_due",
    "compute_sla_due_simple",
    "check_ticket_overdue",
    "calculate_sla_elapsed_minutes",
    "add_business_minutes",
    "calculate_business_minutes_between",
    "load_sla_config_from_db",
    "load_holidays_from_db",
    "is_holiday",
    "BUSINESS_HOURS",
    "SLA_TARGETS_MINUTES",
    "SLA_DEFAULT_MINUTES",
    "SLA_USE_BUSINESS_HOURS",
    "SLA_PAUSE_ON_AGUARDA_CLIENTE",
    "HOLIDAYS",
    "RECURRING_HOLIDAYS",
    # Storage
    "init_storage",
    "put_object",
    "get_object",
    "get_storage_client",
    "is_storage_available",
    "UPLOAD_DIR",
    "APP_NAME",
    # Ticket
    "generate_ticket_number",
    "log_status_change",
    "log_quote_change",
    "get_or_create_reply_token",
    "REJECTION_REASON_CODES",
    # Notification
    "create_notification",
    "notify_supervisors",
    "send_web_push_to_user",
    "set_vapid_keys_valid",
    "get_vapid_keys_valid",
    "set_vapid_keys",
    "get_vapid_public_key",
]
