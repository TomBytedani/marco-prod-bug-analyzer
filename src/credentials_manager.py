"""
Credentials Manager for secure storage of Jira credentials.
Stores credentials in user's app data directory.
"""

import json
import os
from pathlib import Path
from typing import Optional
import base64


class CredentialsManager:
    """Manages Jira credentials storage in user's AppData."""
    
    APP_NAME = "PIBugAnalyzer"
    
    def __init__(self):
        self.config_dir = self._get_config_dir()
        self.config_file = self.config_dir / "credentials.json"
        
    def _get_config_dir(self) -> Path:
        """Get the configuration directory for the app."""
        if os.name == 'nt':  # Windows
            base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
        else:  # Linux/Mac
            base = Path.home() / '.config'
        
        config_dir = base / self.APP_NAME
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir
    
    def _encode(self, value: str) -> str:
        """Simple obfuscation (not true encryption, but hides from casual viewing)."""
        return base64.b64encode(value.encode('utf-8')).decode('utf-8')
    
    def _decode(self, value: str) -> str:
        """Decode obfuscated value."""
        return base64.b64decode(value.encode('utf-8')).decode('utf-8')
    
    def has_credentials(self) -> bool:
        """Check if credentials have been saved."""
        if not self.config_file.exists():
            return False
        
        try:
            creds = self.load_credentials()
            return bool(creds.get('email') and creds.get('api_token'))
        except Exception:
            return False
    
    def save_credentials(self, email: str, api_token: str, jira_domain: str = None) -> None:
        """Save credentials to config file."""
        data = {
            'email': self._encode(email),
            'api_token': self._encode(api_token),
            'jira_domain': jira_domain or 'https://stellantis.atlassian.net'  # Fixed domain
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def load_credentials(self) -> dict:
        """Load credentials from config file."""
        if not self.config_file.exists():
            return {}
        
        with open(self.config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return {
            'email': self._decode(data.get('email', '')),
            'api_token': self._decode(data.get('api_token', '')),
            'jira_domain': data.get('jira_domain', 'https://stellantis.atlassian.net')
        }
    
    def clear_credentials(self) -> None:
        """Remove stored credentials."""
        if self.config_file.exists():
            self.config_file.unlink()
    
    def get_config_path(self) -> Path:
        """Return the path to the config directory."""
        return self.config_dir


if __name__ == "__main__":
    # Test credentials manager
    manager = CredentialsManager()
    print(f"Config directory: {manager.get_config_path()}")
    print(f"Has credentials: {manager.has_credentials()}")
