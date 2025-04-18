import logging
import logging.handlers
import sys
from pathlib import Path
from config.settings import (
    LOG_DIR,
    LOG_FORMAT,
    LOG_LEVEL,
    LOG_FILE,
    MAX_LOG_SIZE,
    LOG_BACKUP_COUNT,
)


def get_logger(name):
    """Get a logger with the specified name."""
    logger = logging.getLogger(name)
    return logger


class RealTimeLogHandler(logging.Handler):
    """Custom log handler to send log messages to the TUI in real-time."""

    def __init__(self, tui_callback):
        super().__init__()
        self.tui_callback = tui_callback

    def emit(self, record):
        log_entry = self.format(record)
        self.tui_callback(log_entry)


def setup_logging(tui_callback=None, secure_logging=True):
    """
    Configure logging for the application.
    
    Args:
        tui_callback: Optional callback for real-time logging to UI
        secure_logging: If True, will redact sensitive information in logs
        
    Returns:
        None
    """
    # Ensure log directory exists
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    
    # Set secure permissions on log directory
    try:
        import stat
        import os
        os.chmod(LOG_DIR, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except Exception as e:
        print(f"Warning: Could not set secure permissions on log directory: {e}")

    # Create root logger
    root_logger = logging.getLogger()
    # Set to DEBUG to capture all logs
    root_logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    root_logger.handlers = []

    # Create formatter with more detail for debugging
    formatter = logging.Formatter(LOG_FORMAT)
    detailed_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )
    
    # Add filter to redact sensitive information if secure_logging is enabled
    if secure_logging:
        class SensitiveDataFilter(logging.Filter):
            def __init__(self):
                super().__init__()
                self.patterns = [
                    (r'token=[^&\s]+', 'token=***REDACTED***'),
                    (r'password=[^&\s]+', 'password=***REDACTED***'),
                    (r'key=[^&\s]+', 'key=***REDACTED***'),
                    (r'Authorization: Bearer [^\s]+', 'Authorization: Bearer ***REDACTED***'),
                    (r'api_key=[^&\s]+', 'api_key=***REDACTED***'),
                    (r'\"password\": \"[^\"]+\"', '\"password\": \"***REDACTED***\"'),
                    (r'\"token\": \"[^\"]+\"', '\"token\": \"***REDACTED***\"')
                ]
                
            def filter(self, record):
                if isinstance(record.msg, str):
                    for pattern, replacement in self.patterns:
                        import re
                        record.msg = re.sub(pattern, replacement, record.msg)
                return True
                
        sensitive_filter = SensitiveDataFilter()
        root_logger.addFilter(sensitive_filter)

    # Create console handler with DEBUG level
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(detailed_formatter)
    console_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)

    # Create file handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_LOG_SIZE, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(detailed_formatter)
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    # Create real-time log handler if callback is provided
    if tui_callback:
        real_time_handler = RealTimeLogHandler(tui_callback)
        real_time_handler.setFormatter(formatter)
        real_time_handler.setLevel(logging.DEBUG)  # Set to DEBUG for maximum detail
        root_logger.addHandler(real_time_handler)

    # Set lower level for third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("github").setLevel(logging.WARNING)  # Changed from DEBUG to WARNING
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)  # Changed from DEBUG to WARNING
    
    # Set higher log levels for OpenAI libraries and HTTP components to reduce verbosity
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("openai.agents").setLevel(logging.WARNING)
    logging.getLogger("openai._base_client").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
    logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # For AI guided option specifically, suppress low-level logs
    logging.getLogger("utils.llm_client").setLevel(logging.INFO)
    
    # Also set higher log levels for GitHub-related modules
    logging.getLogger("github.client").setLevel(logging.WARNING)
    logging.getLogger("github.repository").setLevel(logging.WARNING)
    logging.getLogger("github.content_fetcher").setLevel(logging.WARNING)

    logging.info("Logging configured with selective DEBUG level for real-time updates")
