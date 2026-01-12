"""
Data Transformation Layer for converting Jira API responses to pandas DataFrames.
Handles field mapping, type conversion, and computed fields.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from dateutil import parser as date_parser

# English month abbreviations (BEAD 2 standardization - uppercase)
ENGLISH_MONTHS = {
    1: 'JAN', 2: 'FEB', 3: 'MAR', 4: 'APR', 5: 'MAY', 6: 'JUN',
    7: 'JUL', 8: 'AUG', 9: 'SEP', 10: 'OCT', 11: 'NOV', 12: 'DEC'
}

# System priority for resolving multiple systems
SYSTEM_PRIORITY = ['AF', 'ECD', 'SAP', 'MyGate', 'auth0', 'CRM', 'website', 'documents']


def load_field_mappings() -> dict:
    """Load field mappings from configuration file."""
    mapping_path = Path(__file__).parent.parent / "mappings" / "field_mappings.json"
    with open(mapping_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_option_value(field_data: Optional[dict]) -> Optional[str]:
    """Extract the value from a Jira option field."""
    if not field_data:
        return None
    if isinstance(field_data, dict):
        return field_data.get("value") or field_data.get("name")
    return str(field_data)


def extract_option_list(field_data: Optional[list]) -> str:
    """Extract values from a list of Jira option objects and join with semicolons."""
    if not field_data:
        return ""
    if isinstance(field_data, list):
        values = []
        for item in field_data:
            if isinstance(item, dict):
                value = item.get("value") or item.get("name")
                if value:
                    values.append(value)
        return "; ".join(values) if values else ""
    # If it's a single dict, extract the value
    if isinstance(field_data, dict):
        return field_data.get("value") or field_data.get("name") or ""
    return str(field_data)


def extract_labels(labels: Optional[list]) -> str:
    """Convert labels list to semicolon-separated string."""
    if not labels:
        return ""
    return "; ".join(labels)


def extract_linked_issues(issuelinks: Optional[list]) -> str:
    """Extract linked issue keys from issue links."""
    if not issuelinks:
        return ""
    
    linked = []
    for link in issuelinks:
        # Check for outward and inward links
        if "outwardIssue" in link:
            linked.append(link["outwardIssue"]["key"])
        if "inwardIssue" in link:
            linked.append(link["inwardIssue"]["key"])
    
    return "; ".join(sorted(set(linked)))


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse a datetime string from Jira."""
    if not value:
        return None
    try:
        return date_parser.parse(value)
    except (ValueError, TypeError):
        return None


def parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse a date string from Jira (date only, no time)."""
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    except (ValueError, TypeError):
        return None


def get_primary_system(labels: list[str]) -> str:
    """
    Determine the primary system from labels using priority rules.
    If GatePortal is present with another system, prefer the secondary system.
    """
    if not labels:
        return "Other"
    
    # Find systems in labels
    found_systems = []
    for label in labels:
        if label in SYSTEM_PRIORITY:
            found_systems.append(label)
        elif label == "GatePortal":
            found_systems.append(label)
    
    if not found_systems:
        return "Other"
    
    # If GatePortal is present with another system, remove it
    if "GatePortal" in found_systems and len(found_systems) > 1:
        found_systems.remove("GatePortal")
    
    # Return highest priority system
    for system in SYSTEM_PRIORITY:
        if system in found_systems:
            return system
    
    # If only GatePortal remains
    if "GatePortal" in found_systems:
        return "GatePortal"
    
    return "Other"


def compute_total_days(
    status: str,
    resolution_date: Optional[datetime],
    incident_datetime: Optional[datetime]
) -> Optional[int]:
    """
    Calculate the total days from incident detection to resolution.
    Only calculated for closed issues with both dates.
    """
    if not status or status.lower() != "closed":
        return None
    if not resolution_date or not incident_datetime:
        return None
    
    try:
        delta = resolution_date.date() - incident_datetime.date()
        return delta.days
    except (AttributeError, TypeError):
        return None


def compute_quarter(dt: Optional[datetime]) -> Optional[str]:
    """Calculate the quarter from a datetime (Q1, Q2, Q3, Q4)."""
    if not dt:
        return None
    quarter_num = (dt.month - 1) // 3 + 1
    return f"Q{quarter_num}"


def compute_month(dt: Optional[datetime]) -> Optional[str]:
    """Get English month abbreviation (uppercase) from datetime."""
    if not dt:
        return None
    return ENGLISH_MONTHS.get(dt.month)


class DataTransformer:
    """Transforms Jira API responses into structured DataFrames."""
    
    def __init__(self):
        self.field_mappings = load_field_mappings()
        self.custom_fields = self.field_mappings.get("custom_fields", {})
    
    def _get_custom_field_value(self, fields: dict, field_key: str) -> Optional[any]:
        """Get a custom field value by its key name."""
        field_info = self.custom_fields.get(field_key)
        if not field_info:
            return None
        
        field_id = field_info.get("id")
        if not field_id:
            return None
        
        return fields.get(field_id)
    
    def transform_issue(self, issue: dict) -> dict:
        """Transform a single Jira issue into a flat dict for DataFrame."""
        fields = issue.get("fields", {})
        
        # Standard fields
        key = issue.get("key", "")
        summary = fields.get("summary", "")
        status_obj = fields.get("status", {})
        status = status_obj.get("name", "") if status_obj else ""
        labels = fields.get("labels", [])
        
        # Issue type - needed to filter out Task-converted incidents
        issuetype_obj = fields.get("issuetype", {})
        issuetype = issuetype_obj.get("name", "") if issuetype_obj else ""
        
        # Custom fields
        incident_datetime_raw = self._get_custom_field_value(fields, "incident_detection_datetime")
        incident_date_raw = self._get_custom_field_value(fields, "incident_detection_date")
        severity_raw = self._get_custom_field_value(fields, "severity")
        severity_alt_raw = self._get_custom_field_value(fields, "severity_alt")
        root_cause_raw = self._get_custom_field_value(fields, "root_cause")
        phase_raw = self._get_custom_field_value(fields, "phase")
        system_raw = self._get_custom_field_value(fields, "systems_impacted")
        external_system_raw = self._get_custom_field_value(fields, "external_system")
        
        # Resolution date: prioritize custom Resolution datetime (customfield_10687)
        # then fallback to Resolution date (customfield_10495), then standard resolutiondate
        resolution_datetime_raw = self._get_custom_field_value(fields, "resolution_datetime")
        resolution_date_raw = resolution_datetime_raw
        if not resolution_date_raw:
            resolution_date_raw = self._get_custom_field_value(fields, "resolution_date_custom")
        if not resolution_date_raw:
            resolution_date_raw = fields.get("resolutiondate")
        
        # Parse dates
        incident_datetime = parse_datetime(incident_datetime_raw)
        if not incident_datetime and incident_date_raw:
            incident_datetime = parse_date(incident_date_raw)
        
        # Try parsing as datetime first, then as date
        resolution_date = parse_datetime(resolution_date_raw) or parse_date(resolution_date_raw)
        
        # Extract option values
        severity = extract_option_value(severity_raw) or extract_option_value(severity_alt_raw)
        root_cause = extract_option_value(root_cause_raw)
        phase = extract_option_value(phase_raw)
        system_from_field = extract_option_value(system_raw)
        external_system = extract_option_list(external_system_raw)  # Can be a list of options
        
        # Build result
        result = {
            "Key": key,
            "Summary": summary,
            "Severity": severity,
            "Status": status,
            "Labels": extract_labels(labels),
            "Incident detection datetime": incident_datetime,
            "Linked Issues": extract_linked_issues(fields.get("issuelinks", [])),
            "Resolution date": resolution_date,
            "Root Cause": root_cause,
            "Phase": phase,
            "System": system_from_field or get_primary_system(labels),
            "External System": external_system,  # For third-party filtering
            
            # Computed fields
            "Total Days": compute_total_days(status, resolution_date, incident_datetime),
            "Year": incident_datetime.year if incident_datetime else None,
            "Quarter": compute_quarter(incident_datetime),
            "Month": compute_month(incident_datetime),
            
            # Keep raw labels for filtering
            "_labels_list": labels,
            # Issue Type for filtering Task-converted incidents
            "_issue_type": issuetype,
        }
        
        return result
    
    def transform_issues(self, issues: list[dict]) -> pd.DataFrame:
        """
        Transform a list of Jira issues into a pandas DataFrame.
        
        Args:
            issues: List of issue dicts from Jira API
            
        Returns:
            DataFrame with transformed and computed fields
        """
        if not issues:
            return pd.DataFrame()
        
        transformed = [self.transform_issue(issue) for issue in issues]
        df = pd.DataFrame(transformed)
        
        # Ensure proper data types
        # Handle timezone-aware datetimes by converting to UTC
        if "Incident detection datetime" in df.columns:
            df["Incident detection datetime"] = pd.to_datetime(
                df["Incident detection datetime"], utc=True
            ).dt.tz_localize(None)
        if "Resolution date" in df.columns:
            df["Resolution date"] = pd.to_datetime(
                df["Resolution date"], utc=True
            ).dt.tz_localize(None)
        if "Total Days" in df.columns:
            df["Total Days"] = pd.to_numeric(df["Total Days"], errors="coerce").astype("Int64")
        if "Year" in df.columns:
            df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")
        
        return df
    
    def get_report_columns(self) -> list[str]:
        """Get the list of columns for the main report (excluding internal columns)."""
        return [
            "Issue Type",  # Added as first column
            "Key",
            "Summary", 
            "Severity",
            "Status",
            "Labels",
            "Incident detection datetime",
            "Linked Issues",
            "Resolution date",
            "Total Days",
            "Phase",
            "Root Cause",
        ]


def test_transformation():
    """Test the transformation with sample data."""
    # Load sample data if available
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
    
    transformer = DataTransformer()
    df = transformer.transform_issues(issues)
    
    print(f"\n{'='*60}")
    print("DATA TRANSFORMATION TEST")
    print(f"{'='*60}")
    print(f"\nTransformed {len(df)} issues")
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nFirst 5 rows preview:")
    print(df[transformer.get_report_columns()].head().to_string())
    
    # Show some statistics
    print(f"\n{'='*60}")
    print("STATISTICS")
    print(f"{'='*60}")
    print(f"Status distribution:\n{df['Status'].value_counts()}")
    print(f"\nSeverity distribution:\n{df['Severity'].value_counts()}")
    
    if df["Total Days"].notna().any():
        print(f"\nTotal Days stats (closed issues):")
        print(f"  Mean: {df['Total Days'].mean():.1f} days")
        print(f"  Median: {df['Total Days'].median():.1f} days")
        print(f"  Max: {df['Total Days'].max()} days")


if __name__ == "__main__":
    test_transformation()
