"""
Aggregation Engine for generating pivot tables and summary statistics.
Provides grouped counts, averages, and cross-tabulations for the Excel report.
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict

import pandas as pd
import numpy as np

from .business_hours import calculate_working_hours, calculate_working_hours_to_date, working_hours_to_days


# Define severity order for consistent output
SEVERITY_ORDER = ["Blocker", "Severe", "Medium", "Low"]

# Define phases for journey analysis
JOURNEY_PHASES = [
    "myGATE",
    "website", 
    "Contract management",
    "Accounting",
    "Billing and invoicing",
    "Vehicle delivery",
    "Credit KYC",
    "Onboarding",
    "Quotation - SIS",
    "Quotation - dealer"
]

# Root cause categories
ROOT_CAUSES = [
    "Analysis error",
    "Requirement error",
    "Business operation error",
    "Software error",
    "Third party system error",
    "Non-standard process",
    "Infrastructure downtime",
    "Testing error"
]

# System/Application categories (order defines priority - first = highest priority)
# NOTE: These values must match EXACTLY what comes from Jira customfield_10685
SYSTEMS = [
    "Gate Portal",
    "AF",
    "ECD",
    "SAP",
    "myGATE",
    "auth0",
    "Third party (Iveco)",
    "Third party (Other)",
    "CRM",
    "Website",
    "documents"
]

# Create priority lookup for fast access
SYSTEM_PRIORITY = {system: idx for idx, system in enumerate(SYSTEMS)}

# Month order for English uppercase abbreviations (BEAD 2 standardization)
MONTH_ORDER = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

# English month name to number mapping (BEAD 2)
MONTH_TO_NUM = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}


def sort_year_month_columns(columns: list) -> list:
    """Sort columns in format 'MMM-YYYY' chronologically.
    
    Args:
        columns: List of column names in 'MMM-YYYY' format (e.g., ['JAN-2026', 'DEC-2025'])
        
    Returns:
        List sorted chronologically (earliest date first)
    """
    def parse_year_month(col: str) -> tuple:
        if not isinstance(col, str) or '-' not in col:
            return (9999, 99)  # Unknown format goes last
        parts = col.split('-')
        if len(parts) == 2:
            month_num = MONTH_TO_NUM.get(parts[0], 0)
            try:
                year = int(parts[1])
            except ValueError:
                year = 9999
            return (year, month_num)
        return (9999, 99)
    
    return sorted(columns, key=parse_year_month)


def sort_year_quarter_columns(columns: list) -> list:
    """Sort columns in format 'Qn-YYYY' chronologically.
    
    Args:
        columns: List of column names in 'Qn-YYYY' format (e.g., ['Q1-2026', 'Q4-2025'])
        
    Returns:
        List sorted chronologically (earliest quarter first)
    """
    def parse_year_quarter(col: str) -> tuple:
        if not isinstance(col, str) or '-' not in col:
            return (9999, 99)  # Unknown format goes last
        parts = col.split('-')
        if len(parts) == 2 and parts[0].startswith('Q'):
            try:
                quarter_num = int(parts[0][1:])
                year = int(parts[1])
                return (year, quarter_num)
            except ValueError:
                return (9999, 99)
        return (9999, 99)
    
    return sorted(columns, key=parse_year_quarter)

def get_priority_system(systems_str: str) -> Optional[str]:
    """
    Get the highest priority system from a semicolon-separated string of systems.

    Priority is determined by the order in SYSTEMS list (first = highest priority).
    If a ticket has multiple systems (e.g., "AF; ECD"), returns the one with highest priority.

    Args:
        systems_str: Semicolon-separated string of system names (from customfield_10685)

    Returns:
        The highest priority system name, or None if no valid system found
    """
    if not systems_str or pd.isna(systems_str):
        return None

    # Split by semicolon and clean up
    systems = [s.strip() for s in str(systems_str).split(";") if s.strip()]

    if not systems:
        return None

    # Find the system with lowest priority index (= highest priority)
    best_system = None
    best_priority = float('inf')

    for system in systems:
        if system in SYSTEM_PRIORITY:
            priority = SYSTEM_PRIORITY[system]
            if priority < best_priority:
                best_priority = priority
                best_system = system

    return best_system


def is_external_system(value: str) -> bool:
    """
    Check if a system value indicates an external/third-party system.
    
    External systems are identified by values starting with 'Third Party'.
    Internal systems (SAP, auth0, ECD) should NOT be excluded.
    
    Args:
        value: The External System field value
        
    Returns:
        True if this is an external system that should be excluded
    """
    if not value or pd.isna(value):
        return False
    value_str = str(value).strip()
    # Values to exclude: anything starting with "Third Party"
    return value_str.startswith("Third Party")


def is_rejected(status: str) -> bool:
    """
    Check if a status indicates a Rejected issue.
    
    Args:
        status: The Status field value
        
    Returns:
        True if the issue is Rejected
    """
    if not status or pd.isna(status):
        return False
    return str(status).strip().lower() == "rejected"


VALID_INCIDENT_TYPES = {"[system] incident", "production incident"}


def is_valid_incident_type(issue_type: str) -> bool:
    """
    Check if an issue type is a valid incident type for aggregation.

    Only [System] Incident and Production Incident types should be
    included in aggregation tables. All other types (e.g. "Ask a question")
    are excluded.

    Args:
        issue_type: The issue type name from Jira

    Returns:
        True if the issue type should be included in aggregations
    """
    if not issue_type or pd.isna(issue_type):
        return False
    return str(issue_type).strip().lower() in VALID_INCIDENT_TYPES


def get_end_of_month(year: int, month: int) -> date:
    """Get the last day of a given month."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return next_month - timedelta(days=1)


def get_months_between(start_dt: datetime, end_dt: datetime) -> List[Dict]:
    """
    Get all months between two datetimes.
    
    Returns list of dicts with:
    - year: int
    - month: int
    - month_name: English month abbreviation (uppercase)
    - end_of_month: date
    """
    if not start_dt or not end_dt:
        return []
    
    months = []
    current = date(start_dt.year, start_dt.month, 1)
    end_date = end_dt.date() if isinstance(end_dt, datetime) else end_dt
    
    while current <= end_date:
        month_name = MONTH_ORDER[current.month - 1]
        months.append({
            'year': current.year,
            'month': current.month,
            'month_name': month_name,
            'end_of_month': get_end_of_month(current.year, current.month)
        })
        
        # Move to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    
    return months


class Aggregator:
    """Generates aggregations and summaries from transformed issue data."""
    
    def __init__(self, df: pd.DataFrame):
        """
        Initialize with a transformed DataFrame.
        
        Args:
            df: DataFrame from DataTransformer.transform_issues()
        """
        self.df = df.copy()
        
        # Ensure categorical ordering for severity
        if "Severity" in self.df.columns:
            self.df["Severity"] = pd.Categorical(
                self.df["Severity"],
                categories=SEVERITY_ORDER,
                ordered=True
            )
    
    def filter_by_status(self, status: str = "Closed") -> pd.DataFrame:
        """Filter DataFrame by status."""
        return self.df[self.df["Status"] == status].copy()
    
    def filter_by_label(self, label: str) -> pd.DataFrame:
        """Filter DataFrame to issues containing a specific label."""
        if "_labels_list" in self.df.columns:
            return self.df[self.df["_labels_list"].apply(lambda x: label in x if x else False)].copy()
        elif "Labels" in self.df.columns:
            return self.df[self.df["Labels"].str.contains(label, case=False, na=False)].copy()
        return self.df.copy()
    
    def exclude_rejected(self, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Filter out issues with Rejected status.

        Args:
            df: DataFrame to filter (default: self.df)

        Returns:
            DataFrame excluding Rejected issues
        """
        data = df if df is not None else self.df
        if "Status" not in data.columns:
            return data.copy()
        # Use vectorized string comparison for better reliability
        # Convert to string, strip whitespace, and compare case-insensitively
        status_normalized = data["Status"].fillna("").astype(str).str.strip().str.lower()
        return data[status_normalized != "rejected"].copy()
    
    def exclude_external_systems(self, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Filter out issues from external/third-party systems.

        Uses the External System field (customfield_10685).
        Excludes issues where the value starts with 'Third Party'.
        SAP, auth0, ECD are internal systems and are NOT excluded.

        Args:
            df: DataFrame to filter (default: self.df)

        Returns:
            DataFrame excluding external system issues
        """
        data = df if df is not None else self.df
        if "External System" not in data.columns:
            return data.copy()
        # Use vectorized string operations for better reliability
        ext_sys_normalized = data["External System"].fillna("").astype(str).str.strip()
        return data[~ext_sys_normalized.str.startswith("Third Party")].copy()
    
    def filter_incidents_only(self, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Filter to only include valid incident types.

        Only [System] Incident and Production Incident types are included.
        All other types (e.g. "Ask a question") are excluded.

        Args:
            df: DataFrame to filter (default: self.df)

        Returns:
            DataFrame containing only valid incident types
        """
        data = df if df is not None else self.df
        if "_issue_type" not in data.columns:
            return data.copy()
        # Use vectorized string comparison for reliability
        issue_type_normalized = data["_issue_type"].fillna("").astype(str).str.strip().str.lower()
        return data[issue_type_normalized.isin(VALID_INCIDENT_TYPES)].copy()
    
    def filter_by_severities(
        self, 
        df: Optional[pd.DataFrame] = None, 
        severities: List[str] = None
    ) -> pd.DataFrame:
        """
        Filter to only include specified severities.
        
        Args:
            df: DataFrame to filter (default: self.df)
            severities: List of severities to include (default: Blocker, Severe)
            
        Returns:
            DataFrame with only specified severities
        """
        if severities is None:
            severities = ["Blocker", "Severe"]
        data = df if df is not None else self.df
        if "Severity" not in data.columns:
            return data.copy()
        return data[data["Severity"].isin(severities)].copy()
    
    def filter_by_label_contains(
        self,
        df: Optional[pd.DataFrame] = None,
        label: str = None
    ) -> pd.DataFrame:
        """
        Filter DataFrame to issues containing a specific label.
        
        Args:
            df: DataFrame to filter (default: self.df)
            label: Label to filter by
            
        Returns:
            DataFrame with only issues containing the label
        """
        if label is None:
            return df if df is not None else self.df.copy()
        data = df if df is not None else self.df
        if "_labels_list" in data.columns:
            return data[data["_labels_list"].apply(lambda x: label in x if x else False)].copy()
        elif "Labels" in data.columns:
            return data[data["Labels"].str.contains(label, case=False, na=False)].copy()
        return data.copy()
    
    def count_by_severity_and_period(
        self,
        df: Optional[pd.DataFrame] = None,
        period: str = "Month"  # Month, Quarter, or Year
    ) -> pd.DataFrame:
        """
        Create a pivot table of issue counts by severity and time period.
        
        Returns DataFrame with periods as rows, severities as columns.
        """
        data = df if df is not None else self.df
        
        if data.empty:
            return pd.DataFrame()
        
        pivot = pd.pivot_table(
            data,
            values="Key",
            index=["Year", "Quarter", period] if period == "Month" else ["Year", period],
            columns="Severity",
            aggfunc="count",
            fill_value=0,
            observed=False
        )
        
        # Ensure all severity columns exist
        for sev in SEVERITY_ORDER:
            if sev not in pivot.columns:
                pivot[sev] = 0
        
        pivot = pivot[SEVERITY_ORDER]
        pivot["Grand Total"] = pivot.sum(axis=1)
        
        return pivot
    
    def avg_resolution_by_severity_and_period(
        self,
        df: Optional[pd.DataFrame] = None,
        period: str = "Month"
    ) -> pd.DataFrame:
        """
        Create a pivot table of average resolution time by severity and period.
        
        Returns DataFrame with periods as rows, severities as columns.
        """
        data = df if df is not None else self.df
        
        # Only include closed issues with Total Days
        data = data[data["Total Days"].notna()].copy()
        
        if data.empty:
            return pd.DataFrame()
        
        pivot = pd.pivot_table(
            data,
            values="Total Days",
            index=["Year", "Quarter", period] if period == "Month" else ["Year", period],
            columns="Severity",
            aggfunc="mean",
            fill_value=np.nan,
            observed=False
        )
        
        # Ensure all severity columns exist
        for sev in SEVERITY_ORDER:
            if sev not in pivot.columns:
                pivot[sev] = np.nan
        
        pivot = pivot[SEVERITY_ORDER]
        
        return pivot
    
    def monthly_severity_counts(self) -> pd.DataFrame:
        """
        Generate monthly severity counts as a simple table.
        Each ticket is counted in every month it was open (detection → resolution).
        Rows: Severity levels
        Columns: YearMonth in format 'MMM-YYYY' (e.g., 'JAN-2025', 'FEB-2026')

        BEAD 1 Filtering applied:
        - Excludes Rejected status
        - Excludes external systems (Third Party)

        Multi-year support: Columns span all years present in the data,
        sorted chronologically.
        """
        if self.df.empty or "YearMonth" not in self.df.columns:
            return pd.DataFrame()

        # Apply filters: exclude Task-type issues, Rejected, and external systems
        data = self.filter_incidents_only()
        data = self.exclude_rejected(data)
        data = self.exclude_external_systems(data)

        if data.empty:
            return pd.DataFrame()

        # Expand each ticket into one row per month it was open
        expanded_rows = []
        for _, row in data.iterrows():
            start_dt = row.get("Incident detection datetime")
            if pd.isna(start_dt):
                continue

            end_dt = row.get("Resolution date")
            if pd.isna(end_dt):
                end_dt = datetime.now()

            months = get_months_between(start_dt, end_dt)
            if not months:
                # Fallback to original YearMonth column
                months = [{"month_name": row["YearMonth"].split("-")[0],
                           "year": int(row["YearMonth"].split("-")[1])}]

            for m in months:
                ym = f"{m['month_name']}-{m['year']}"
                expanded_rows.append({
                    "Key": row["Key"],
                    "Severity": row["Severity"],
                    "YearMonth": ym,
                })

        if not expanded_rows:
            return pd.DataFrame()

        expanded_df = pd.DataFrame(expanded_rows)
        expanded_df["Severity"] = pd.Categorical(
            expanded_df["Severity"], categories=SEVERITY_ORDER
        )

        pivot = pd.pivot_table(
            expanded_df,
            values="Key",
            index="Severity",
            columns="YearMonth",
            aggfunc="count",
            fill_value=0,
            observed=False
        )

        # Sort columns chronologically using year-month sorting
        cols = sort_year_month_columns([c for c in pivot.columns])
        if not cols:
            return pivot

        pivot = pivot[cols]

        # Reorder rows to severity order
        rows = [s for s in SEVERITY_ORDER if s in pivot.index]
        if rows:
            pivot = pivot.reindex(rows)

        return pivot
    
    def phase_severity_counts(
        self,
        severities: list[str] = None
    ) -> pd.DataFrame:
        """
        Count issues by phase (E2E journey phase) and quarter.

        BEAD 1 Filtering applied:
        - Blocker/Severe severity only (default) - both included together
        - Excludes Rejected status

        Rows: E2E journey phases (myGATE, website, etc.)
        Columns: YearQuarter in 'Qn-YYYY' format (e.g., 'Q1-2025', 'Q2-2026')

        Args:
            severities: List of severities to include (default: Blocker, Severe)
        """
        if severities is None:
            severities = ["Blocker", "Severe"]

        # Apply filters: exclude Task-type issues, Rejected, filter to specified severities
        data = self.filter_incidents_only()
        data = self.exclude_rejected(data)
        data = self.filter_by_severities(data, severities)

        if data.empty or "Phase" not in data.columns or "YearQuarter" not in data.columns:
            return pd.DataFrame()

        pivot = pd.pivot_table(
            data,
            values="Key",
            index="Phase",
            columns="YearQuarter",
            aggfunc="count",
            fill_value=0,
            observed=False
        )

        # Sort columns chronologically using year-quarter sorting
        cols = sort_year_quarter_columns([c for c in pivot.columns])
        if cols:
            pivot = pivot[cols]

        return pivot
    
    def quarterly_dealer_journey(
        self,
        severities: list[str] = None,
        system_filter: str = None
    ) -> pd.DataFrame:
        """
        Generate quarterly breakdown of Blocker & Severe issues on Dealer Journey.

        BEAD 1 Filtering applied:
        - ONLY includes issues with DEALER_CRITICAL_PATH label
        - Blocker/Severe severity only (default)
        - Excludes Rejected status

        Multi-year support: Columns are in 'Qn-YYYY' format (e.g., 'Q1-2025', 'Q2-2026'),
        sorted chronologically.

        Args:
            severities: List of severities to include (default: Blocker, Severe)
            system_filter: Optional system filter:
                - "AF": Only include tickets where priority system is AF
                - "non-AF": Only include tickets where priority system is NOT AF
                - None: Include all systems (default)

        Returns DataFrame with severities as rows, year-quarters as columns.
        """
        if severities is None:
            severities = ["Blocker", "Severe"]

        # Apply filters:
        # 1. Exclude Task-type issues
        # 2. Filter by DEALER_CRITICAL_PATH label
        # 3. Exclude Rejected
        # 4. Filter to specified severities
        data = self.filter_incidents_only()
        data = self.filter_by_label_contains(data, "DEALER_CRITICAL_PATH")
        data = self.exclude_rejected(data)
        data = self.filter_by_severities(data, severities)

        if data.empty or "YearQuarter" not in data.columns:
            return pd.DataFrame()

        # Apply system filter if specified
        if system_filter and "External System" in data.columns:
            data = data.copy()
            data["_priority_system"] = data["External System"].apply(get_priority_system)

            if system_filter == "AF":
                data = data[data["_priority_system"] == "AF"]
            elif system_filter == "non-AF":
                data = data[data["_priority_system"] != "AF"]

        if data.empty:
            return pd.DataFrame()

        pivot = pd.pivot_table(
            data,
            values="Key",
            index="Severity",
            columns="YearQuarter",
            aggfunc="count",
            fill_value=0,
            observed=False
        )

        # Sort columns chronologically using year-quarter sorting
        cols = sort_year_quarter_columns([c for c in pivot.columns])
        if cols:
            pivot = pivot[cols]

        # Order rows by severity
        rows = [s for s in severities if s in pivot.index]
        if rows:
            pivot = pivot.reindex(rows)

        return pivot
    
    def avg_resolution_by_month(self) -> pd.DataFrame:
        """
        Calculate average resolution time (Age WH) by month.
        
        Returns DataFrame with single row of averages by month.
        """
        data = self.df[self.df["Total Days"].notna()].copy()
        
        if data.empty:
            return pd.DataFrame()
        
        result = data.groupby("Month")["Total Days"].mean()
        
        # Reorder to month order
        result = result.reindex([m for m in MONTH_ORDER if m in result.index])
        
        return pd.DataFrame([result], index=["Avg Resolution (days)"])
    
    def root_cause_counts(self, severities: list[str] = None) -> pd.DataFrame:
        """
        Count issues by root cause category and quarter.

        BEAD 1 Filtering applied:
        - Blocker/Severe severity only (default)
        - INCLUDES Rejected status (exception - Root Cause Analysis keeps Rejected)

        Rows: Root cause categories
        Columns: YearQuarter in 'Qn-YYYY' format (e.g., 'Q1-2025', 'Q2-2026')

        Args:
            severities: List of severities to include (default: Blocker, Severe)

        Returns DataFrame with root causes as rows, quarters as columns.
        """
        if severities is None:
            severities = ["Blocker", "Severe"]

        # Apply filters: Exclude Task-type, Blocker/Severe only
        # NOTE: Root Cause Analysis is the EXCEPTION - we KEEP Rejected issues
        data = self.filter_incidents_only()
        data = self.filter_by_severities(data, severities)

        if "Root Cause" not in data.columns or "YearQuarter" not in data.columns:
            return pd.DataFrame()

        if data.empty:
            return pd.DataFrame()

        pivot = pd.pivot_table(
            data,
            values="Key",
            index="Root Cause",
            columns="YearQuarter",
            aggfunc="count",
            fill_value=0,
            observed=False
        )

        # Sort columns chronologically using year-quarter sorting
        cols = sort_year_quarter_columns([c for c in pivot.columns])
        if cols:
            pivot = pivot[cols]

        # Reorder rows to standard root cause order
        rows = [rc for rc in ROOT_CAUSES if rc in pivot.index]
        if rows:
            pivot = pivot.reindex(rows)

        # Clear index/columns names to prevent extra row in Excel output
        pivot.index.name = None
        pivot.columns.name = None

        return pivot
    
    def system_counts(self, severities: list[str] = None) -> pd.DataFrame:
        """
        Count issues by system/application and quarter.

        Uses the External System field (customfield_10685) as data source.
        When a ticket has multiple systems, only counts once using priority order.
        Priority follows SYSTEMS list order (GatePortal > AF > ECD > ... > documents).

        BEAD 1 Filtering applied:
        - Blocker/Severe severity only (default)
        - Excludes Rejected status

        Rows: System/Application names
        Columns: YearQuarter in 'Qn-YYYY' format (e.g., 'Q1-2025', 'Q2-2026')

        Args:
            severities: List of severities to include (default: Blocker, Severe)

        Returns DataFrame with systems as rows, quarters as columns.
        """
        if severities is None:
            severities = ["Blocker", "Severe"]

        # Apply filters: Exclude Task-type, Rejected, then Blocker/Severe only
        data = self.filter_incidents_only()
        data = self.exclude_rejected(data)
        data = self.filter_by_severities(data, severities)

        if "External System" not in data.columns or "YearQuarter" not in data.columns:
            return pd.DataFrame()

        if data.empty:
            return pd.DataFrame()

        # Apply priority logic: for each ticket, select highest priority system
        data = data.copy()
        data["_priority_system"] = data["External System"].apply(get_priority_system)

        pivot = pd.pivot_table(
            data,
            values="Key",
            index="_priority_system",
            columns="YearQuarter",
            aggfunc="count",
            fill_value=0,
            observed=False
        )

        # Sort columns chronologically using year-quarter sorting
        cols = sort_year_quarter_columns([c for c in pivot.columns])
        if cols:
            pivot = pivot[cols]

        # Reorder rows to standard system order
        rows = [sys for sys in SYSTEMS if sys in pivot.index]
        if rows:
            pivot = pivot.reindex(rows)

        # Clear index/columns names to prevent extra row in Excel output
        pivot.index.name = None
        pivot.columns.name = None

        return pivot
    
    def generate_pivot_table_a(self, label_filter: str = "AF") -> pd.DataFrame:
        """
        Generate PIVOT Table A: Issue Count by Severity
        Filter: Status=Closed, Labels contains specified label
        """
        data = self.filter_by_status("Closed")
        data = data[data["_labels_list"].apply(lambda x: label_filter in x if x else False)]
        
        return self.count_by_severity_and_period(data, "Month")
    
    def generate_pivot_table_b(self, label_filter: str = "AF") -> pd.DataFrame:
        """
        Generate PIVOT Table B: Average Resolution Time
        Same filters as Table A, but with averages.
        """
        data = self.filter_by_status("Closed")
        data = data[data["_labels_list"].apply(lambda x: label_filter in x if x else False)]
        
        return self.avg_resolution_by_severity_and_period(data, "Month")
    
    def avg_working_hours_by_month_cross(self, severities: list[str] = None) -> pd.DataFrame:
        """
        Calculate average working HOURS by month with cross-month logic.

        A ticket spanning Oct-Nov contributes:
        - To October: working hours from incident → Oct 31 (cumulative to end of Oct)
        - To November: working hours from incident → resolution (FULL duration)

        This means:
        - Each month gets the cumulative working hours up to that month's end
        - The resolution month gets the full working hours duration

        BEAD 1 Filtering applied:
        - Status: Closed, Workaround Applied, or Resolved (with resolution date)
        - Blocker/Severe severity only (default)
        - Excludes Rejected status
        - Excludes external systems (Third Party)

        Args:
            severities: List of severities to include (default: Blocker, Severe)

        Returns DataFrame with single row of average working hours by year-month.
        Columns are in format 'MMM-YYYY' (e.g., 'JAN-2025', 'FEB-2026').
        """
        if severities is None:
            severities = ["Blocker", "Severe"]

        # Apply filters:
        # 1. Exclude Task-type issues
        # 2. Exclude Rejected status
        # 3. Exclude external systems (Third Party)
        # 4. Filter to resolved/closed tickets with specified severities
        data = self.filter_incidents_only()
        data = self.exclude_rejected(data)
        data = self.exclude_external_systems(data)

        # Statuses that indicate a ticket has been resolved (has a resolution date)
        resolved_statuses = ["Closed", "Workaround Applied", "Resolved"]
        
        # Filter to resolved/closed tickets with specified severities
        resolved_tickets = data[
            (data["Status"].isin(resolved_statuses)) &
            (data["Severity"].isin(severities))
        ].copy()

        if resolved_tickets.empty:
            return pd.DataFrame()

        # Build monthly contributions using year-month keys (MMM-YYYY format)
        monthly_hours: Dict[str, List[float]] = {}

        for _, ticket in resolved_tickets.iterrows():
            incident_dt = ticket.get("Incident detection datetime")
            resolution_dt = ticket.get("Resolution date")

            if pd.isna(incident_dt) or pd.isna(resolution_dt):
                continue

            # Ensure datetime types
            if not isinstance(incident_dt, datetime):
                continue
            if not isinstance(resolution_dt, datetime):
                # Try to convert date to datetime
                if isinstance(resolution_dt, date):
                    resolution_dt = datetime.combine(resolution_dt, datetime.min.time().replace(hour=18))
                else:
                    continue

            # Get all months this ticket spans
            months_spanned = get_months_between(incident_dt, resolution_dt)

            for month_info in months_spanned:
                # Build year-month key in MMM-YYYY format
                year_month_key = f"{month_info['month_name']}-{month_info['year']}"
                end_of_month = month_info["end_of_month"]

                # Calculate working hours from incident to min(end_of_month, resolution)
                # For the resolution month, use resolution_dt
                # For other months, use end of that month
                if resolution_dt.date() <= end_of_month:
                    # This is the resolution month - use full duration
                    hours = calculate_working_hours(incident_dt, resolution_dt)
                else:
                    # Not resolution month - use hours up to end of this month
                    hours = calculate_working_hours_to_date(incident_dt, end_of_month)

                if hours > 0:
                    if year_month_key not in monthly_hours:
                        monthly_hours[year_month_key] = []
                    monthly_hours[year_month_key].append(hours)

        # Calculate averages
        result = {}
        for year_month_key, hours_list in monthly_hours.items():
            if hours_list:
                result[year_month_key] = sum(hours_list) / len(hours_list)

        if not result:
            return pd.DataFrame()

        # Create DataFrame with year-month columns
        df_result = pd.DataFrame([result], index=["Avg WH"])

        # Sort columns chronologically using year-month sorting
        cols = sort_year_month_columns([c for c in df_result.columns])
        return df_result[cols]
    
    def avg_working_days_by_month_cross(self, severities: list[str] = None) -> pd.DataFrame:
        """
        Calculate average working DAYS by month with cross-month logic.

        This is derived from avg_working_hours_by_month_cross() by dividing by 8.
        
        Columns are in format 'MMM-YYYY' (e.g., 'JAN-2025', 'FEB-2026').

        Args:
            severities: List of severities to include (default: Blocker, Severe)

        Returns DataFrame with single row of average working days by year-month.
        """
        hours_df = self.avg_working_hours_by_month_cross(severities=severities)
        
        if hours_df.empty:
            return pd.DataFrame()
        
        # Convert hours to days (8 hours per day)
        days_df = hours_df.apply(working_hours_to_days)
        days_df.index = ["Avg WD"]

        return days_df

    def monthly_blocker_closures(self) -> pd.DataFrame:
        """
        Count Blocker tickets closed by month and their average working hours.

        Groups by RESOLUTION month (not incident month).

        Filtering applied:
        - Severity = Blocker only
        - Status = Closed, Workaround Applied, or Resolved
        - Excludes System = AF
        - Excludes Root Cause = "Non-standard process"
        - Excludes Task-type issues

        Returns DataFrame with two rows:
        - "Count": Number of Blockers closed in that month
        - "Avg WH": Average working hours for those Blockers

        Columns are in format 'MMM-YYYY' (e.g., 'JAN-2025', 'FEB-2026').
        """
        # Apply filters:
        # 1. Exclude Task-type issues
        data = self.filter_incidents_only()

        # 2. Filter to Blocker severity only
        data = self.filter_by_severities(data, ["Blocker"])

        # 3. Filter to resolved/closed statuses
        resolved_statuses = ["Closed", "Workaround Applied", "Resolved"]
        data = data[data["Status"].isin(resolved_statuses)].copy()

        if data.empty:
            return pd.DataFrame()

        # 4. Exclude AF system (using priority system logic)
        if "External System" in data.columns:
            data["_priority_system"] = data["External System"].apply(get_priority_system)
            data = data[data["_priority_system"] != "AF"]

        # 5. Exclude "Non-standard process" root cause
        if "Root Cause" in data.columns:
            data = data[data["Root Cause"] != "Non-standard process"]

        if data.empty:
            return pd.DataFrame()

        # Group by resolution month (not incident month)
        monthly_count: Dict[str, int] = {}
        monthly_hours: Dict[str, List[float]] = {}

        for _, ticket in data.iterrows():
            incident_dt = ticket.get("Incident detection datetime")
            resolution_dt = ticket.get("Resolution date")

            if pd.isna(resolution_dt):
                continue

            # Ensure datetime types
            if not isinstance(resolution_dt, datetime):
                if isinstance(resolution_dt, date):
                    resolution_dt = datetime.combine(resolution_dt, datetime.min.time().replace(hour=18))
                else:
                    continue

            # Get resolution month in MMM-YYYY format
            resolution_month = resolution_dt.month
            resolution_year = resolution_dt.year
            month_name = MONTH_ORDER[resolution_month - 1]
            year_month_key = f"{month_name}-{resolution_year}"

            # Count the ticket
            monthly_count[year_month_key] = monthly_count.get(year_month_key, 0) + 1

            # Calculate working hours if we have incident datetime
            if not pd.isna(incident_dt) and isinstance(incident_dt, datetime):
                hours = calculate_working_hours(incident_dt, resolution_dt)
                if hours > 0:
                    if year_month_key not in monthly_hours:
                        monthly_hours[year_month_key] = []
                    monthly_hours[year_month_key].append(hours)

        if not monthly_count:
            return pd.DataFrame()

        # Build result with all months that have data
        all_months = sorted(set(monthly_count.keys()) | set(monthly_hours.keys()),
                           key=lambda x: (int(x.split('-')[1]), MONTH_TO_NUM.get(x.split('-')[0], 0)))

        count_row = {}
        avg_wh_row = {}

        for month_key in all_months:
            count_row[month_key] = monthly_count.get(month_key, 0)
            hours_list = monthly_hours.get(month_key, [])
            if hours_list:
                avg_wh_row[month_key] = sum(hours_list) / len(hours_list)
            else:
                avg_wh_row[month_key] = 0

        # Create DataFrame
        df_result = pd.DataFrame([count_row, avg_wh_row], index=["Count", "Avg WH"])

        # Sort columns chronologically
        cols = sort_year_month_columns([c for c in df_result.columns])
        return df_result[cols]


def test_aggregations():
    """Test aggregations with sample data."""
    import json
    from pathlib import Path
    from .data_transformer import DataTransformer
    
    sample_path = Path(__file__).parent.parent / "pi-filter-output.json"
    
    if not sample_path.exists():
        print("Sample data file not found")
        return
    
    with open(sample_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    issues = data.get("issues", [])
    if not issues:
        print("No issues in sample data")
        return
    
    # Transform data
    transformer = DataTransformer()
    df = transformer.transform_issues(issues)
    
    # Create aggregator
    agg = Aggregator(df)
    
    print(f"\n{'='*60}")
    print("AGGREGATION TEST")
    print(f"{'='*60}")
    
    print("\n1. Monthly Severity Counts:")
    print(agg.monthly_severity_counts())
    
    print("\n2. Quarterly Dealer Journey (Blocker & Severe):")
    print(agg.quarterly_dealer_journey())
    
    print("\n3. Average Resolution by Month:")
    print(agg.avg_resolution_by_month())
    
    print("\n4. Root Cause Counts:")
    print(agg.root_cause_counts())
    
    print("\n5. System Counts:")
    print(agg.system_counts())


if __name__ == "__main__":
    test_aggregations()
