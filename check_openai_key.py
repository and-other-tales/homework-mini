#!/usr/bin/env python3

import os
import logging
from config.credentials_manager import CredentialsManager
from utils.env_loader import load_environment_variables

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("check_openai_key")

def main():
    """Check if OpenAI API key is properly configured."""
    logger.info("Checking for OpenAI API key...")
    
    # Step 1: Load environment variables
    logger.info("Step 1: Loading environment variables")
    env_vars = load_environment_variables()
    
    # Step 2: Check OS environment directly
    logger.info("Step 2: Checking OS environment")
    env_key = os.environ.get("OPENAI_API_KEY")
    if env_key:
        masked_key = env_key[:4] + "..." + env_key[-4:] if len(env_key) > 8 else "***"
        logger.info(f"Found OpenAI API key in OS environment: {masked_key}")
    else:
        logger.warning("OpenAI API key not found in OS environment")
    
    # Step 3: Check using credentials manager
    logger.info("Step 3: Checking using credentials manager")
    credentials_manager = CredentialsManager()
    creds_key = credentials_manager.get_openai_key()
    
    if creds_key:
        masked_key = creds_key[:4] + "..." + creds_key[-4:] if len(creds_key) > 8 else "***"
        logger.info(f"Found OpenAI API key via credentials manager: {masked_key}")
    else:
        logger.warning("OpenAI API key not found via credentials manager")
    
    # Step 4: Check .env file directly
    logger.info("Step 4: Checking .env file directly")
    try:
        from pathlib import Path
        import re
        
        env_paths = [
            Path(".env"),
            Path("../.env"),
            Path(os.path.join(os.path.dirname(__file__), "../.env")),
        ]
        
        env_key_found = False
        for env_path in env_paths:
            if env_path.exists():
                logger.info(f"Reading .env file at {env_path.absolute()}")
                env_content = env_path.read_text()
                key_match = re.search(r'OPENAI_API_KEY=(.+)', env_content)
                
                if key_match:
                    env_key = key_match.group(1).strip()
                    masked_key = env_key[:4] + "..." + env_key[-4:] if len(env_key) > 8 else "***"
                    logger.info(f"Found OpenAI API key in .env file: {masked_key}")
                    env_key_found = True
                    break
                else:
                    logger.warning(f"No OpenAI API key pattern found in {env_path}")
        
        if not env_key_found:
            logger.warning("OpenAI API key not found in any .env file")
            
    except Exception as e:
        logger.error(f"Error checking .env file: {e}")
    
    # Summary
    key_found = env_key or creds_key or env_key_found
    if key_found:
        logger.info("OpenAI API key is properly configured!")
    else:
        logger.error("OpenAI API key is not configured. Please set OPENAI_API_KEY in your .env file or environment.")

if __name__ == "__main__":
    main()