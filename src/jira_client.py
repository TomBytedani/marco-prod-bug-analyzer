"""
Jira REST API Client for fetching issues and field metadata.
Handles authentication, pagination, and rate limiting.
"""

import json
import time
import logging
from typing import Optional, Generator
from pathlib import Path

import requests

from .config import get_config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class JiraAPIError(Exception):
    """Raised when Jira API returns an error."""
    pass


class JiraClient:
    """Client for interacting with Jira Cloud REST API."""
    
    def __init__(self):
        self.config = get_config()
        self.session = requests.Session()
        self.session.auth = self.config.jira_auth
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        
        # Rate limiting settings
        self.max_retries = 3
        self.base_delay = 1.0  # seconds
    
    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an API request with retry logic for rate limiting."""
        url = f"{self.config.jira_base_url}/{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(method, url, **kwargs)
                
                if response.status_code == 429:
                    # Rate limited - exponential backoff
                    retry_after = int(response.headers.get("Retry-After", self.base_delay * (2 ** attempt)))
                    logger.warning(f"Rate limited. Waiting {retry_after}s before retry...")
                    time.sleep(retry_after)
                    continue
                
                if response.status_code == 401:
                    raise JiraAPIError("Authentication failed. Check your credentials.")
                
                if response.status_code == 403:
                    raise JiraAPIError("Access forbidden. Check your permissions.")
                
                if response.status_code >= 400:
                    error_msg = response.text[:500]
                    raise JiraAPIError(f"API error {response.status_code}: {error_msg}")
                
                return response.json()
            
            except requests.RequestException as e:
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(f"Request failed: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    raise JiraAPIError(f"Request failed after {self.max_retries} attempts: {e}")
        
        raise JiraAPIError("Max retries exceeded")
    
    def get_fields(self) -> list[dict]:
        """
        Fetch all field definitions from Jira.
        Returns list of field metadata including custom field IDs.
        """
        logger.info("Fetching Jira field definitions...")
        return self._request("GET", "field")
    
    def discover_custom_fields(self, save_to_file: Optional[Path] = None) -> dict:
        """
        Discover and return custom field IDs for required fields.
        Optionally saves the discovery results to a JSON file.
        """
        fields = self.get_fields()
        
        # Fields we're looking for (case-insensitive partial match)
        target_fields = {
            "severity": None,
            "root cause": None,
            "incident detection": None,
            "system": None,
            "application": None,
            "phase": None,
        }
        
        discovered = {}
        all_custom_fields = []
        
        for field in fields:
            field_id = field.get("id", "")
            field_name = field.get("name", "")
            field_type = field.get("schema", {}).get("type", "unknown") if field.get("schema") else "unknown"
            is_custom = field_id.startswith("customfield_")
            
            if is_custom:
                all_custom_fields.append({
                    "id": field_id,
                    "name": field_name,
                    "type": field_type,
                    "searchable": field.get("searchable", False),
                    "clauseNames": field.get("clauseNames", [])
                })
            
            # Check if this matches any of our target fields
            name_lower = field_name.lower()
            for target, _ in target_fields.items():
                if target in name_lower:
                    discovered[target] = {
                        "id": field_id,
                        "name": field_name,
                        "type": field_type
                    }
        
        result = {
            "discovered_fields": discovered,
            "all_custom_fields": all_custom_fields
        }
        
        if save_to_file:
            save_to_file.parent.mkdir(parents=True, exist_ok=True)
            with open(save_to_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            logger.info(f"Field discovery saved to {save_to_file}")
        
        return result
    
    def search_issues(
        self,
        jql: Optional[str] = None,
        fields: Optional[list[str]] = None,
        max_results: int = 100
    ) -> Generator[dict, None, None]:
        """
        Search for issues using JQL with automatic pagination.
        Uses the new /search/jql endpoint (per Atlassian CHANGE-2046).
        Uses nextPageToken for pagination.
        Yields individual issues.
        
        Args:
            jql: JQL query string (defaults to config JQL)
            fields: List of field keys to include (defaults to all)
            max_results: Results per page (max 100)
        """
        jql = jql or self.config.jira_jql
        next_page_token = None
        fetched_count = 0
        
        logger.info(f"Searching issues with JQL: {jql[:100]}...")
        
        while True:
            payload = {
                "jql": jql,
                "maxResults": min(max_results, 100)
            }
            
            if next_page_token:
                payload["nextPageToken"] = next_page_token
            
            if fields:
                payload["fields"] = fields
            
            # Use new /search/jql endpoint (deprecated /search returns 410)
            result = self._request("POST", "search/jql", json=payload)
            
            issues = result.get("issues", [])
            next_page_token = result.get("nextPageToken")
            
            fetched_count += len(issues)
            total = result.get("total", fetched_count)
            
            logger.info(f"Fetched {fetched_count}/{total} issues")
            
            for issue in issues:
                yield issue
            
            # Stop if no more pages or no issues returned
            if not next_page_token or not issues:
                break
    
    def get_all_issues(
        self,
        jql: Optional[str] = None,
        fields: Optional[list[str]] = None
    ) -> list[dict]:
        """
        Fetch all issues matching the query.
        Returns a list of all issues.
        """
        return list(self.search_issues(jql, fields))
    
    def get_field_options(self, field_id: str) -> list[dict]:
        """
        Get available options for a select/multiselect custom field.
        Note: This may require different API endpoints based on field type.
        """
        try:
            # Try the contexts approach for custom fields
            if field_id.startswith("customfield_"):
                contexts = self._request("GET", f"field/{field_id}/context")
                options = []
                for ctx in contexts.get("values", []):
                    ctx_id = ctx.get("id")
                    if ctx_id:
                        opts = self._request("GET", f"field/{field_id}/context/{ctx_id}/option")
                        options.extend(opts.get("values", []))
                return options
        except JiraAPIError as e:
            logger.warning(f"Could not fetch options for {field_id}: {e}")
        
        return []


def test_connection():
    """Test the Jira connection and print field discovery results."""
    client = JiraClient()
    
    print("\n" + "=" * 60)
    print("JIRA CONNECTION TEST")
    print("=" * 60)
    
    try:
        # Test by fetching fields
        discovery_path = Path("mappings/discovered_fields.json")
        result = client.discover_custom_fields(save_to_file=discovery_path)
        
        print("\n✓ Connection successful!\n")
        print("Discovered Fields:")
        print("-" * 40)
        
        for name, info in result["discovered_fields"].items():
            print(f"  {name}:")
            print(f"    ID: {info['id']}")
            print(f"    Name: {info['name']}")
            print(f"    Type: {info['type']}")
            print()
        
        print(f"\nTotal custom fields found: {len(result['all_custom_fields'])}")
        print(f"\nFull discovery saved to: {discovery_path}")
        
        # Test search with a limited query
        print("\n" + "-" * 40)
        print("Testing issue search (first 5 issues)...")
        
        issues = []
        for i, issue in enumerate(client.search_issues(max_results=5)):
            issues.append(issue)
            if i >= 4:
                break
        
        print(f"✓ Retrieved {len(issues)} issues")
        for issue in issues[:3]:
            key = issue.get("key")
            summary = issue.get("fields", {}).get("summary", "")[:50]
            print(f"  - {key}: {summary}...")
        
        return True
        
    except JiraAPIError as e:
        print(f"\n✗ Connection failed: {e}")
        return False


if __name__ == "__main__":
    test_connection()
