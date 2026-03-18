"""
Business Hours Calculator.
Calculates working hours between two datetimes, excluding:
- Weekends (Saturday, Sunday)
- Italian national holidays
- Non-working hours (only 9:00-13:00 and 14:00-18:00 are counted)
- Lunch break (13:00-14:00)
"""

from datetime import datetime, date, time, timedelta
from typing import Optional, Tuple, List

from .holidays import is_working_day


# Working hours configuration
WORK_PERIODS: List[Tuple[time, time]] = [
    (time(9, 0), time(13, 0)),   # Morning: 4 hours
    (time(14, 0), time(18, 0)),  # Afternoon: 4 hours
]
HOURS_PER_DAY = 8.0  # Total working hours per day
WORK_START = time(9, 0)
WORK_END = time(18, 0)


def _time_to_hours(t: time) -> float:
    """Convert a time object to hours since midnight."""
    return t.hour + t.minute / 60.0 + t.second / 3600.0


def _get_hours_in_period(start_t: time, end_t: time, period_start: time, period_end: time) -> float:
    """
    Calculate hours overlap between a time range and a work period.
    
    Args:
        start_t: Start time of the range
        end_t: End time of the range
        period_start: Start of work period
        period_end: End of work period
    
    Returns:
        Hours of overlap (can be 0)
    """
    # Convert to hours for easier math
    start_h = _time_to_hours(start_t)
    end_h = _time_to_hours(end_t)
    period_start_h = _time_to_hours(period_start)
    period_end_h = _time_to_hours(period_end)
    
    # Find overlap
    overlap_start = max(start_h, period_start_h)
    overlap_end = min(end_h, period_end_h)
    
    if overlap_end > overlap_start:
        return overlap_end - overlap_start
    return 0.0


def get_working_hours_in_range(start_t: time, end_t: time) -> float:
    """
    Calculate working hours in a given time range within a single day.
    Only counts hours within the defined work periods.
    
    Args:
        start_t: Start time
        end_t: End time
    
    Returns:
        Working hours in the range
    """
    total = 0.0
    for period_start, period_end in WORK_PERIODS:
        total += _get_hours_in_period(start_t, end_t, period_start, period_end)
    return total


def get_working_hours_from_time(start_t: time) -> float:
    """
    Calculate remaining working hours in a day from a given start time.
    """
    return get_working_hours_in_range(start_t, WORK_END)


def get_working_hours_until_time(end_t: time) -> float:
    """
    Calculate working hours in a day until a given end time.
    """
    return get_working_hours_in_range(WORK_START, end_t)


def calculate_working_hours(
    start_dt: datetime,
    end_dt: datetime
) -> float:
    """
    Calculate total working hours between two datetimes.
    
    Rules:
    - Only counts Monday-Friday (excludes weekends)
    - Excludes Italian national holidays
    - Only counts 9:00-13:00 and 14:00-18:00 (excludes lunch break)
    
    Args:
        start_dt: Start datetime
        end_dt: End datetime
    
    Returns:
        Total working hours (float)
    """
    if not start_dt or not end_dt:
        return 0.0
    
    # Ensure start is before end
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    
    total_hours = 0.0
    current_date = start_dt.date()
    end_date = end_dt.date()
    
    while current_date <= end_date:
        if is_working_day(current_date):
            if current_date == start_dt.date() == end_dt.date():
                # Same day: partial hours from start to end
                start_time = start_dt.time()
                end_time = end_dt.time()
                
                # Clamp times to working hours
                if start_time < WORK_START:
                    start_time = WORK_START
                if end_time > WORK_END:
                    end_time = WORK_END
                
                if start_time < end_time:
                    total_hours += get_working_hours_in_range(start_time, end_time)
                    
            elif current_date == start_dt.date():
                # First day: from start_time to end of work day
                start_time = start_dt.time()
                if start_time < WORK_START:
                    start_time = WORK_START
                if start_time < WORK_END:
                    total_hours += get_working_hours_from_time(start_time)
                    
            elif current_date == end_dt.date():
                # Last day: from start of work day to end_time
                end_time = end_dt.time()
                if end_time > WORK_END:
                    end_time = WORK_END
                if end_time > WORK_START:
                    total_hours += get_working_hours_until_time(end_time)
                    
            else:
                # Full working day
                total_hours += HOURS_PER_DAY
        
        current_date += timedelta(days=1)
    
    return total_hours


def calculate_working_hours_to_date(
    start_dt: datetime,
    end_date: date
) -> float:
    """
    Calculate working hours from a start datetime to the end of a specific date.
    
    Args:
        start_dt: Start datetime
        end_date: End date (counts until 18:00 of this date)
    
    Returns:
        Total working hours
    """
    # End at 18:00 (end of work day) on the end_date
    end_dt = datetime.combine(end_date, WORK_END)
    return calculate_working_hours(start_dt, end_dt)


def working_hours_to_days(hours: float) -> float:
    """
    Convert working hours to working days.
    
    Args:
        hours: Working hours
    
    Returns:
        Working days (can be fractional)
    """
    return hours / HOURS_PER_DAY if HOURS_PER_DAY > 0 else 0.0


# Test function
if __name__ == "__main__":
    # Test case: Oct 16, 2025 (Thursday) to Nov 15, 2025 (Saturday)
    start = datetime(2025, 10, 16, 10, 0)  # 10 AM
    end = datetime(2025, 11, 15, 14, 0)    # 2 PM
    
    hours = calculate_working_hours(start, end)
    days = working_hours_to_days(hours)
    
    print(f"Start: {start}")
    print(f"End: {end}")
    print(f"Working hours: {hours:.2f}")
    print(f"Working days: {days:.2f}")
