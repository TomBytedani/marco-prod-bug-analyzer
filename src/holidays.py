"""
Italian Holiday Calendar wrapper.
Uses workalendar for accurate Italian national holiday detection.
"""

from datetime import date
from functools import lru_cache
from typing import Set

try:
    from workalendar.europe import Italy
    WORKALENDAR_AVAILABLE = True
except ImportError:
    WORKALENDAR_AVAILABLE = False


# Fallback: Known Italian national holidays (fixed dates)
# Variable holidays (Easter, etc.) will only work with workalendar installed
FIXED_ITALIAN_HOLIDAYS = {
    (1, 1),    # Capodanno
    (1, 6),    # Epifania
    (4, 25),   # Festa della Liberazione
    (5, 1),    # Festa dei Lavoratori
    (6, 2),    # Festa della Repubblica
    (8, 15),   # Ferragosto
    (11, 1),   # Tutti i Santi
    (12, 8),   # Immacolata Concezione
    (12, 25),  # Natale
    (12, 26),  # Santo Stefano
}


class ItalianHolidayCalendar:
    """
    Italian holiday calendar.
    Uses workalendar if available, otherwise falls back to fixed holidays.
    """
    
    def __init__(self):
        if WORKALENDAR_AVAILABLE:
            self._calendar = Italy()
        else:
            self._calendar = None
    
    @lru_cache(maxsize=10)
    def get_holidays_for_year(self, year: int) -> Set[date]:
        """Get all holidays for a given year."""
        if self._calendar:
            # workalendar returns list of (date, name) tuples
            return {h[0] for h in self._calendar.holidays(year)}
        else:
            # Fallback: only fixed holidays (no Easter, etc.)
            return {date(year, month, day) for (month, day) in FIXED_ITALIAN_HOLIDAYS}
    
    def is_holiday(self, d: date) -> bool:
        """Check if a date is an Italian national holiday."""
        holidays = self.get_holidays_for_year(d.year)
        return d in holidays
    
    def is_working_day(self, d: date) -> bool:
        """
        Check if a date is a working day.
        A working day is Monday-Friday and not a holiday.
        """
        # Check if weekend (Saturday=5, Sunday=6)
        if d.weekday() >= 5:
            return False
        
        # Check if holiday
        if self.is_holiday(d):
            return False
        
        return True


# Singleton instance
_calendar = None

def get_italian_calendar() -> ItalianHolidayCalendar:
    """Get the singleton Italian calendar instance."""
    global _calendar
    if _calendar is None:
        _calendar = ItalianHolidayCalendar()
    return _calendar


def is_working_day(d: date) -> bool:
    """Convenience function to check if a date is a working day."""
    return get_italian_calendar().is_working_day(d)


def is_holiday(d: date) -> bool:
    """Convenience function to check if a date is a holiday."""
    return get_italian_calendar().is_holiday(d)
