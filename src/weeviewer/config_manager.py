"""
Configuration Management Module

Provides persistent storage and management functionality for application configuration.
"""

import os
import json
import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

# Configuration file path
CONFIG_FILE = "viewer_config.json"

# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class WindowConfig:
    """Window configuration"""
    width: int = 1000
    height: int = 700
    x: int = 50
    y: int = 50
    maximized: bool = False
    sash_position: int = 500


@dataclass
class SearchConfig:
    """Search configuration"""
    case_sensitive: bool = False
    whole_word: bool = False
    regex: bool = False
    search_scope: str = "all"
    highlight_color: str = "#FF8C00"  # Dark orange
    background_color: str = "#FFFFC8"  # Light yellow


@dataclass
class HistoryConfig:
    """History configuration"""
    max_file_history: int = 10
    max_path_history: int = 20
    enable_file_history: bool = True
    enable_path_history: bool = True


@dataclass
class ThemeConfig:
    """Theme configuration"""
    current_theme: str = "light"
    custom_font_size: int = 10
    custom_font_family: str = "default"


@dataclass
class AdvancedConfig:
    """Advanced configuration"""
    auto_save: bool = True
    auto_save_interval: int = 300  # 5 minutes
    enable_logging: bool = True
    log_level: str = "INFO"
    max_log_files: int = 30


@dataclass
class AppConfig:
    """Application configuration"""
    window: WindowConfig = field(default_factory=WindowConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    theme: ThemeConfig = field(default_factory=ThemeConfig)
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)
    file_history: list = field(default_factory=list)  # File history
    path_history: list = field(default_factory=list)  # Path history
    bookmarks: list = field(default_factory=list)  # Bookmarks
    version: str = "1.0"
    last_updated: str = ""


class ConfigManager:
    """Configuration manager

    Responsible for loading, saving, and managing application configuration.
    """

    def __init__(self, config_file: Optional[str] = None):
        """Initialize the configuration manager

        Args:
            config_file: Configuration file path, defaults to viewer_config.json
        """
        self.config_file = config_file or CONFIG_FILE
        self.config = AppConfig()
        self._dirty = False

        # Load configuration
        self.load()

        logger.info(f"ConfigManager initialized, configuration file: {self.config_file}")
    
    def load(self) -> bool:
        """Load configuration file

        Returns:
            Whether the load was successful
        """
        try:
            if not os.path.exists(self.config_file):
                logger.info(f"Configuration file does not exist, using default configuration: {self.config_file}")
                return False

            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate configuration version
            saved_version = data.get('version', '')
            if saved_version != self.config.version:
                logger.info(f"Configuration version mismatch: {saved_version} != {self.config.version}, using default configuration")

            # Update configuration
            self._update_config_from_dict(data)

            logger.info(f"Configuration loaded successfully: {self.config_file}")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse configuration file JSON: {e}")
            return False

        except Exception as e:
            logger.error(f"Failed to load configuration file: {e}")
            return False
    
    def _update_config_from_dict(self, data: Dict[str, Any]) -> None:
        """Update configuration from dictionary

        Args:
            data: Configuration dictionary
        """
        # Update window configuration
        if 'window' in data:
            window_data = data['window']
            self.config.window.width = window_data.get('width', self.config.window.width)
            self.config.window.height = window_data.get('height', self.config.window.height)
            self.config.window.x = window_data.get('x', self.config.window.x)
            self.config.window.y = window_data.get('y', self.config.window.y)
            self.config.window.maximized = window_data.get('maximized', self.config.window.maximized)
            self.config.window.sash_position = window_data.get('sash_position', self.config.window.sash_position)

        # Update search configuration
        if 'search' in data:
            search_data = data['search']
            self.config.search.case_sensitive = search_data.get('case_sensitive', self.config.search.case_sensitive)
            self.config.search.whole_word = search_data.get('whole_word', self.config.search.whole_word)
            self.config.search.regex = search_data.get('regex', self.config.search.regex)
            self.config.search.search_scope = search_data.get('search_scope', self.config.search.search_scope)
            self.config.search.highlight_color = search_data.get('highlight_color', self.config.search.highlight_color)
            self.config.search.background_color = search_data.get('background_color', self.config.search.background_color)

        # Update history configuration
        if 'history' in data:
            history_data = data['history']
            self.config.history.max_file_history = history_data.get('max_file_history', self.config.history.max_file_history)
            self.config.history.max_path_history = history_data.get('max_path_history', self.config.history.max_path_history)
            self.config.history.enable_file_history = history_data.get('enable_file_history', self.config.history.enable_file_history)
            self.config.history.enable_path_history = history_data.get('enable_path_history', self.config.history.enable_path_history)

        # Update theme configuration
        if 'theme' in data:
            theme_data = data['theme']
            self.config.theme.current_theme = theme_data.get('current_theme', self.config.theme.current_theme)
            self.config.theme.custom_font_size = theme_data.get('custom_font_size', self.config.theme.custom_font_size)
            self.config.theme.custom_font_family = theme_data.get('custom_font_family', self.config.theme.custom_font_family)

        # Update advanced configuration
        if 'advanced' in data:
            advanced_data = data['advanced']
            self.config.advanced.auto_save = advanced_data.get('auto_save', self.config.advanced.auto_save)
            self.config.advanced.auto_save_interval = advanced_data.get('auto_save_interval', self.config.advanced.auto_save_interval)
            self.config.advanced.enable_logging = advanced_data.get('enable_logging', self.config.advanced.enable_logging)
            self.config.advanced.log_level = advanced_data.get('log_level', self.config.advanced.log_level)
            self.config.advanced.max_log_files = advanced_data.get('max_log_files', self.config.advanced.max_log_files)

        # Update metadata
        self.config.version = data.get('version', self.config.version)
        self.config.last_updated = data.get('last_updated', self.config.last_updated)

        # Update file history
        if 'file_history' in data:
            self.config.file_history = data.get('file_history', [])

        # Update path history
        if 'path_history' in data:
            self.config.path_history = data.get('path_history', [])

        # Update bookmarks
        if 'bookmarks' in data:
            self.config.bookmarks = data.get('bookmarks', [])
    
    def save(self) -> bool:
        """Save configuration to file

        Returns:
            Whether the save was successful
        """
        try:
            # Update timestamp
            self.config.last_updated = datetime.now().isoformat()

            # Convert to dictionary
            data = asdict(self.config)

            # Write to file
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            self._dirty = False
            logger.info(f"Configuration saved successfully: {self.config_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to save configuration file: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value

        Args:
            key: Configuration key, supports dot-separated nested keys (e.g., "window.width")
            default: Default value

        Returns:
            Configuration value
        """
        try:
            keys = key.split('.')
            value = self.config

            for k in keys:
                if hasattr(value, k):
                    value = getattr(value, k)
                else:
                    return default

            return value

        except Exception as e:
            logger.warning(f"Failed to get configuration: key={key}, error={e}")
            return default
    
    def set(self, key: str, value: Any) -> bool:
        """Set configuration value

        Args:
            key: Configuration key, supports dot-separated nested keys (e.g., "window.width")
            value: Configuration value

        Returns:
            Whether the setting was successful
        """
        try:
            keys = key.split('.')
            obj = self.config

            # Traverse to the second-to-last key
            for k in keys[:-1]:
                if hasattr(obj, k):
                    obj = getattr(obj, k)
                else:
                    logger.warning(f"Configuration key does not exist: {key}")
                    return False

            # Set the value for the last key
            last_key = keys[-1]
            if hasattr(obj, last_key):
                setattr(obj, last_key, value)
                self._dirty = True
                logger.debug(f"Configuration updated: {key}={value}")
                return True
            else:
                logger.warning(f"Configuration key does not exist: {key}")
                return False

        except Exception as e:
            logger.error(f"Failed to set configuration: key={key}, value={value}, error={e}")
            return False
    
    def reset(self) -> bool:
        """Reset to default configuration

        Returns:
            Whether the reset was successful
        """
        try:
            self.config = AppConfig()
            self._dirty = True
            logger.info("Configuration reset to default values")
            return True

        except Exception as e:
            logger.error(f"Failed to reset configuration: {e}")
            return False
    
    def export(self, export_file: str) -> bool:
        """Export configuration to file

        Args:
            export_file: Export file path

        Returns:
            Whether the export was successful
        """
        try:
            data = asdict(self.config)

            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            logger.info(f"Configuration exported successfully: {export_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to export configuration: {e}")
            return False
    
    def import_config(self, import_file: str) -> bool:
        """Import configuration from file

        Args:
            import_file: Import file path

        Returns:
            Whether the import was successful
        """
        try:
            with open(import_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._update_config_from_dict(data)
            self._dirty = True

            logger.info(f"Configuration imported successfully: {import_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to import configuration: {e}")
            return False
    
    def is_dirty(self) -> bool:
        """Check if configuration has unsaved changes

        Returns:
            Whether there are unsaved changes
        """
        return self._dirty
    
    def get_config(self) -> AppConfig:
        """Get complete configuration object

        Returns:
            Configuration object
        """
        return self.config
    
    def get_dict(self) -> Dict[str, Any]:
        """Get configuration dictionary

        Returns:
            Configuration dictionary
        """
        return asdict(self.config)