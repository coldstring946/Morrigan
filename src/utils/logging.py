"""
Logging utilities for the BBC Radio Processor.
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logging(level: str, log_path: str, service_name: str, 
                  max_size_mb: int = 10, backup_count: int = 5,
                  console: bool = True) -> logging.Logger:
    """
    Set up logging with file and console handlers.
    
    Args:
        level (str): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_path (str): Path to save log files.
        service_name (str): Name of the service (used for log file name).
        max_size_mb (int): Maximum log file size in MB.
        backup_count (int): Number of backup files to keep.
        console (bool): Whether to log to console.
        
    Returns:
        logging.Logger: Configured logger.
    """
    # Create log directory if it doesn't exist
    os.makedirs(log_path, exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    
    # Convert level string to logging level
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set up formatter
    formatter = logging.Formatter(
        '%(asctime)s [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Set up file handler
    log_file = os.path.join(log_path, f"{service_name}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=backup_count
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Set up console handler if requested
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # Create and return service-specific logger
    logger = logging.getLogger(service_name)
    logger.info(f"Logging initialized for {service_name} at level {level}")
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.
    
    Args:
        name (str): Logger name.
        
    Returns:
        logging.Logger: Logger instance.
    """
    return logging.getLogger(name)


def set_log_level(level: str) -> None:
    """
    Set the log level for the root logger.
    
    Args:
        level (str): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    root_logger = logging.getLogger()
    
    # Convert level string to logging level
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    root_logger.setLevel(numeric_level)
    
    # Update level for all handlers
    for handler in root_logger.handlers:
        handler.setLevel(numeric_level)
