import os
import logging
from pathlib import Path

# Base directories
APP_DIR = Path(os.path.expanduser("~/.othertales_homework"))
CACHE_DIR = APP_DIR / "cache"
LOG_DIR = APP_DIR / "logs"
CONFIG_DIR = APP_DIR / "config"
TEMP_DIR = APP_DIR / "temp"  # For temporary files during dataset creation

# Configuration validation settings
CONFIG_VALIDATION = {
    "SERVER_PORT": {"type": "int", "min": 1024, "max": 65535},
    "API_TIMEOUT": {"type": "int", "min": 5, "max": 300},
    "GITHUB_TIMEOUT": {"type": "int", "min": 5, "max": 300},
    "MAX_FILE_SIZE_MB": {"type": "int", "min": 1, "max": 50},
    "LOG_LEVEL": {"type": "enum", "values": [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]},
    "MAX_LOG_SIZE": {"type": "int", "min": 1024 * 1024, "max": 100 * 1024 * 1024},
    "PARALLEL_MAX_WORKERS": {"type": "int", "min": 1, "max": 32},
}

# Function to validate a configuration value
def validate_config(name, value):
    """Validate a configuration value against its schema."""
    if name not in CONFIG_VALIDATION:
        return value  # No validation defined
        
    schema = CONFIG_VALIDATION[name]
    if schema["type"] == "int":
        if not isinstance(value, int):
            try:
                value = int(value)
            except (ValueError, TypeError):
                logging.warning(f"Invalid value for {name}: {value}. Using default.")
                return globals()[name]  # Return the default
                
        # Check bounds
        if "min" in schema and value < schema["min"]:
            logging.warning(f"Value for {name} too small: {value}. Using minimum: {schema['min']}")
            return schema["min"]
        if "max" in schema and value > schema["max"]:
            logging.warning(f"Value for {name} too large: {value}. Using maximum: {schema['max']}")
            return schema["max"]
            
    elif schema["type"] == "enum" and value not in schema["values"]:
        logging.warning(f"Invalid value for {name}: {value}. Using default.")
        return globals()[name]  # Return the default
        
    return value

# Ensure directories exist with proper permissions
try:
    import stat
    for directory in [APP_DIR, CACHE_DIR, LOG_DIR, CONFIG_DIR, TEMP_DIR]:
        directory.mkdir(exist_ok=True, parents=True)
        # Try to set appropriate permissions (owner read/write/execute only)
        try:
            os.chmod(directory, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        except Exception as e:
            logging.warning(f"Could not set permissions on {directory}: {e}")
except Exception as e:
    # Fall back to simple directory creation if permission setting fails
    logging.error(f"Error creating directories: {e}")
    for directory in [APP_DIR, CACHE_DIR, LOG_DIR, CONFIG_DIR, TEMP_DIR]:
        directory.mkdir(exist_ok=True, parents=True)
    
# Server settings (defaults, can be overridden in config)
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8080

# API connection settings
API_MAX_RETRIES = 3
API_TIMEOUT = 30
DEFAULT_BRANCH = "main"
DOWNLOAD_RETRIES = 5  # Specific retry count for file downloads

# GitHub API settings
GITHUB_API_URL = "https://api.github.com"
GITHUB_MAX_RETRIES = 3
GITHUB_TIMEOUT = 30
GITHUB_DEFAULT_BRANCH = "main"
GITHUB_DOWNLOAD_RETRIES = 5  # Specific retry count for file downloads

# Repository content settings
RELEVANT_FOLDERS = [
    "doc",
    "docs",
    "documentation",
    "example",
    "examples",
    "sample",
    "samples",
    "cookbook",
    "cookbooks",
    "tutorial",
    "tutorials",
    "guide",
    "guides",
]
IGNORED_DIRS = [".git", "node_modules", "__pycache__", "build", "dist"]
MAX_FILE_SIZE_MB = 10
TEXT_FILE_EXTENSIONS = [
    ".md",
    ".txt",
    ".py",
    ".js",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".html",
    ".css",
    ".json",
    ".yaml",
    ".yml",
    ".rst",
    ".ipynb",
]

# Hugging Face settings
HF_DATASET_TEMPLATE = {
    "metadata": {
        "creator": "github_hf_dataset_creator",
        "timestamp": "",
        "source": "",
        "version": "1.0",
    },
    "config": {"features": {"text": "string", "metadata": "dict"}},
}
HF_DEFAULT_REPO_TYPE = "dataset"

# Logging settings
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_LEVEL = logging.INFO
LOG_FILE = LOG_DIR / "app.log"
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 3

# Parallel processing settings
PARALLEL_MAX_WORKERS = None  # None means use CPU count - 1
PARALLEL_CHUNK_SIZE = 10  # Number of items to process at once in parallel
ASYNC_MAX_WORKERS = None  # None means use CPU count * 2 for IO-bound tasks
