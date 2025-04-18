import os
import dotenv
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def load_environment_variables():
    """
    Load environment variables from .env file and system environment.

    Returns:
        dict: Dictionary of environment variables
    """
    # Find the project root directory (which contains the .env file)
    current_dir = Path(os.getcwd())
    project_root = current_dir
    
    # First, try to find project root by looking for specific files/directories
    while project_root != project_root.parent:
        if (project_root / ".env").exists() or (project_root / "docker-compose.yml").exists():
            break
        project_root = project_root.parent
    
    # Define env file paths to check
    env_paths = [
        project_root / ".env",                 # Project root .env
        Path(".env"),                          # Current directory .env
        Path("../.env"),                       # Parent directory .env
        current_dir.parent / ".env",           # Explicit parent directory .env
        Path(os.path.expanduser("~/.env")),    # Home directory .env
        Path("/app/.env")                      # Docker environments
    ]
    
    env_loaded = False
    
    for env_file in env_paths:
        if env_file.exists():
            try:
                logger.info(f"Loading environment variables from {env_file.absolute()}")
                dotenv.load_dotenv(str(env_file.absolute()))
                logger.info(f"Loaded environment variables from {env_file}")
                env_loaded = True
                
                # Check for OPENAI_API_KEY immediately after loading this .env file
                if "OPENAI_API_KEY" in os.environ:
                    masked_key = os.environ["OPENAI_API_KEY"][:4] + "..." + os.environ["OPENAI_API_KEY"][-4:] if len(os.environ["OPENAI_API_KEY"]) > 8 else "***"
                    logger.info(f"Found OPENAI_API_KEY in environment after loading {env_file}: {masked_key}")
                    # Set in environment (just to be extra sure)
                    if not os.environ.get("OPENAI_API_KEY_SET"):
                        os.environ["OPENAI_API_KEY_SET"] = "true"
                
            except Exception as e:
                logger.error(f"Error loading environment from {env_file}: {e}")
    
    if not env_loaded:
        logger.warning("No .env files were successfully loaded")
    
    # Special check for OPENAI_API_KEY in environment
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        masked_key = openai_key[:4] + "..." + openai_key[-4:] if len(openai_key) > 8 else "***"
        logger.info(f"Found OPENAI_API_KEY in environment: {masked_key}")
    else:
        logger.warning("OPENAI_API_KEY not found in environment")

    # Get environment variables relevant to the application
    env_vars = {
        "github_token": os.environ.get("GITHUB_TOKEN", ""),
        "github_username": os.environ.get("GITHUB_USERNAME", ""),
        "huggingface_token": os.environ.get("HUGGINGFACE_TOKEN", ""),
        "huggingface_username": os.environ.get("HUGGINGFACE_USERNAME", ""),
        "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
        "neo4j_uri": os.environ.get("NEO4J_URI", ""),
        "neo4j_user": os.environ.get("NEO4J_USER", ""),
        "neo4j_password": os.environ.get("NEO4J_PASSWORD", ""),
    }
    
    # Log which environment variables are present (without showing their values)
    present_vars = [k for k, v in env_vars.items() if v]
    logger.info(f"Present environment variables: {', '.join(present_vars) or 'None'}")
    
    # Specifically log if OPENAI_API_KEY is found
    if "openai_api_key" in present_vars:
        logger.info("OPENAI_API_KEY is set in environment dictionary")

    return env_vars