"""
SLA Service Module.
Contains business logic for SLA calculations, business hours, and pause/resume functionality.
"""
import logging
from datetime import datetime, timezone, timedelta, date, time
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)

# ============== SLA BUSINESS HOURS CONFIGURATION ==============
# Default values - can be overridden by database config
BUSINESS_HOURS = {
    0: (time(8, 30), time(18, 30)),   # Monday
    1: (time(8, 30), time(18, 30)),   # Tuesday
    2: (time(8, 30), time(18, 30)),   # Wednesday
    3: (time(8, 30), time(18, 30)),   # Thursday
    4: (time(8, 30), time(18, 30)),   # Friday
    5: (time(8, 30), time(13, 0)),    # Saturday
    6: None,                           # Sunday (closed)
}

# SLA targets in business minutes per ticket type - default values
SLA_TARGETS_MINUTES = {
    "ORCAMENTO_PNEUS": 480,      # 8 hours = 480 minutes
    "ORCAMENTO_MECANICA": 480,   # 8 hours = 480 minutes
    "INFORMACAO": 120,           # 2 hours = 120 minutes
    "RECLAMACAO": 120,           # 2 hours = 120 minutes
    "MARCACAO": 180,             # 3 hours = 180 minutes
    "INTERNO": 480,              # 8 hours (default for internal)
}

# SLA options - default values
SLA_DEFAULT_MINUTES = 120  # 2 hours fallback
SLA_USE_BUSINESS_HOURS = True
SLA_PAUSE_ON_AGUARDA_CLIENTE = True

# Holidays - loaded from database
# Structure: List of tuples (date, is_recurring_annual)
# For recurring holidays, we store (month, day) for annual matching
HOLIDAYS: List[date] = []
RECURRING_HOLIDAYS: List[tuple] = []  # [(month, day), ...]


def parse_time_string(time_str: str) -> time:
    """Parse a time string like '08:30' into a time object."""
    try:
        parts = time_str.split(':')
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return time(8, 30)  # Default fallback


async def load_holidays_from_db(db):
    """Load holidays from database and update global variables."""
    global HOLIDAYS, RECURRING_HOLIDAYS
    
    try:
        # Get all active holidays
        holidays = await db.holidays.find({"active": True}, {"_id": 0}).to_list(1000)
        
        fixed_holidays = []
        recurring_holidays = []
        
        for h in holidays:
            try:
                holiday_date = datetime.strptime(h["date"], "%Y-%m-%d").date()
                
                if h.get("is_recurring_annual", False):
                    # Store as (month, day) for annual matching
                    recurring_holidays.append((holiday_date.month, holiday_date.day))
                else:
                    # Store as fixed date
                    fixed_holidays.append(holiday_date)
            except (ValueError, KeyError):
                continue
        
        HOLIDAYS = fixed_holidays
        RECURRING_HOLIDAYS = recurring_holidays
        
        logger.info(f"Holidays loaded: {len(HOLIDAYS)} fixed, {len(RECURRING_HOLIDAYS)} recurring")
    except Exception as e:
        logger.error(f"Error loading holidays: {e}")


def is_holiday(d: date) -> bool:
    """Check if a date is a holiday (fixed or recurring annual)."""
    # Check fixed holidays
    if d in HOLIDAYS:
        return True
    
    # Check recurring annual holidays
    for month, day in RECURRING_HOLIDAYS:
        if d.month == month and d.day == day:
            return True
    
    return False


async def load_sla_config_from_db(db):
    """Load SLA configuration from database and update global variables."""
    global BUSINESS_HOURS, SLA_TARGETS_MINUTES, SLA_DEFAULT_MINUTES, SLA_USE_BUSINESS_HOURS, SLA_PAUSE_ON_AGUARDA_CLIENTE
    
    try:
        config = await db.settings.find_one({"type": "sla_config"}, {"_id": 0})
        if not config:
            return  # Use defaults
        
        # Update business hours
        day_mapping = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        for day_name, day_num in day_mapping.items():
            day_config = config.get(day_name)
            if day_config:
                if day_config.get('closed', False):
                    BUSINESS_HOURS[day_num] = None
                else:
                    start = parse_time_string(day_config.get('start', '08:30'))
                    end = parse_time_string(day_config.get('end', '18:30'))
                    BUSINESS_HOURS[day_num] = (start, end)
        
        # Update SLA targets (convert hours to minutes)
        if 'sla_orcamento_mecanica' in config:
            SLA_TARGETS_MINUTES['ORCAMENTO_MECANICA'] = config['sla_orcamento_mecanica'] * 60
        if 'sla_orcamento_pneus' in config:
            SLA_TARGETS_MINUTES['ORCAMENTO_PNEUS'] = config['sla_orcamento_pneus'] * 60
        if 'sla_informacao' in config:
            SLA_TARGETS_MINUTES['INFORMACAO'] = config['sla_informacao'] * 60
        if 'sla_reclamacao' in config:
            SLA_TARGETS_MINUTES['RECLAMACAO'] = config['sla_reclamacao'] * 60
        if 'sla_marcacao' in config:
            SLA_TARGETS_MINUTES['MARCACAO'] = config['sla_marcacao'] * 60
        if 'sla_interno' in config:
            SLA_TARGETS_MINUTES['INTERNO'] = config['sla_interno'] * 60
        if 'sla_default' in config:
            SLA_DEFAULT_MINUTES = config['sla_default'] * 60
        
        # Update options
        if 'use_business_hours' in config:
            SLA_USE_BUSINESS_HOURS = config['use_business_hours']
        if 'pause_on_aguarda_cliente' in config:
            SLA_PAUSE_ON_AGUARDA_CLIENTE = config['pause_on_aguarda_cliente']
            
        logger.info(f"SLA config loaded from database: business_hours={SLA_USE_BUSINESS_HOURS}, pause_aguarda={SLA_PAUSE_ON_AGUARDA_CLIENTE}")
    except Exception as e:
        logger.error(f"Error loading SLA config: {e}")


def is_business_day(d: date) -> bool:
    """Check if a date is a business day (not weekend, not holiday)."""
    if is_holiday(d):
        return False
    weekday = d.weekday()
    return BUSINESS_HOURS.get(weekday) is not None


def get_business_hours_for_day(d: date) -> Tuple[time, time] | None:
    """Get business hours (start, end) for a given date. Returns None if closed or holiday."""
    if is_holiday(d):
        return None
    return BUSINESS_HOURS.get(d.weekday())


def get_business_minutes_in_day(d: date, start_time: time = None, end_time: time = None) -> int:
    """
    Calculate business minutes available in a day.
    If start_time is provided, start counting from that time.
    If end_time is provided, stop counting at that time.
    """
    hours = get_business_hours_for_day(d)
    if not hours:
        return 0
    
    biz_start, biz_end = hours
    
    # Effective start is max of business start and provided start
    effective_start = biz_start
    if start_time:
        effective_start = max(biz_start, start_time)
    
    # Effective end is min of business end and provided end
    effective_end = biz_end
    if end_time:
        effective_end = min(biz_end, end_time)
    
    # If effective start >= effective end, no business time available
    if effective_start >= effective_end:
        return 0
    
    # Calculate minutes
    start_minutes = effective_start.hour * 60 + effective_start.minute
    end_minutes = effective_end.hour * 60 + effective_end.minute
    
    return end_minutes - start_minutes


def add_business_minutes(start_dt: datetime, minutes_to_add: int) -> datetime:
    """
    Add business minutes to a datetime and return the resulting datetime.
    If start_dt is outside business hours, it advances to the next business period.
    """
    if minutes_to_add <= 0:
        return start_dt
    
    current_dt = start_dt
    remaining_minutes = minutes_to_add
    
    # Maximum iterations to prevent infinite loop (e.g., 365 days)
    max_iterations = 365
    iterations = 0
    
    while remaining_minutes > 0 and iterations < max_iterations:
        iterations += 1
        current_date = current_dt.date()
        current_time = current_dt.time()
        
        hours = get_business_hours_for_day(current_date)
        
        if not hours:
            # Not a business day, move to next day at midnight
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        
        biz_start, biz_end = hours
        
        # If current time is before business start, move to business start
        if current_time < biz_start:
            current_dt = datetime.combine(current_date, biz_start, tzinfo=current_dt.tzinfo)
            current_time = biz_start
        
        # If current time is after business end, move to next day
        if current_time >= biz_end:
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        
        # Calculate available minutes until end of business day
        current_minutes = current_time.hour * 60 + current_time.minute
        end_minutes = biz_end.hour * 60 + biz_end.minute
        available_minutes = end_minutes - current_minutes
        
        if remaining_minutes <= available_minutes:
            # Can finish within this day
            final_minutes = current_minutes + remaining_minutes
            final_hour = final_minutes // 60
            final_minute = final_minutes % 60
            return datetime.combine(current_date, time(final_hour, final_minute), tzinfo=current_dt.tzinfo)
        else:
            # Use all available minutes and move to next day
            remaining_minutes -= available_minutes
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
    
    # Fallback if max iterations reached
    return current_dt


def calculate_business_minutes_between(start_dt: datetime, end_dt: datetime) -> int:
    """
    Calculate the number of business minutes between two datetimes.
    Used to calculate elapsed SLA time.
    """
    if end_dt <= start_dt:
        return 0
    
    total_minutes = 0
    current_dt = start_dt
    
    # Maximum iterations to prevent infinite loop
    max_iterations = 365
    iterations = 0
    
    while current_dt < end_dt and iterations < max_iterations:
        iterations += 1
        current_date = current_dt.date()
        current_time = current_dt.time()
        
        hours = get_business_hours_for_day(current_date)
        
        if not hours:
            # Not a business day, move to next day
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        
        biz_start, biz_end = hours
        
        # If current time is before business start, move to business start
        if current_time < biz_start:
            current_dt = datetime.combine(current_date, biz_start, tzinfo=current_dt.tzinfo)
            current_time = biz_start
        
        # If current time is after business end, move to next day
        if current_time >= biz_end:
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        
        # Determine how far we can go today
        if end_dt.date() == current_date:
            # End is on the same day
            end_time_today = min(end_dt.time(), biz_end)
        else:
            # End is on a future day, count until business end
            end_time_today = biz_end
        
        # If end_time_today is before current time (shouldn't happen normally), skip
        if end_time_today <= current_time:
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
            continue
        
        # Calculate minutes in this segment
        current_minutes = current_time.hour * 60 + current_time.minute
        end_minutes_today = end_time_today.hour * 60 + end_time_today.minute
        segment_minutes = end_minutes_today - current_minutes
        total_minutes += segment_minutes
        
        # Move to end of this segment
        if end_dt.date() == current_date and end_dt.time() <= biz_end:
            # We've reached the end
            break
        else:
            # Move to next day
            current_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0), tzinfo=current_dt.tzinfo)
    
    return total_minutes


def compute_sla_due(ticket_type: str = "INFORMACAO", created_at: datetime = None) -> Tuple[datetime, int, str]:
    """
    Returns (SLA due datetime, target_minutes, policy_key) based on ticket type and business hours.
    If created_at is outside business hours, SLA starts at next business period.
    Uses SLA_DEFAULT_MINUTES as fallback if ticket type not found.
    """
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    
    # Get target minutes from config, use global default as fallback
    target_minutes = SLA_TARGETS_MINUTES.get(ticket_type, SLA_DEFAULT_MINUTES)
    policy_key = f"SLA_{ticket_type}_{target_minutes}min"
    
    # Check if business hours mode is enabled
    if SLA_USE_BUSINESS_HOURS:
        sla_due = add_business_minutes(created_at, target_minutes)
    else:
        # Simple calculation - just add minutes directly
        sla_due = created_at + timedelta(minutes=target_minutes)
    
    return sla_due, target_minutes, policy_key


def compute_sla_due_simple() -> datetime:
    """Legacy function for backwards compatibility - returns 2 hours from now (simple calculation)."""
    now = datetime.now(timezone.utc)
    return now + timedelta(hours=2)


def check_ticket_overdue(ticket: dict) -> bool:
    """
    Check if ticket is overdue based on SLA due date and first response status.
    Takes into account:
    - Ticket status (closed tickets are never overdue)
    - First response done flag
    - SLA breached flag (if already marked as breached)
    - SLA pause state
    """
    from schemas.ticket import TicketStatus
    
    now = datetime.now(timezone.utc)
    
    # Closed tickets are never considered overdue
    if ticket.get("status") == TicketStatus.FECHADO.value:
        return False
    
    # If SLA already breached, return True
    if ticket.get("sla_breached"):
        return True
    
    # If first response already done, not overdue
    if ticket.get("first_response_done"):
        return False
    
    # If SLA is currently paused, not overdue (clock is stopped)
    if ticket.get("sla_paused_at"):
        return False
    
    # Check if current time exceeds SLA due
    if ticket.get("sla_due"):
        try:
            sla_due = datetime.fromisoformat(ticket["sla_due"].replace("Z", "+00:00"))
            if now > sla_due:
                return True
        except (ValueError, TypeError):
            pass
    
    return False


def calculate_sla_elapsed_minutes(ticket: dict) -> int:
    """
    Calculate total elapsed business minutes for SLA tracking.
    Takes into account pause periods.
    """
    created_at_str = ticket.get("sla_started_at") or ticket.get("created_at")
    if not created_at_str:
        return 0
    
    try:
        sla_start = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return 0
    
    # Get paused time accumulated
    paused_minutes = ticket.get("sla_paused_minutes", 0)
    
    # If currently paused, calculate only up to pause start
    if ticket.get("sla_paused_at"):
        try:
            pause_start = datetime.fromisoformat(ticket["sla_paused_at"].replace("Z", "+00:00"))
            elapsed = calculate_business_minutes_between(sla_start, pause_start)
            return elapsed - paused_minutes
        except (ValueError, TypeError):
            pass
    
    # Calculate elapsed from start to now
    now = datetime.now(timezone.utc)
    elapsed = calculate_business_minutes_between(sla_start, now)
    
    return max(0, elapsed - paused_minutes)
