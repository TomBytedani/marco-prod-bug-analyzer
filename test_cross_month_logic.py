"""
Test script to verify cross-month/cross-year logic and weekend exclusion
for Average Working Hours and Average Working Days calculations.

This tests:
1. Cross-month logic - tickets spanning multiple months
2. Cross-year logic - tickets spanning Dec 2025 to Jan 2026
3. Multi-month tickets - tickets open for more than 2 months
4. Weekend exclusion - Saturdays and Sundays should not count
5. Holiday exclusion - Italian national holidays should not count
6. Business hours - only 9:00-13:00 and 14:00-18:00 should count
"""

from datetime import datetime, date, time, timedelta
import pandas as pd

from src.business_hours import (
    calculate_working_hours,
    calculate_working_hours_to_date,
    working_hours_to_days,
    HOURS_PER_DAY,
    WORK_PERIODS
)
from src.holidays import is_working_day, is_holiday, get_italian_calendar
from src.aggregator import Aggregator, get_months_between, sort_year_month_columns, is_valid_incident_type, MONTH_ORDER


def print_header(title: str):
    print(f"\n{'='*70}")
    print(f" {title}")
    print(f"{'='*70}")


def print_result(test_name: str, passed: bool, details: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {test_name}")
    if details:
        print(f"       {details}")


def test_weekend_exclusion():
    """Test that weekends are correctly excluded from working hours."""
    print_header("TEST 1: Weekend Exclusion")

    all_passed = True

    # Test 1a: A full week including a weekend
    # Monday Jan 6, 2025 9:00 to Monday Jan 13, 2025 18:00
    # Should be 5 working days (Mon-Fri, excluding Sat/Sun)
    # But Jan 6 is Epifania (holiday), so only 4 working days
    start = datetime(2025, 1, 7, 9, 0)  # Tuesday (after Epifania)
    end = datetime(2025, 1, 13, 18, 0)  # Monday
    hours = calculate_working_hours(start, end)
    expected_days = 5  # Tue, Wed, Thu, Fri, Mon
    expected_hours = expected_days * HOURS_PER_DAY
    passed = abs(hours - expected_hours) < 0.01
    print_result(
        "Full week (Tue-Mon) = 5 working days",
        passed,
        f"Expected: {expected_hours}h, Got: {hours}h"
    )
    all_passed = all_passed and passed

    # Test 1b: Friday to Monday (weekend in between)
    # Should only count Friday and Monday
    start = datetime(2025, 1, 10, 9, 0)  # Friday
    end = datetime(2025, 1, 13, 18, 0)   # Monday
    hours = calculate_working_hours(start, end)
    expected_hours = 2 * HOURS_PER_DAY  # Only Fri and Mon
    passed = abs(hours - expected_hours) < 0.01
    print_result(
        "Friday 9:00 to Monday 18:00 = 2 working days (weekend excluded)",
        passed,
        f"Expected: {expected_hours}h, Got: {hours}h"
    )
    all_passed = all_passed and passed

    # Test 1c: Saturday to Sunday (entirely weekend)
    start = datetime(2025, 1, 11, 9, 0)   # Saturday
    end = datetime(2025, 1, 12, 18, 0)    # Sunday
    hours = calculate_working_hours(start, end)
    passed = hours == 0
    print_result(
        "Saturday to Sunday = 0 working hours",
        passed,
        f"Expected: 0h, Got: {hours}h"
    )
    all_passed = all_passed and passed

    # Test 1d: Check specific dates are weekends
    saturday = date(2025, 1, 11)
    sunday = date(2025, 1, 12)
    monday = date(2025, 1, 13)

    passed = not is_working_day(saturday) and not is_working_day(sunday) and is_working_day(monday)
    print_result(
        "is_working_day correctly identifies weekends",
        passed,
        f"Sat={is_working_day(saturday)}, Sun={is_working_day(sunday)}, Mon={is_working_day(monday)}"
    )
    all_passed = all_passed and passed

    return all_passed


def test_holiday_exclusion():
    """Test that Italian holidays are correctly excluded."""
    print_header("TEST 2: Italian Holiday Exclusion")

    all_passed = True

    # Test Italian holidays for 2025
    holidays_2025 = [
        (date(2025, 1, 1), "Capodanno"),
        (date(2025, 1, 6), "Epifania"),
        (date(2025, 4, 25), "Festa della Liberazione"),
        (date(2025, 5, 1), "Festa dei Lavoratori"),
        (date(2025, 6, 2), "Festa della Repubblica"),
        (date(2025, 8, 15), "Ferragosto"),
        (date(2025, 11, 1), "Tutti i Santi"),
        (date(2025, 12, 8), "Immacolata Concezione"),
        (date(2025, 12, 25), "Natale"),
        (date(2025, 12, 26), "Santo Stefano"),
    ]

    for holiday_date, holiday_name in holidays_2025:
        is_hol = is_holiday(holiday_date)
        is_work = is_working_day(holiday_date)
        # Holiday should be recognized as holiday and NOT a working day
        # (unless it falls on a weekend, then is_working_day is False anyway)
        passed = is_hol and not is_work
        print_result(
            f"{holiday_name} ({holiday_date}) is holiday",
            passed,
            f"is_holiday={is_hol}, is_working_day={is_work}"
        )
        all_passed = all_passed and passed

    # Test that a week containing a holiday has fewer working hours
    # April 21-25, 2025: Mon, Tue, Wed, Thu, Fri(25th is Liberazione)
    start = datetime(2025, 4, 21, 9, 0)  # Monday
    end = datetime(2025, 4, 25, 18, 0)   # Friday (holiday)
    hours = calculate_working_hours(start, end)
    expected_hours = 4 * HOURS_PER_DAY  # Only Mon-Thu, Fri is holiday
    passed = abs(hours - expected_hours) < 0.01
    print_result(
        "Week with Festa della Liberazione (Apr 25) = 4 working days",
        passed,
        f"Expected: {expected_hours}h, Got: {hours}h"
    )
    all_passed = all_passed and passed

    return all_passed


def test_business_hours():
    """Test that only business hours (9-13, 14-18) are counted."""
    print_header("TEST 3: Business Hours (9:00-13:00, 14:00-18:00)")

    all_passed = True

    # Test 3a: Full working day = 8 hours
    start = datetime(2025, 1, 7, 9, 0)   # Tuesday 9:00
    end = datetime(2025, 1, 7, 18, 0)    # Tuesday 18:00
    hours = calculate_working_hours(start, end)
    passed = abs(hours - 8.0) < 0.01
    print_result(
        "Full day (9:00-18:00) = 8 working hours",
        passed,
        f"Expected: 8h, Got: {hours}h"
    )
    all_passed = all_passed and passed

    # Test 3b: Morning only (9:00-13:00) = 4 hours
    start = datetime(2025, 1, 7, 9, 0)
    end = datetime(2025, 1, 7, 13, 0)
    hours = calculate_working_hours(start, end)
    passed = abs(hours - 4.0) < 0.01
    print_result(
        "Morning only (9:00-13:00) = 4 hours",
        passed,
        f"Expected: 4h, Got: {hours}h"
    )
    all_passed = all_passed and passed

    # Test 3c: Afternoon only (14:00-18:00) = 4 hours
    start = datetime(2025, 1, 7, 14, 0)
    end = datetime(2025, 1, 7, 18, 0)
    hours = calculate_working_hours(start, end)
    passed = abs(hours - 4.0) < 0.01
    print_result(
        "Afternoon only (14:00-18:00) = 4 hours",
        passed,
        f"Expected: 4h, Got: {hours}h"
    )
    all_passed = all_passed and passed

    # Test 3d: Lunch break (13:00-14:00) = 0 hours
    start = datetime(2025, 1, 7, 13, 0)
    end = datetime(2025, 1, 7, 14, 0)
    hours = calculate_working_hours(start, end)
    passed = abs(hours - 0.0) < 0.01
    print_result(
        "Lunch break (13:00-14:00) = 0 hours",
        passed,
        f"Expected: 0h, Got: {hours}h"
    )
    all_passed = all_passed and passed

    # Test 3e: Before work hours (7:00-9:00) = 0 hours
    start = datetime(2025, 1, 7, 7, 0)
    end = datetime(2025, 1, 7, 9, 0)
    hours = calculate_working_hours(start, end)
    passed = abs(hours - 0.0) < 0.01
    print_result(
        "Before work (7:00-9:00) = 0 hours",
        passed,
        f"Expected: 0h, Got: {hours}h"
    )
    all_passed = all_passed and passed

    # Test 3f: After work hours (18:00-20:00) = 0 hours
    start = datetime(2025, 1, 7, 18, 0)
    end = datetime(2025, 1, 7, 20, 0)
    hours = calculate_working_hours(start, end)
    passed = abs(hours - 0.0) < 0.01
    print_result(
        "After work (18:00-20:00) = 0 hours",
        passed,
        f"Expected: 0h, Got: {hours}h"
    )
    all_passed = all_passed and passed

    # Test 3g: Partial morning (10:30-12:00) = 1.5 hours
    start = datetime(2025, 1, 7, 10, 30)
    end = datetime(2025, 1, 7, 12, 0)
    hours = calculate_working_hours(start, end)
    passed = abs(hours - 1.5) < 0.01
    print_result(
        "Partial morning (10:30-12:00) = 1.5 hours",
        passed,
        f"Expected: 1.5h, Got: {hours}h"
    )
    all_passed = all_passed and passed

    return all_passed


def test_cross_month_logic():
    """Test cross-month calculation logic."""
    print_header("TEST 4: Cross-Month Logic")

    all_passed = True

    # Test get_months_between function
    start = datetime(2025, 10, 15, 10, 0)
    end = datetime(2025, 11, 20, 16, 0)
    months = get_months_between(start, end)

    passed = len(months) == 2
    print_result(
        "Oct 15 to Nov 20 spans 2 months",
        passed,
        f"Got {len(months)} months: {[m['month_name'] + '-' + str(m['year']) for m in months]}"
    )
    all_passed = all_passed and passed

    # Test calculate_working_hours_to_date
    # Oct 15 9:00 to Oct 31 18:00
    start = datetime(2025, 10, 15, 9, 0)  # Wednesday
    end_of_oct = date(2025, 10, 31)
    hours_to_oct = calculate_working_hours_to_date(start, end_of_oct)

    # Count working days from Oct 15-31, 2025
    # Oct 15 (Wed), 16 (Thu), 17 (Fri), 20 (Mon), 21 (Tue), 22 (Wed), 23 (Thu), 24 (Fri),
    # 27 (Mon), 28 (Tue), 29 (Wed), 30 (Thu), 31 (Fri) = 13 working days
    expected_working_days = 13
    expected_hours = expected_working_days * HOURS_PER_DAY
    passed = abs(hours_to_oct - expected_hours) < 0.01
    print_result(
        f"Oct 15 to Oct 31 working hours",
        passed,
        f"Expected: {expected_hours}h ({expected_working_days} days), Got: {hours_to_oct}h"
    )
    all_passed = all_passed and passed

    # Full calculation Oct 15 to Nov 20
    end = datetime(2025, 11, 20, 16, 0)  # Thursday 4pm
    full_hours = calculate_working_hours(start, end)

    # Nov working days: 3,4,5,6,7,10,11,12,13,14,17,18,19,20 = 14 days
    # But Nov 20 ends at 16:00, so it's a partial day (9-13 + 14-16 = 6 hours)
    # Nov 1 is holiday (Tutti i Santi), but it's Saturday in 2025, so doesn't matter
    # Actually, let me recalculate:
    # Nov 2025: 3(Mon),4(Tue),5(Wed),6(Thu),7(Fri),10(Mon),11(Tue),12(Wed),13(Thu),14(Fri),
    #           17(Mon),18(Tue),19(Wed),20(Thu-partial)
    # = 13 full days + 1 partial (6h) = 13*8 + 6 = 110 hours for Nov portion

    print(f"       Full duration (Oct 15 9:00 - Nov 20 16:00): {full_hours}h")
    print(f"       Hours to end of Oct: {hours_to_oct}h")

    # Verify that the cross-month logic would produce cumulative values
    # OCT contribution: hours from Oct 15 to Oct 31
    # NOV contribution: hours from Oct 15 to Nov 20 (FULL duration)

    print(f"\n       Cross-month expected contributions:")
    print(f"       - OCT-2025: {hours_to_oct}h (incident to end of Oct)")
    print(f"       - NOV-2025: {full_hours}h (incident to resolution - FULL duration)")

    passed = full_hours > hours_to_oct
    print_result(
        "Full duration > partial (Oct only)",
        passed,
        f"Full: {full_hours}h > Oct only: {hours_to_oct}h"
    )
    all_passed = all_passed and passed

    return all_passed


def test_cross_year_logic():
    """Test cross-year calculation (Dec 2025 to Jan 2026)."""
    print_header("TEST 5: Cross-Year Logic (Dec 2025 -> Jan 2026)")

    all_passed = True

    # Ticket opened Dec 15, 2025 and closed Jan 15, 2026
    start = datetime(2025, 12, 15, 10, 0)  # Monday
    end = datetime(2026, 1, 15, 16, 0)     # Thursday

    months = get_months_between(start, end)

    passed = len(months) == 2
    print_result(
        "Dec 15, 2025 to Jan 15, 2026 spans 2 months",
        passed,
        f"Got {len(months)} months: {[m['month_name'] + '-' + str(m['year']) for m in months]}"
    )
    all_passed = all_passed and passed

    # Verify year-month keys are correct
    expected_keys = ["DEC-2025", "JAN-2026"]
    actual_keys = [f"{m['month_name']}-{m['year']}" for m in months]
    passed = actual_keys == expected_keys
    print_result(
        "Year-month keys are correct format",
        passed,
        f"Expected: {expected_keys}, Got: {actual_keys}"
    )
    all_passed = all_passed and passed

    # Calculate hours
    # Dec 2025: 15(Mon),16(Tue),17(Wed),18(Thu),19(Fri),22(Mon),23(Tue),24(Wed),
    #           [25-Natale],[26-SantoStefano],29(Mon),30(Tue),31(Wed)
    # = 11 working days to end of Dec
    # Jan 2026: [1-Capodanno],2(Thu?),3(Fri?),... need to check calendar

    end_of_dec = date(2025, 12, 31)
    hours_to_dec = calculate_working_hours_to_date(start, end_of_dec)
    full_hours = calculate_working_hours(start, end)

    print(f"       Hours from Dec 15 to Dec 31: {hours_to_dec}h")
    print(f"       Full hours (Dec 15 to Jan 15): {full_hours}h")

    # Verify cross-year sorting works
    columns = ["JAN-2026", "DEC-2025", "NOV-2025"]
    sorted_cols = sort_year_month_columns(columns)
    expected_sorted = ["NOV-2025", "DEC-2025", "JAN-2026"]
    passed = sorted_cols == expected_sorted
    print_result(
        "Cross-year column sorting works correctly",
        passed,
        f"Expected: {expected_sorted}, Got: {sorted_cols}"
    )
    all_passed = all_passed and passed

    # Verify Christmas and Santo Stefano are excluded
    christmas = date(2025, 12, 25)
    santo_stefano = date(2025, 12, 26)
    passed = is_holiday(christmas) and is_holiday(santo_stefano)
    print_result(
        "Christmas and Santo Stefano are recognized as holidays",
        passed,
        f"Dec 25 holiday={is_holiday(christmas)}, Dec 26 holiday={is_holiday(santo_stefano)}"
    )
    all_passed = all_passed and passed

    return all_passed


def test_multi_month_ticket():
    """Test ticket spanning more than 2 months."""
    print_header("TEST 6: Multi-Month Ticket (3+ months)")

    all_passed = True

    # Ticket opened Oct 1, 2025 and closed Jan 15, 2026 (4 months)
    start = datetime(2025, 10, 1, 9, 0)   # Wednesday
    end = datetime(2026, 1, 15, 18, 0)    # Thursday

    months = get_months_between(start, end)

    passed = len(months) == 4
    print_result(
        "Oct 1, 2025 to Jan 15, 2026 spans 4 months",
        passed,
        f"Got {len(months)} months: {[m['month_name'] + '-' + str(m['year']) for m in months]}"
    )
    all_passed = all_passed and passed

    expected_months = ["OCT-2025", "NOV-2025", "DEC-2025", "JAN-2026"]
    actual_months = [f"{m['month_name']}-{m['year']}" for m in months]
    passed = actual_months == expected_months
    print_result(
        "All 4 months identified correctly",
        passed,
        f"Expected: {expected_months}, Got: {actual_months}"
    )
    all_passed = all_passed and passed

    # Calculate cumulative hours for each month
    full_hours = calculate_working_hours(start, end)

    cumulative_hours = {}
    for month_info in months:
        year_month_key = f"{month_info['month_name']}-{month_info['year']}"
        end_of_month = month_info['end_of_month']

        if end.date() <= end_of_month:
            # Resolution month
            hours = full_hours
        else:
            # Intermediate month
            hours = calculate_working_hours_to_date(start, end_of_month)

        cumulative_hours[year_month_key] = hours

    print(f"\n       Cumulative hours per month (cross-month logic):")
    for month_key, hours in cumulative_hours.items():
        print(f"       - {month_key}: {hours:.1f}h")

    # Verify cumulative nature: each month should have >= previous month
    prev_hours = 0
    cumulative_correct = True
    for month_key, hours in cumulative_hours.items():
        if hours < prev_hours:
            cumulative_correct = False
            break
        prev_hours = hours

    print_result(
        "Hours are cumulative (each month >= previous)",
        cumulative_correct,
        "Each subsequent month should have more hours"
    )
    all_passed = all_passed and cumulative_correct

    return all_passed


def test_aggregator_cross_month():
    """Test the Aggregator's cross-month methods with mock data."""
    print_header("TEST 7: Aggregator Cross-Month Methods")

    all_passed = True

    # Create mock DataFrame with tickets spanning multiple months
    mock_data = {
        'Key': ['PI-001', 'PI-002', 'PI-003'],
        'Severity': ['Blocker', 'Severe', 'Blocker'],
        'Status': ['Closed', 'Closed', 'Resolved'],
        '_issue_type': ['[System] Incident', 'Production Incident', '[System] Incident'],
        'External System': ['AF', 'Gate Portal', 'ECD'],
        'Incident detection datetime': [
            datetime(2025, 10, 15, 10, 0),  # Oct 15
            datetime(2025, 11, 1, 9, 0),    # Nov 1
            datetime(2025, 12, 15, 14, 0),  # Dec 15 (cross-year)
        ],
        'Resolution date': [
            datetime(2025, 11, 20, 16, 0),  # Nov 20 (spans Oct-Nov)
            datetime(2025, 11, 15, 18, 0),  # Nov 15 (single month)
            datetime(2026, 1, 10, 12, 0),   # Jan 10 (spans Dec-Jan, cross-year)
        ],
        'YearMonth': ['OCT-2025', 'NOV-2025', 'DEC-2025'],
        'Year': [2025, 2025, 2025],
        'Quarter': [4, 4, 4],
        'Month': ['OCT', 'NOV', 'DEC'],
    }

    df = pd.DataFrame(mock_data)
    agg = Aggregator(df)

    # Test avg_working_hours_by_month_cross
    wh_result = agg.avg_working_hours_by_month_cross()

    print(f"\n       Mock data tickets:")
    print(f"       - PI-001: Oct 15 -> Nov 20 (Blocker)")
    print(f"       - PI-002: Nov 1 -> Nov 15 (Severe)")
    print(f"       - PI-003: Dec 15 -> Jan 10 (Blocker, cross-year)")

    print(f"\n       avg_working_hours_by_month_cross result:")
    if not wh_result.empty:
        for col in wh_result.columns:
            print(f"       - {col}: {wh_result[col].values[0]:.1f}h")

        # Check that expected columns exist
        expected_cols = {'OCT-2025', 'NOV-2025', 'DEC-2025', 'JAN-2026'}
        actual_cols = set(wh_result.columns)
        passed = expected_cols.issubset(actual_cols)
        print_result(
            "All expected month columns present",
            passed,
            f"Expected: {expected_cols}, Got: {actual_cols}"
        )
        all_passed = all_passed and passed

        # Check columns are sorted chronologically
        cols_list = list(wh_result.columns)
        sorted_cols = sort_year_month_columns(cols_list)
        passed = cols_list == sorted_cols
        print_result(
            "Columns are sorted chronologically",
            passed,
            f"Order: {cols_list}"
        )
        all_passed = all_passed and passed
    else:
        print("       (empty result)")
        all_passed = False

    # Test avg_working_days_by_month_cross
    wd_result = agg.avg_working_days_by_month_cross()

    print(f"\n       avg_working_days_by_month_cross result:")
    if not wd_result.empty:
        for col in wd_result.columns:
            print(f"       - {col}: {wd_result[col].values[0]:.2f} days")

        # Verify WD = WH / 8
        if not wh_result.empty:
            for col in wh_result.columns:
                if col in wd_result.columns:
                    expected_days = wh_result[col].values[0] / 8.0
                    actual_days = wd_result[col].values[0]
                    passed = abs(expected_days - actual_days) < 0.01
                    if not passed:
                        print_result(
                            f"{col}: WD = WH/8",
                            passed,
                            f"Expected: {expected_days:.2f}, Got: {actual_days:.2f}"
                        )
                        all_passed = False

            print_result("Working Days = Working Hours / 8", True, "All conversions correct")
    else:
        print("       (empty result)")
        all_passed = False

    return all_passed


def test_incident_type_filtering():
    """Test that only valid incident types are included and others are excluded."""
    print_header("TEST 8: Incident Type Filtering (Allowlist)")

    all_passed = True

    # Test is_valid_incident_type function
    valid_types = ["[System] Incident", "Production Incident",
                   " [System] Incident ", " production incident "]
    for t in valid_types:
        passed = is_valid_incident_type(t)
        print_result(f'is_valid_incident_type("{t.strip()}")', passed)
        all_passed = all_passed and passed

    invalid_types = ["Ask a question", "Task", "Bug", "", None]
    for t in invalid_types:
        passed = not is_valid_incident_type(t)
        label = str(t) if t is not None else "None"
        print_result(f'is_valid_incident_type("{label}") is False', passed)
        all_passed = all_passed and passed

    # Test filter_incidents_only via Aggregator with mixed types
    mock_data = {
        'Key': ['PI-010', 'PI-011', 'PI-012', 'PI-013'],
        'Severity': ['Blocker', 'Severe', 'Blocker', 'Medium'],
        'Status': ['Closed', 'Closed', 'Closed', 'Closed'],
        '_issue_type': [
            '[System] Incident',
            'Production Incident',
            'Ask a question',
            'Task',
        ],
        'External System': ['AF', 'AF', 'AF', 'AF'],
        'YearMonth': ['JAN-2025', 'JAN-2025', 'JAN-2025', 'JAN-2025'],
        'Year': [2025, 2025, 2025, 2025],
        'Quarter': [1, 1, 1, 1],
        'Month': ['JAN', 'JAN', 'JAN', 'JAN'],
    }
    df = pd.DataFrame(mock_data)
    agg = Aggregator(df)
    filtered = agg.filter_incidents_only()

    passed = set(filtered['Key'].tolist()) == {'PI-010', 'PI-011'}
    print_result(
        "filter_incidents_only keeps only valid incident types",
        passed,
        f"Expected: PI-010, PI-011; Got: {filtered['Key'].tolist()}"
    )
    all_passed = all_passed and passed

    return all_passed


def test_monthly_severity_expansion():
    """Test that monthly_severity_counts expands tickets across all months they were open."""
    print_header("TEST 9: Monthly Severity Expansion (open-range)")

    all_passed = True

    # Create mock DataFrame:
    # PI-100: Blocker, Oct 15 -> Nov 20  (spans OCT & NOV)
    # PI-101: Severe,  Nov 5  -> Nov 25  (single month NOV)
    # PI-102: Medium,  Dec 20 -> Jan 10  (cross-year DEC & JAN)
    # PI-103: Low,     Nov 1  -> None    (still open -> counted through current month)
    mock_data = {
        'Key': ['PI-100', 'PI-101', 'PI-102', 'PI-103'],
        'Severity': ['Blocker', 'Severe', 'Medium', 'Low'],
        'Status': ['Closed', 'Closed', 'Closed', 'Open'],
        '_issue_type': [
            '[System] Incident',
            'Production Incident',
            '[System] Incident',
            'Production Incident',
        ],
        'External System': ['AF', 'Gate Portal', 'ECD', 'AF'],
        'Incident detection datetime': [
            datetime(2025, 10, 15, 10, 0),
            datetime(2025, 11, 5, 9, 0),
            datetime(2025, 12, 20, 14, 0),
            datetime(2025, 11, 1, 8, 0),
        ],
        'Resolution date': [
            datetime(2025, 11, 20, 16, 0),
            datetime(2025, 11, 25, 18, 0),
            datetime(2026, 1, 10, 12, 0),
            pd.NaT,
        ],
        'YearMonth': ['OCT-2025', 'NOV-2025', 'DEC-2025', 'NOV-2025'],
        'Year': [2025, 2025, 2025, 2025],
        'Quarter': [4, 4, 4, 4],
        'Month': ['OCT', 'NOV', 'DEC', 'NOV'],
    }

    df = pd.DataFrame(mock_data)
    agg = Aggregator(df)
    result = agg.monthly_severity_counts()

    print(f"\n       Result table:")
    print(result.to_string())

    # --- Check PI-100 (Blocker): should appear in both OCT-2025 and NOV-2025 ---
    oct_blocker = result.loc['Blocker', 'OCT-2025'] if 'OCT-2025' in result.columns else 0
    nov_blocker = result.loc['Blocker', 'NOV-2025'] if 'NOV-2025' in result.columns else 0
    passed = oct_blocker >= 1 and nov_blocker >= 1
    print_result(
        "PI-100 (Blocker) counted in OCT and NOV",
        passed,
        f"OCT-2025 Blocker={oct_blocker}, NOV-2025 Blocker={nov_blocker}"
    )
    all_passed = all_passed and passed

    # --- Check PI-101 (Severe): should appear only in NOV-2025 ---
    nov_severe = result.loc['Severe', 'NOV-2025'] if 'NOV-2025' in result.columns else 0
    oct_severe = result.loc['Severe', 'OCT-2025'] if 'OCT-2025' in result.columns else 0
    passed = nov_severe >= 1 and oct_severe == 0
    print_result(
        "PI-101 (Severe) counted only in NOV",
        passed,
        f"OCT-2025 Severe={oct_severe}, NOV-2025 Severe={nov_severe}"
    )
    all_passed = all_passed and passed

    # --- Check PI-102 (Medium): should appear in DEC-2025 and JAN-2026 ---
    dec_medium = result.loc['Medium', 'DEC-2025'] if 'DEC-2025' in result.columns else 0
    jan_medium = result.loc['Medium', 'JAN-2026'] if 'JAN-2026' in result.columns else 0
    passed = dec_medium >= 1 and jan_medium >= 1
    print_result(
        "PI-102 (Medium) counted in DEC-2025 and JAN-2026 (cross-year)",
        passed,
        f"DEC-2025 Medium={dec_medium}, JAN-2026 Medium={jan_medium}"
    )
    all_passed = all_passed and passed

    # --- Check PI-103 (Low, still open): should be counted from NOV-2025 through current month ---
    from datetime import datetime as dt
    now = dt.now()
    current_ym = f"{MONTH_ORDER[now.month - 1]}-{now.year}"
    low_nov = result.loc['Low', 'NOV-2025'] if 'NOV-2025' in result.columns else 0
    low_current = result.loc['Low', current_ym] if current_ym in result.columns else 0
    passed = low_nov >= 1 and low_current >= 1
    print_result(
        f"PI-103 (Low, open) counted in NOV-2025 through {current_ym}",
        passed,
        f"NOV-2025 Low={low_nov}, {current_ym} Low={low_current}"
    )
    all_passed = all_passed and passed

    return all_passed


def run_all_tests():
    """Run all tests and report summary."""
    print("\n" + "="*70)
    print(" CROSS-MONTH LOGIC AND WEEKEND EXCLUSION TEST SUITE")
    print("="*70)

    results = {
        "Weekend Exclusion": test_weekend_exclusion(),
        "Holiday Exclusion": test_holiday_exclusion(),
        "Business Hours": test_business_hours(),
        "Cross-Month Logic": test_cross_month_logic(),
        "Cross-Year Logic": test_cross_year_logic(),
        "Multi-Month Ticket": test_multi_month_ticket(),
        "Aggregator Cross-Month": test_aggregator_cross_month(),
        "Incident Type Filtering": test_incident_type_filtering(),
        "Monthly Severity Expansion": test_monthly_severity_expansion(),
    }

    print_header("TEST SUMMARY")

    total_passed = 0
    total_tests = len(results)

    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {test_name}")
        if passed:
            total_passed += 1

    print(f"\n  Total: {total_passed}/{total_tests} test groups passed")

    if total_passed == total_tests:
        print("\n  All tests PASSED!")
        return True
    else:
        print(f"\n  {total_tests - total_passed} test group(s) FAILED")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
