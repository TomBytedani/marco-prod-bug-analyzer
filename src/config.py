"""
Configuration management for the Bug Analysis Workflow.
Loads environment variables and provides validated configuration.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


class Config:
    """Configuration container with validation."""
    
    def __init__(self):
        # Jira connection settings
        self.jira_site = self._get_required("JIRA_SITE")
        self.jira_username = self._get_required("JIRA_USERNAME")
        self.jira_api_token = self._get_required("JIRA_API_TOKEN")
        
        # Query settings
        self.jira_project = os.getenv("JIRA_PROJECT", "PI")
        self.jira_jql = os.getenv(
            "JIRA_JQL",
            f'project = "{self.jira_project}" ORDER BY created DESC'
        )
        
        # Output settings
        self.output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
        self.report_prefix = os.getenv("REPORT_PREFIX", "PI-report")
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_required(self, key: str) -> str:
        """Get a required environment variable or raise error."""
        value = os.getenv(key)
        if not value:
            raise ConfigError(f"Missing required environment variable: {key}")
        return value
    
    @property
    def jira_base_url(self) -> str:
        """Get the base URL for Jira REST API."""
        return f"{self.jira_site}/rest/api/3"
    
    @property
    def jira_auth(self) -> tuple:
        """Get authentication tuple for requests."""
        return (self.jira_username, self.jira_api_token)


# Global config instance - lazy loaded
_config = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


if __name__ == "__main__":
    # Test configuration loading
    try:
        config = get_config()
        print(f"✓ Jira Site: {config.jira_site}")
        print(f"✓ Jira Username: {config.jira_username}")
        print(f"✓ Jira Project: {config.jira_project}")
        print(f"✓ Output Directory: {config.output_dir}")
        print(f"✓ JQL Query: {config.jira_jql[:50]}...")
    except ConfigError as e:
        print(f"✗ Configuration Error: {e}")
