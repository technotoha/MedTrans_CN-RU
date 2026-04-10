"""
Logging utilities for the PDF translation pipeline.
Provides structured logging with file and console output.
"""

import sys
from pathlib import Path
from loguru import logger as _logger


def setup_logger(
    log_level: str = "INFO",
    log_file: Path = None,
    console_output: bool = True
) -> None:
    """
    Configure the application logger.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        console_output: Whether to output to console
    """
    # Remove default handler
    _logger.remove()
    
    # Console format with colors
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # File format (no colors, more detailed)
    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{process.id} | "
        "{thread.name} | "
        "{message}"
    )
    
    # Add console handler
    if console_output:
        _logger.add(
            sys.stderr,
            format=console_format,
            level=log_level,
            colorize=True,
            backtrace=True,
            diagnose=True
        )
    
    # Add file handler
    if log_file:
        # Ensure log directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        _logger.add(
            log_file,
            format=file_format,
            level=log_level,
            rotation="10 MB",
            retention="7 days",
            compression="zip",
            backtrace=True,
            diagnose=True
        )


def get_logger(name: str = __name__):
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Configured logger instance
    """
    return _logger.bind(name=name)


# Context manager for timing operations
class Timer:
    """Context manager for timing code blocks."""
    
    def __init__(self, logger, operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time = None
    
    def __enter__(self):
        import time
        self.start_time = time.time()
        self.logger.debug(f"Starting: {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        elapsed = time.time() - self.start_time
        if exc_type is None:
            self.logger.debug(f"Completed: {self.operation} in {elapsed:.2f}s")
        else:
            self.logger.error(f"Failed: {self.operation} after {elapsed:.2f}s - {exc_val}")
        return False


def timer(logger, operation: str):
    """Decorator for timing function execution."""
    import time
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            logger.debug(f"Starting: {operation}")
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start
                logger.debug(f"Completed: {operation} in {elapsed:.2f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"Failed: {operation} after {elapsed:.2f}s - {e}")
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            logger.debug(f"Starting: {operation}")
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                logger.debug(f"Completed: {operation} in {elapsed:.2f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"Failed: {operation} after {elapsed:.2f}s - {e}")
                raise
        
        # Detect if function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
