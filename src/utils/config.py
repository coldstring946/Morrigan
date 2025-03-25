"""
Configuration utilities for the BBC Radio Processor.
"""
import os
import yaml
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Exception raised when a configuration error occurs."""
    pass


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from a YAML file.
    
    Args:
        config_path (str): Path to the configuration file.
        
    Returns:
        dict: Configuration dictionary.
    """
    try:
        if not os.path.exists(config_path):
            raise ConfigError(f"Configuration file not found: {config_path}")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Validate configuration
        validate_config(config)
        
        return config
    
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML configuration: {e}")
        raise ConfigError(f"Error parsing YAML configuration: {e}")
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        raise ConfigError(f"Error loading configuration: {e}")


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate the configuration structure.
    
    Args:
        config (dict): Configuration dictionary.
    """
    # Check for required sections
    required_sections = ["network", "database", "downloader", "transcription", "logging"]
    for section in required_sections:
        if section not in config:
            raise ConfigError(f"Missing required configuration section: {section}")
    
    # Validate network section
    network = config["network"]
    if "nas_mount" not in network:
        raise ConfigError("Missing required configuration: network.nas_mount")
    
    # Validate database section
    database = config["database"]
    if "type" not in database:
        raise ConfigError("Missing required configuration: database.type")
    if database["type"] not in ["sqlite", "postgresql"]:
        raise ConfigError(f"Unsupported database type: {database['type']}")
    if "path" not in database:
        raise ConfigError("Missing required configuration: database.path")
    if "name" not in database:
        raise ConfigError("Missing required configuration: database.name")
    
    # Validate downloader section
    downloader = config["downloader"]
    if "download_path" not in downloader:
        raise ConfigError("Missing required configuration: downloader.download_path")
    if "get_iplayer_options" not in downloader:
        raise ConfigError("Missing required configuration: downloader.get_iplayer_options")
    
    # Validate transcription section
    transcription = config["transcription"]
    if "input_path" not in transcription:
        raise ConfigError("Missing required configuration: transcription.input_path")
    if "output_path" not in transcription:
        raise ConfigError("Missing required configuration: transcription.output_path")
    if "model" not in transcription:
        raise ConfigError("Missing required configuration: transcription.model")
    
    # Validate logging section
    logging_config = config["logging"]
    if "log_path" not in logging_config:
        raise ConfigError("Missing required configuration: logging.log_path")
    if "level" not in logging_config:
        raise ConfigError("Missing required configuration: logging.level")


def save_config(config: Dict[str, Any], config_path: str) -> None:
    """
    Save configuration to a YAML file.
    
    Args:
        config (dict): Configuration dictionary.
        config_path (str): Path to save the configuration file.
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"Configuration saved to {config_path}")
    
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")
        raise ConfigError(f"Error saving configuration: {e}")


def get_config_value(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """
    Get a configuration value using a dotted key path.
    
    Args:
        config (dict): Configuration dictionary.
        key_path (str): Dotted key path (e.g., "network.nas_mount").
        default (any, optional): Default value if the key doesn't exist.
        
    Returns:
        any: Configuration value or default.
    """
    keys = key_path.split('.')
    result = config
    
    for key in keys:
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            return default
    
    return result


def update_config_value(config: Dict[str, Any], key_path: str, value: Any) -> Dict[str, Any]:
    """
    Update a configuration value using a dotted key path.
    
    Args:
        config (dict): Configuration dictionary.
        key_path (str): Dotted key path (e.g., "network.nas_mount").
        value (any): Value to set.
        
    Returns:
        dict: Updated configuration dictionary.
    """
    keys = key_path.split('.')
    current = config
    
    # Navigate to the last level
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    # Set the value
    current[keys[-1]] = value
    
    return config
