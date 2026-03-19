"""
Configuration settings for the API.
"""

import os
from pathlib import Path
from typing import Optional


class Settings:
    """Application settings."""
    
    # API Settings
    APP_NAME: str = "Secret Detection API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "API for detecting secrets in text using CodeBERT model"
    
    # Server Settings
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    RELOAD: bool = False
    
    # Model Settings
    MODEL_PATH: str = "models/balanced/microsoft_codebert-base_complete"
    REGEX_FILE: str = "Secret-Regular-Expression.xlsx"
    
    # Inference Settings
    MAX_LENGTH: int = 256
    WINDOW_SIZE: int = 100
    USE_QUANTIZATION: bool = False
    DEVICE: Optional[str] = None  # None for auto-detect
    
    # Default Inference Parameters
    DEFAULT_BATCH_SIZE: int = 32
    
    # Cache Settings
    ENABLE_CACHE: bool = True
    CACHE_SIZE: int = 128
    
    @classmethod
    def validate(cls) -> bool:
        """Validate that required files exist."""
        model_path = Path(cls.MODEL_PATH)
        regex_file = Path(cls.REGEX_FILE)
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {cls.MODEL_PATH}")
        
        if not regex_file.exists():
            raise FileNotFoundError(f"Regex file not found: {cls.REGEX_FILE}")
        
        return True


# Global settings instance
settings = Settings()
