#!/usr/bin/env python3

import os
import json
import logging
from pathlib import Path
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("debug_env")

def check_env_file():
    """Check if .env file exists and is readable."""
    env_file = Path(".env")
    
    if not env_file.exists():
        logger.error(f".env file not found at {env_file.absolute()}")
        return False
    
    try:
        content = env_file.read_text()
        logger.info(f".env file exists with size {len(content)} bytes")
        
        # Count number of lines with key-value pairs
        lines = [line.strip() for line in content.split('\n') if '=' in line and not line.strip().startswith('#')]
        logger.info(f"Found {len(lines)} environment variables in .env file")
        
        # Check for OPENAI_API_KEY specifically (without revealing it)
        has_openai_key = any(line.startswith('OPENAI_API_KEY=') for line in lines)
        if has_openai_key:
            logger.info("OPENAI_API_KEY found in .env file")
        else:
            logger.warning("OPENAI_API_KEY not found in .env file")
        
        return True
    except Exception as e:
        logger.error(f"Error reading .env file: {e}")
        return False

def check_environment_variables():
    """Check for relevant environment variables in the OS environment."""
    relevant_vars = {
        "OPENAI_API_KEY": "OpenAI API key",
        "GITHUB_TOKEN": "GitHub token",
        "HUGGINGFACE_TOKEN": "Hugging Face token",
        "NEO4J_URI": "Neo4j URI",
        "NEO4J_USER": "Neo4j username",
        "NEO4J_PASSWORD": "Neo4j password"
    }
    
    found_vars = []
    missing_vars = []
    
    for var_name, description in relevant_vars.items():
        value = os.environ.get(var_name)
        if value:
            # For sensitive values, don't log the whole thing
            masked_value = "..." if len(value) < 8 else f"{value[:4]}...{value[-4:]}"
            found_vars.append(f"{var_name} ({masked_value})")
        else:
            missing_vars.append(var_name)
    
    if found_vars:
        logger.info(f"Found environment variables: {', '.join(found_vars)}")
    
    if missing_vars:
        logger.warning(f"Missing environment variables: {', '.join(missing_vars)}")
    
    # Special check for OPENAI_API_KEY
    if "OPENAI_API_KEY" in os.environ:
        logger.info("OPENAI_API_KEY is properly set in the environment")
    else:
        logger.error("OPENAI_API_KEY is not set in the environment")

def debug_dotenv_loading():
    """Debug the process of loading environment variables with dotenv."""
    try:
        import dotenv
        
        logger.info("Testing dotenv.load_dotenv() function")
        
        env_file = Path(".env")
        if not env_file.exists():
            logger.error(f".env file not found at {env_file.absolute()}")
            return
        
        # Try to load the environment
        result = dotenv.load_dotenv(env_file)
        logger.info(f"dotenv.load_dotenv() returned: {result}")
        
        # Check if OPENAI_API_KEY was loaded
        if "OPENAI_API_KEY" in os.environ:
            logger.info("OPENAI_API_KEY was successfully loaded into environment by dotenv")
        else:
            logger.warning("dotenv did not load OPENAI_API_KEY into environment")
            
            # Try reading directly
            try:
                content = env_file.read_text()
                import re
                key_match = re.search(r'OPENAI_API_KEY=(.+)', content)
                
                if key_match:
                    key = key_match.group(1).strip()
                    logger.info(f"Found OPENAI_API_KEY in .env file: {key[:4]}...{key[-4:]}")
                else:
                    logger.error("Could not find OPENAI_API_KEY pattern in .env file")
            except Exception as e:
                logger.error(f"Error parsing .env file directly: {e}")
        
    except ImportError:
        logger.error("dotenv module not available")
    except Exception as e:
        logger.error(f"Error testing dotenv: {e}")

def check_config_file():
    """Check if the application config file exists and has relevant settings."""
    try:
        # Common config paths
        paths = [
            Path("config/config.json"),
            Path("backend/config/config.json"),
            Path("~/.othertales_homework/config.json").expanduser()
        ]
        
        found = False
        for config_path in paths:
            if config_path.exists():
                logger.info(f"Found config file at {config_path}")
                
                # Read and check content
                try:
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                    
                    # Check for relevant keys (without revealing sensitive values)
                    keys = list(config.keys())
                    logger.info(f"Config file contains keys: {', '.join(keys)}")
                    
                    # Check specifically for OpenAI key
                    if "openai_key" in config:
                        key = config["openai_key"]
                        masked_key = "..." if len(key) < 8 else f"{key[:4]}...{key[-4:]}"
                        logger.info(f"Found openai_key in config: {masked_key}")
                    else:
                        logger.warning("No openai_key found in config")
                        
                    found = True
                    
                except Exception as e:
                    logger.error(f"Error reading config file {config_path}: {e}")
        
        if not found:
            logger.warning("No config files found")
            
    except Exception as e:
        logger.error(f"Error checking config files: {e}")

def main():
    """Run all environment checks."""
    logger.info("=== Environment Debug Tool ===")
    logger.info(f"Current working directory: {os.getcwd()}")
    
    # Check Python version
    logger.info(f"Python version: {sys.version}")
    
    # Check .env file
    logger.info("\n=== Checking .env file ===")
    check_env_file()
    
    # Check environment variables
    logger.info("\n=== Checking environment variables ===")
    check_environment_variables()
    
    # Debug dotenv loading
    logger.info("\n=== Debugging dotenv loading ===")
    debug_dotenv_loading()
    
    # Check config file
    logger.info("\n=== Checking config files ===")
    check_config_file()
    
    logger.info("\n=== Debug complete ===")

if __name__ == "__main__":
    main()