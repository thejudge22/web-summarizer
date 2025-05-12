# ABOUTME: Loads environment variables from .env and system for config.
# ABOUTME: Used for both local dev and Dockerized production.

import os
from dotenv import load_dotenv

load_dotenv()  # Loads .env if present (local dev)

class Config:
    FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.0-flash")
    KARAKEEP_API_URL = os.environ.get("KARAKEEP_API_URL")
    KARAKEEP_API_KEY = os.environ.get("KARAKEEP_API_KEY")
    KARAKEEP_LIST_NAME = os.environ.get("KARAKEEP_LIST_NAME")
    
    # Calculated property for Karakeep integration status
    @classmethod
    def is_karakeep_enabled(cls):
        """Check if all required Karakeep settings are configured."""
        return bool(cls.KARAKEEP_API_URL and cls.KARAKEEP_API_KEY and cls.KARAKEEP_LIST_NAME)
    
    # KARAKEEP_ENABLED is now a property
    
    # ... add more as needed

    @property
    def KARAKEEP_ENABLED(self):
        """Check if Karakeep integration is enabled."""
        return self.is_karakeep_enabled()

# Usage: from config import Config; Config.FLASK_SECRET_KEY