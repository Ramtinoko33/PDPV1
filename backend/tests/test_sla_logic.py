"""
Test cases for SLA business hours logic.
Tests the calculation of business hours, SLA due dates, and pause/resume functionality.
"""
import sys
sys.path.insert(0, '/app/backend')

from datetime import datetime, timezone, timedelta, date, time

# Import SLA functions from sla_service
from services.sla_service import (
    BUSINESS_HOURS,
    SLA_TARGETS_MINUTES,
    HOLIDAYS,
    RECURRING_HOLIDAYS,
    is_business_day,
    is_holiday,
    get_business_hours_for_day,
    get_business_minutes_in_day,
    add_business_minutes,
    calculate_business_minutes_between,
    compute_sla_due,
)


def test_business_hours_config():
    """Test that business hours are correctly configured."""
    print("\n=== Test: Business Hours Configuration ===")
    
    # Monday-Friday: 08:30-18:30 (10 hours = 600 minutes)
    for day in range(5):  # 0=Monday to 4=Friday
        hours = BUSINESS_HOURS.get(day)
        assert hours is not None, f"Day {day} should have business hours"
        assert hours[0] == time(8, 30), f"Day {day} should start at 08:30"
        assert hours[1] == time(18, 30), f"Day {day} should end at 18:30"
        print(f"  Day {day}: {hours[0]} - {hours[1]} ✓")
    
    # Saturday: 08:30-13:00 (4.5 hours = 270 minutes)
    saturday = BUSINESS_HOURS.get(5)
    assert saturday is not None, "Saturday should have business hours"
    assert saturday[0] == time(8, 30), "Saturday should start at 08:30"
    assert saturday[1] == time(13, 0), "Saturday should end at 13:00"
    print(f"  Saturday: {saturday[0]} - {saturday[1]} ✓")
    
    # Sunday: Closed
    sunday = BUSINESS_HOURS.get(6)
    assert sunday is None, "Sunday should be closed"
    print(f"  Sunday: Closed ✓")
    
    print("  [PASSED]")


def test_sla_targets():
    """Test that SLA targets are correctly configured."""
    print("\n=== Test: SLA Targets Configuration ===")
    
    expected = {
        "ORCAMENTO_PNEUS": 480,      # 8 hours
        "ORCAMENTO_MECANICA": 480,   # 8 hours
        "INFORMACAO": 120,           # 2 hours
        "RECLAMACAO": 120,           # 2 hours
        "MARCACAO": 180,             # 3 hours
        "INTERNO": 480,              # 8 hours
    }
    
    for ticket_type, expected_minutes in expected.items():
        actual = SLA_TARGETS_MINUTES.get(ticket_type)
        assert actual == expected_minutes, f"{ticket_type} should be {expected_minutes} minutes"
        print(f"  {ticket_type}: {actual} minutes ({actual//60}h) ✓")
    
    print("  [PASSED]")


def test_is_business_day():
    """Test business day detection."""
    print("\n=== Test: is_business_day ===")
    
    # Monday (should be business day)
    monday = date(2025, 12, 22)  # A Monday
    assert is_business_day(monday), "Monday should be business day"
    print(f"  Monday {monday}: Business day ✓")
    
    # Saturday (should be business day)
    saturday = date(2025, 12, 27)  # A Saturday
    assert is_business_day(saturday), "Saturday should be business day"
    print(f"  Saturday {saturday}: Business day ✓")
    
    # Sunday (should NOT be business day)
    sunday = date(2025, 12, 28)  # A Sunday
    assert not is_business_day(sunday), "Sunday should NOT be business day"
    print(f"  Sunday {sunday}: NOT business day ✓")
    
    print("  [PASSED]")


def test_business_minutes_in_day():
    """Test calculation of business minutes in a day."""
    print("\n=== Test: Business Minutes in Day ===")
    
    # Full weekday: 08:30-18:30 = 600 minutes
    monday = date(2025, 12, 22)
    full_day = get_business_minutes_in_day(monday)
    assert full_day == 600, f"Full weekday should be 600 minutes, got {full_day}"
    print(f"  Full weekday: {full_day} minutes ✓")
    
    # Full Saturday: 08:30-13:00 = 270 minutes
    saturday = date(2025, 12, 27)
    sat_full = get_business_minutes_in_day(saturday)
    assert sat_full == 270, f"Full Saturday should be 270 minutes, got {sat_full}"
    print(f"  Full Saturday: {sat_full} minutes ✓")
    
    # Sunday: 0 minutes
    sunday = date(2025, 12, 28)
    sun_full = get_business_minutes_in_day(sunday)
    assert sun_full == 0, f"Sunday should be 0 minutes, got {sun_full}"
    print(f"  Sunday: {sun_full} minutes ✓")
    
    # Partial day - start at 10:00 on weekday
    partial = get_business_minutes_in_day(monday, start_time=time(10, 0))
    expected = (18*60+30) - (10*60)  # 18:30 - 10:00 = 510 minutes
    assert partial == expected, f"Partial day from 10:00 should be {expected} minutes, got {partial}"
    print(f"  Weekday from 10:00: {partial} minutes ✓")
    
    # Start before business hours (should count from 08:30)
    early = get_business_minutes_in_day(monday, start_time=time(7, 0))
    assert early == 600, f"Starting at 07:00 should still be 600 minutes, got {early}"
    print(f"  Weekday starting 07:00 (before open): {early} minutes ✓")
    
    # Start after business hours (should be 0)
    late = get_business_minutes_in_day(monday, start_time=time(19, 0))
    assert late == 0, f"Starting at 19:00 should be 0 minutes, got {late}"
    print(f"  Weekday starting 19:00 (after close): {late} minutes ✓")
    
    print("  [PASSED]")


def test_add_business_minutes_same_day():
    """Test adding business minutes within the same day."""
    print("\n=== Test: Add Business Minutes (Same Day) ===")
    
    # Start at 09:00 Monday, add 60 minutes -> 10:00 Monday
    monday_9am = datetime(2025, 12, 22, 9, 0, tzinfo=timezone.utc)
    result = add_business_minutes(monday_9am, 60)
    expected = datetime(2025, 12, 22, 10, 0, tzinfo=timezone.utc)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  09:00 + 60min = {result.strftime('%H:%M')} ✓")
    
    # Start at 10:30 Monday, add 120 minutes -> 12:30 Monday
    monday_1030 = datetime(2025, 12, 22, 10, 30, tzinfo=timezone.utc)
    result = add_business_minutes(monday_1030, 120)
    expected = datetime(2025, 12, 22, 12, 30, tzinfo=timezone.utc)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  10:30 + 120min = {result.strftime('%H:%M')} ✓")
    
    print("  [PASSED]")


def test_add_business_minutes_cross_day():
    """Test adding business minutes that cross to the next day."""
    print("\n=== Test: Add Business Minutes (Cross Day) ===")
    
    # Start at 17:00 Monday (90 min left), add 120 minutes
    # Should be: 90 min Monday + 30 min Tuesday = 30 min into Tuesday
    # Tuesday 08:30 + 30 = 09:00
    monday_5pm = datetime(2025, 12, 22, 17, 0, tzinfo=timezone.utc)
    result = add_business_minutes(monday_5pm, 120)
    expected = datetime(2025, 12, 23, 9, 0, tzinfo=timezone.utc)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  Monday 17:00 + 120min = Tuesday {result.strftime('%H:%M')} ✓")
    
    # Start at 18:00 Monday (30 min left), add 60 minutes
    # 30 min Monday + 30 min Tuesday = 09:00 Tuesday
    monday_6pm = datetime(2025, 12, 22, 18, 0, tzinfo=timezone.utc)
    result = add_business_minutes(monday_6pm, 60)
    expected = datetime(2025, 12, 23, 9, 0, tzinfo=timezone.utc)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  Monday 18:00 + 60min = Tuesday {result.strftime('%H:%M')} ✓")
    
    print("  [PASSED]")


def test_add_business_minutes_weekend():
    """Test adding business minutes over the weekend."""
    print("\n=== Test: Add Business Minutes (Over Weekend) ===")
    
    # Start Friday 17:00 (90 min left), add 480 minutes (8 hours)
    # Friday: 90 min
    # Saturday: 270 min (08:30-13:00)
    # Sunday: 0 (closed)
    # Monday: 120 min needed
    # Total: 90 + 270 + 0 + 120 = 480 ✓
    # Monday 08:30 + 120 = 10:30
    friday_5pm = datetime(2025, 12, 26, 17, 0, tzinfo=timezone.utc)  # Friday
    result = add_business_minutes(friday_5pm, 480)
    expected = datetime(2025, 12, 29, 10, 30, tzinfo=timezone.utc)  # Monday 10:30
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  Friday 17:00 + 480min (8h) = Monday {result.strftime('%Y-%m-%d %H:%M')} ✓")
    
    # Start Sunday 10:00, add 60 minutes -> should start counting from Monday 08:30
    sunday_10am = datetime(2025, 12, 28, 10, 0, tzinfo=timezone.utc)  # Sunday
    result = add_business_minutes(sunday_10am, 60)
    expected = datetime(2025, 12, 29, 9, 30, tzinfo=timezone.utc)  # Monday 09:30
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  Sunday 10:00 + 60min = Monday {result.strftime('%Y-%m-%d %H:%M')} ✓")
    
    print("  [PASSED]")


def test_add_business_minutes_before_open():
    """Test adding business minutes when starting before business hours."""
    print("\n=== Test: Add Business Minutes (Before Open) ===")
    
    # Start Monday 06:00 (before open), add 60 minutes
    # Should start counting from 08:30 -> 09:30
    monday_6am = datetime(2025, 12, 22, 6, 0, tzinfo=timezone.utc)
    result = add_business_minutes(monday_6am, 60)
    expected = datetime(2025, 12, 22, 9, 30, tzinfo=timezone.utc)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  Monday 06:00 + 60min = {result.strftime('%H:%M')} ✓")
    
    print("  [PASSED]")


def test_add_business_minutes_after_close():
    """Test adding business minutes when starting after business hours."""
    print("\n=== Test: Add Business Minutes (After Close) ===")
    
    # Start Monday 20:00 (after close), add 60 minutes
    # Should start counting from Tuesday 08:30 -> 09:30
    monday_8pm = datetime(2025, 12, 22, 20, 0, tzinfo=timezone.utc)
    result = add_business_minutes(monday_8pm, 60)
    expected = datetime(2025, 12, 23, 9, 30, tzinfo=timezone.utc)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  Monday 20:00 + 60min = Tuesday {result.strftime('%H:%M')} ✓")
    
    print("  [PASSED]")


def test_calculate_business_minutes_between():
    """Test calculation of business minutes between two datetimes."""
    print("\n=== Test: Calculate Business Minutes Between ===")
    
    # Same day, within business hours
    start = datetime(2025, 12, 22, 9, 0, tzinfo=timezone.utc)
    end = datetime(2025, 12, 22, 11, 30, tzinfo=timezone.utc)
    result = calculate_business_minutes_between(start, end)
    expected = 150  # 2.5 hours
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  09:00 to 11:30 same day: {result} minutes ✓")
    
    # Cross day
    start = datetime(2025, 12, 22, 17, 0, tzinfo=timezone.utc)  # Monday 17:00
    end = datetime(2025, 12, 23, 10, 0, tzinfo=timezone.utc)    # Tuesday 10:00
    result = calculate_business_minutes_between(start, end)
    # Monday: 17:00-18:30 = 90 min
    # Tuesday: 08:30-10:00 = 90 min
    # Total: 180 min
    expected = 180
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  Monday 17:00 to Tuesday 10:00: {result} minutes ✓")
    
    # Over weekend
    start = datetime(2025, 12, 26, 17, 0, tzinfo=timezone.utc)  # Friday 17:00
    end = datetime(2025, 12, 29, 10, 0, tzinfo=timezone.utc)    # Monday 10:00
    result = calculate_business_minutes_between(start, end)
    # Friday: 17:00-18:30 = 90 min
    # Saturday: 08:30-13:00 = 270 min
    # Sunday: 0 min
    # Monday: 08:30-10:00 = 90 min
    # Total: 450 min
    expected = 450
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  Friday 17:00 to Monday 10:00 (over weekend): {result} minutes ✓")
    
    print("  [PASSED]")


def test_compute_sla_due():
    """Test SLA due date computation for different ticket types."""
    print("\n=== Test: Compute SLA Due ===")
    
    # INFORMACAO: 2 hours (120 min)
    monday_10am = datetime(2025, 12, 22, 10, 0, tzinfo=timezone.utc)
    sla_due, target, policy = compute_sla_due("INFORMACAO", monday_10am)
    expected_due = datetime(2025, 12, 22, 12, 0, tzinfo=timezone.utc)
    assert sla_due == expected_due, f"Expected {expected_due}, got {sla_due}"
    assert target == 120, f"Expected target 120, got {target}"
    print(f"  INFORMACAO: 10:00 + 2h = {sla_due.strftime('%H:%M')} ✓")
    
    # MARCACAO: 3 hours (180 min)
    sla_due, target, policy = compute_sla_due("MARCACAO", monday_10am)
    expected_due = datetime(2025, 12, 22, 13, 0, tzinfo=timezone.utc)
    assert sla_due == expected_due, f"Expected {expected_due}, got {sla_due}"
    assert target == 180, f"Expected target 180, got {target}"
    print(f"  MARCACAO: 10:00 + 3h = {sla_due.strftime('%H:%M')} ✓")
    
    # ORCAMENTO_PNEUS: 8 hours (480 min)
    sla_due, target, policy = compute_sla_due("ORCAMENTO_PNEUS", monday_10am)
    expected_due = datetime(2025, 12, 22, 18, 0, tzinfo=timezone.utc)
    assert sla_due == expected_due, f"Expected {expected_due}, got {sla_due}"
    assert target == 480, f"Expected target 480, got {target}"
    print(f"  ORCAMENTO_PNEUS: 10:00 + 8h = {sla_due.strftime('%H:%M')} ✓")
    
    # ORCAMENTO late in day (should cross to next day)
    monday_4pm = datetime(2025, 12, 22, 16, 0, tzinfo=timezone.utc)
    sla_due, target, policy = compute_sla_due("ORCAMENTO_PNEUS", monday_4pm)
    # Monday 16:00-18:30 = 150 min
    # Need 480-150 = 330 min more
    # Tuesday 08:30 + 330 = 14:00
    expected_due = datetime(2025, 12, 23, 14, 0, tzinfo=timezone.utc)
    assert sla_due == expected_due, f"Expected {expected_due}, got {sla_due}"
    print(f"  ORCAMENTO_PNEUS: Monday 16:00 + 8h = Tuesday {sla_due.strftime('%H:%M')} ✓")
    
    print("  [PASSED]")


def test_sla_due_outside_business_hours():
    """Test SLA due when ticket created outside business hours."""
    print("\n=== Test: SLA Due Outside Business Hours ===")
    
    # Created on Sunday - should start Monday 08:30
    sunday_noon = datetime(2025, 12, 28, 12, 0, tzinfo=timezone.utc)
    sla_due, target, policy = compute_sla_due("INFORMACAO", sunday_noon)
    # Monday 08:30 + 120 min = 10:30
    expected_due = datetime(2025, 12, 29, 10, 30, tzinfo=timezone.utc)
    assert sla_due == expected_due, f"Expected {expected_due}, got {sla_due}"
    print(f"  INFORMACAO on Sunday 12:00: SLA due Monday {sla_due.strftime('%H:%M')} ✓")
    
    # Created at night (after hours) - should start next business day
    monday_11pm = datetime(2025, 12, 22, 23, 0, tzinfo=timezone.utc)
    sla_due, target, policy = compute_sla_due("INFORMACAO", monday_11pm)
    # Tuesday 08:30 + 120 min = 10:30
    expected_due = datetime(2025, 12, 23, 10, 30, tzinfo=timezone.utc)
    assert sla_due == expected_due, f"Expected {expected_due}, got {sla_due}"
    print(f"  INFORMACAO on Monday 23:00: SLA due Tuesday {sla_due.strftime('%H:%M')} ✓")
    
    # Created early morning (before open) - should start same day at 08:30
    monday_6am = datetime(2025, 12, 22, 6, 0, tzinfo=timezone.utc)
    sla_due, target, policy = compute_sla_due("INFORMACAO", monday_6am)
    # Monday 08:30 + 120 min = 10:30
    expected_due = datetime(2025, 12, 22, 10, 30, tzinfo=timezone.utc)
    assert sla_due == expected_due, f"Expected {expected_due}, got {sla_due}"
    print(f"  INFORMACAO on Monday 06:00: SLA due same day {sla_due.strftime('%H:%M')} ✓")
    
    print("  [PASSED]")


def run_all_tests():
    """Run all SLA tests."""
    print("=" * 60)
    print("Running SLA Business Hours Tests")
    print("=" * 60)
    
    tests = [
        test_business_hours_config,
        test_sla_targets,
        test_is_business_day,
        test_business_minutes_in_day,
        test_add_business_minutes_same_day,
        test_add_business_minutes_cross_day,
        test_add_business_minutes_weekend,
        test_add_business_minutes_before_open,
        test_add_business_minutes_after_close,
        test_calculate_business_minutes_between,
        test_compute_sla_due,
        test_sla_due_outside_business_hours,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAILED] {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Tests completed: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


# ============== HOLIDAY TESTS ==============
def test_fixed_holiday():
    """Test that a fixed holiday is correctly identified."""
    print("\n=== Test: Fixed Holiday ===")
    import services.sla_service as sla
    
    # Save original holidays
    original_holidays = sla.HOLIDAYS.copy()
    original_recurring = sla.RECURRING_HOLIDAYS.copy()
    
    # Set a fixed holiday
    test_date = date(2026, 6, 10)  # 10 de Junho (Portugal Day)
    sla.HOLIDAYS = [test_date]
    sla.RECURRING_HOLIDAYS = []
    
    # Test is_holiday
    assert is_holiday(test_date) == True, "June 10, 2026 should be a holiday"
    assert is_business_day(test_date) == False, "Holiday should not be a business day"
    
    # Test that business hours return None for holiday
    hours = get_business_hours_for_day(test_date)
    assert hours is None, "Holiday should have no business hours"
    
    # Test that non-holiday is still working
    non_holiday = date(2026, 6, 9)  # Day before
    assert is_holiday(non_holiday) == False, "June 9 should not be a holiday"
    
    # Restore
    sla.HOLIDAYS = original_holidays
    sla.RECURRING_HOLIDAYS = original_recurring
    
    print("  Fixed holiday identified correctly ✓")
    print("  [PASSED]")


def test_recurring_annual_holiday():
    """Test that recurring annual holidays are correctly identified across years."""
    print("\n=== Test: Recurring Annual Holiday ===")
    import services.sla_service as sla
    
    # Save original holidays
    original_holidays = sla.HOLIDAYS.copy()
    original_recurring = sla.RECURRING_HOLIDAYS.copy()
    
    # Set a recurring holiday (Christmas - December 25)
    sla.HOLIDAYS = []
    sla.RECURRING_HOLIDAYS = [(12, 25)]  # month, day
    
    # Test different years
    assert is_holiday(date(2025, 12, 25)) == True, "Christmas 2025 should be a holiday"
    assert is_holiday(date(2026, 12, 25)) == True, "Christmas 2026 should be a holiday"
    assert is_holiday(date(2027, 12, 25)) == True, "Christmas 2027 should be a holiday"
    
    # Test non-Christmas days
    assert is_holiday(date(2026, 12, 24)) == False, "December 24 should not be a holiday"
    assert is_holiday(date(2026, 12, 26)) == False, "December 26 should not be a holiday"
    
    # Restore
    sla.HOLIDAYS = original_holidays
    sla.RECURRING_HOLIDAYS = original_recurring
    
    print("  Recurring holiday works across years ✓")
    print("  [PASSED]")


def test_sla_across_holiday():
    """Test that SLA calculation correctly skips holidays."""
    print("\n=== Test: SLA Calculation Across Holiday ===")
    import services.sla_service as sla
    
    # Save original holidays
    original_holidays = sla.HOLIDAYS.copy()
    original_recurring = sla.RECURRING_HOLIDAYS.copy()
    
    # Set a fixed holiday on a Wednesday
    holiday_date = date(2026, 4, 1)  # Wednesday, April 1, 2026
    sla.HOLIDAYS = [holiday_date]
    sla.RECURRING_HOLIDAYS = []
    
    # Start on Tuesday at 17:00 (1.5 hours before close)
    # 1.5 hours = 90 minutes available on Tuesday
    # Wednesday is a holiday (0 minutes)
    # Thursday should provide the rest
    start = datetime(2026, 3, 31, 17, 0, tzinfo=timezone.utc)  # Tuesday
    
    # Add 180 minutes (3 hours)
    # 90 min on Tuesday -> 90 min remaining
    # Skip Wednesday (holiday)
    # 90 min on Thursday starting at 08:30 -> ends at 10:00
    result = add_business_minutes(start, 180)
    
    # Should skip the holiday and land on Thursday
    assert result.date() == date(2026, 4, 2), f"Should land on Thursday, got {result.date()}"
    
    print(f"  Start: {start} (Tuesday)")
    print(f"  Added: 180 minutes")
    print(f"  Result: {result} (Thursday)")
    print("  Holiday was correctly skipped ✓")
    
    # Restore
    sla.HOLIDAYS = original_holidays
    sla.RECURRING_HOLIDAYS = original_recurring
    
    print("  [PASSED]")


def test_saturday_plus_holiday():
    """Test that Saturday + holiday on Monday works correctly."""
    print("\n=== Test: Saturday + Holiday on Monday ===")
    import services.sla_service as sla
    
    # Save original holidays
    original_holidays = sla.HOLIDAYS.copy()
    original_recurring = sla.RECURRING_HOLIDAYS.copy()
    
    # Set Monday as a holiday
    # Find a Monday in 2026
    monday_holiday = date(2026, 4, 6)  # Monday, April 6, 2026
    sla.HOLIDAYS = [monday_holiday]
    sla.RECURRING_HOLIDAYS = []
    
    # Start on Saturday at 12:00 (1 hour before close on Saturday)
    # Saturday: 1 hour = 60 minutes
    # Sunday: closed
    # Monday: holiday (0 minutes)
    # Tuesday should provide the rest
    start = datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc)  # Saturday
    
    # Add 120 minutes (2 hours)
    # 60 min on Saturday -> 60 min remaining
    # Skip Sunday (closed)
    # Skip Monday (holiday)
    # 60 min on Tuesday starting at 08:30 -> ends at 09:30
    result = add_business_minutes(start, 120)
    
    assert result.date() == date(2026, 4, 7), f"Should land on Tuesday, got {result.date()}"
    
    print(f"  Start: {start} (Saturday)")
    print(f"  Added: 120 minutes")
    print(f"  Result: {result} (Tuesday - skipped Sunday and holiday Monday)")
    
    # Restore
    sla.HOLIDAYS = original_holidays
    sla.RECURRING_HOLIDAYS = original_recurring
    
    print("  [PASSED]")


def test_sunday_still_closed():
    """Test that Sunday remains closed even with holidays configured."""
    print("\n=== Test: Sunday Still Closed ===")
    import services.sla_service as sla
    
    # Save original holidays
    original_holidays = sla.HOLIDAYS.copy()
    original_recurring = sla.RECURRING_HOLIDAYS.copy()
    
    # Configure some holidays
    sla.HOLIDAYS = [date(2026, 6, 10)]
    sla.RECURRING_HOLIDAYS = [(12, 25)]
    
    # Test various Sundays
    sundays = [
        date(2026, 4, 5),
        date(2026, 5, 3),
        date(2026, 6, 7),
    ]
    
    for sunday in sundays:
        assert is_business_day(sunday) == False, f"{sunday} should not be a business day (Sunday)"
        hours = get_business_hours_for_day(sunday)
        assert hours is None, f"{sunday} should have no business hours (Sunday)"
    
    print("  Sundays remain closed regardless of holiday config ✓")
    
    # Restore
    sla.HOLIDAYS = original_holidays
    sla.RECURRING_HOLIDAYS = original_recurring
    
    print("  [PASSED]")


def run_holiday_tests():
    """Run all holiday-related tests."""
    tests = [
        test_fixed_holiday,
        test_recurring_annual_holiday,
        test_sla_across_holiday,
        test_saturday_plus_holiday,
        test_sunday_still_closed,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"  [FAILED] {e}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {e}")
    
    print("\n" + "=" * 60)
    print(f"Holiday tests: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    holiday_success = run_holiday_tests()
    sys.exit(0 if (success and holiday_success) else 1)
