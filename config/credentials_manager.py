import json
import os
import sys
import logging
from pathlib import Path
from config.settings import CONFIG_DIR
from utils.env_loader import load_environment_variables

# Setup logger
logger = logging.getLogger(__name__)

# Global keyring status
HAS_KEYRING = False
KEYRING_CHECKED = False

def check_keyring():
    """Check if keyring is available and working."""
    global HAS_KEYRING, KEYRING_CHECKED
    
    if KEYRING_CHECKED:
        return HAS_KEYRING
        
    try:
        import keyring
        # Check for and install keyrings.alt as fallback if needed
        try:
            import keyrings.alt
            logger.info("keyrings.alt is available as a fallback")
        except ImportError:
            try:
                import pip
                logger.info("Installing keyrings.alt as a fallback keyring backend")
                import subprocess
                subprocess.check_call([sys.executable, "-m", "pip", "install", "keyrings.alt"])
                import keyrings.alt
            except Exception as e:
                logger.warning(f"Could not install keyrings.alt: {e}")
                
        # Test that keyring actually works (not just importable)
        try:
            keyring.get_keyring()
            HAS_KEYRING = True
            logger.info("Keyring is available and will be used for storing credentials")
        except Exception as e:
            # Try to set a fallback keyring
            try:
                from keyrings.alt import file
                keyring.set_keyring(file.PlaintextKeyring())
                # Verify the fallback works
                keyring.get_keyring()
                HAS_KEYRING = True
                logger.info("Using PlaintextKeyring as fallback for storing credentials")
            except Exception as fallback_error:
                # Both main and fallback keyring failed
                logger.warning(f"Keyring module found but not usable: {e}")
                logger.warning(f"Fallback keyring also failed: {fallback_error}")
                logger.warning("Will store credentials in config file instead (less secure)")
    except ImportError:
        # Keyring module not installed
        logger.warning("Keyring module not found, will store credentials in config file")
    
    KEYRING_CHECKED = True
    return HAS_KEYRING


class CredentialsManager:
    """Manages secure storage and retrieval of API credentials and application settings."""

    SERVICE_NAME = "othertales_homework"
    HUGGINGFACE_KEY = "huggingface_token"
    OPENAPI_KEY = "openapi_key"
    OPENAI_KEY = "openai_key"  # Added for OpenAI API
    GITHUB_KEY = "github_token"  # Add constant for GitHub key
    NEO4J_URI_KEY = "neo4j_uri"
    NEO4J_USER_KEY = "neo4j_username"
    NEO4J_PASSWORD_KEY = "neo4j_password"
    AWS_ACCESS_KEY = "aws_access_key"
    AWS_SECRET_KEY = "aws_secret_key"
    AWS_REGION_KEY = "aws_region"
    CONFIG_FILE = CONFIG_DIR / "config.json"
    
    # Default settings
    DEFAULT_SERVER_PORT = 8080
    DEFAULT_TEMP_DIR = str(Path(os.path.expanduser("~/.othertales_homework/temp")))
    DEFAULT_AWS_REGION = "us-east-1"

    def __init__(self):
        self._ensure_config_file_exists()
        # Load environment variables
        self.env_vars = load_environment_variables()
        # Extract usernames from tokens if available
        self._extract_usernames_from_env()
        # Check keyring availability
        self.has_keyring = check_keyring()
        
        if self.has_keyring:
            import keyring
            self.keyring = keyring
        else:
            self.keyring = None

    def _ensure_config_file_exists(self):
        """Ensure the configuration file exists with default values."""
        if not self.CONFIG_FILE.exists():
            default_config = {
                "huggingface_username": "",
                "server_port": self.DEFAULT_SERVER_PORT,
                "temp_dir": self.DEFAULT_TEMP_DIR
            }
            self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.CONFIG_FILE.write_text(json.dumps(default_config, indent=2))
            logger.info(f"Created default configuration file at {self.CONFIG_FILE}")

    def _extract_usernames_from_env(self):
        """Try to update usernames in config if we have tokens in env variables."""
        try:
            config = self._load_config()
            updated = False

            # HuggingFace username extraction
            if self.env_vars.get("huggingface_token") and not config.get(
                "huggingface_username"
            ):
                hf_username = self.env_vars.get("huggingface_username")
                if hf_username:
                    config["huggingface_username"] = hf_username
                    updated = True

            if updated:
                self._save_config(config)
        except Exception as e:
            logger.error(f"Error extracting usernames from env: {e}")

    def save_huggingface_credentials(self, username, token):
        """Save HuggingFace credentials."""
        try:
            config = self._load_config()
            config["huggingface_username"] = username
            
            # Try to use keyring if available
            if self.has_keyring:
                try:
                    self.keyring.set_password(self.SERVICE_NAME, self.HUGGINGFACE_KEY, token)
                    logger.info("Saved HuggingFace token to keyring")
                except Exception as e:
                    logger.warning(f"Keyring save failed, storing in config file: {e}")
                    config["huggingface_token"] = token
            else:
                # Save in config file if keyring not available 
                config["huggingface_token"] = token
                logger.info("Saved HuggingFace token to config file")
                    
            self._save_config(config)
            logger.info(f"Saved HuggingFace credentials for user {username}")
            return True
        except Exception as e:
            logger.error(f"Failed to save HuggingFace credentials: {e}")
            return False

    def get_huggingface_credentials(self):
        """Get HuggingFace credentials with environment variable fallback."""
        config = self._load_config()
        username = config.get("huggingface_username", "")
        token = None

        # Try to get token from keyring if available
        if self.has_keyring:
            try:
                token = self.keyring.get_password(self.SERVICE_NAME, self.HUGGINGFACE_KEY)
                if token:
                    logger.debug("Retrieved HuggingFace token from keyring")
            except Exception as e:
                logger.warning(f"Error accessing keyring: {e}")
                # Don't retry keyring operations for this session
                global HAS_KEYRING
                HAS_KEYRING = False
                self.has_keyring = False

        # If not found in keyring, try config file
        if not token and "huggingface_token" in config:
            token = config.get("huggingface_token")
            logger.debug("Using HuggingFace token from config file")

        # If still not found, check environment variable
        if not token and self.env_vars.get("huggingface_token"):
            token = self.env_vars.get("huggingface_token")
            logger.debug("Using HuggingFace token from environment variables")

        return username, token
        
    def save_openapi_key(self, key):
        """Save OpenAPI API key."""
        try:
            config = self._load_config()
            
            # Try to use keyring if available
            if self.has_keyring:
                try:
                    self.keyring.set_password(self.SERVICE_NAME, self.OPENAPI_KEY, key)
                    logger.info("Saved OpenAPI key to keyring")
                except Exception as e:
                    logger.warning(f"Keyring save failed, storing in config file: {e}")
                    config["openapi_key"] = key
            else:
                # Save in config file if keyring not available
                config["openapi_key"] = key
                logger.info("Saved OpenAPI key to config file")
                    
            self._save_config(config)
            return True
        except Exception as e:
            logger.error(f"Failed to save OpenAPI API key: {e}")
            return False

    def get_openapi_key(self):
        """Get OpenAPI API key."""
        config = self._load_config()
        key = None

        # Try to get key from keyring if available
        if self.has_keyring:
            try:
                key = self.keyring.get_password(self.SERVICE_NAME, self.OPENAPI_KEY)
                if key:
                    logger.debug("Retrieved OpenAPI key from keyring")
            except Exception as e:
                logger.warning(f"Error accessing keyring: {e}")
                # Don't retry keyring operations for this session
                global HAS_KEYRING
                HAS_KEYRING = False
                self.has_keyring = False

        # If not found in keyring, try config file
        if not key and "openapi_key" in config:
            key = config.get("openapi_key")
            logger.debug("Using OpenAPI key from config file")

        # If still not found, check environment variable
        if not key and self.env_vars.get("openapi_key"):
            key = self.env_vars.get("openapi_key")
            logger.debug("Using OpenAPI key from environment variables")

        return key
        
    def get_server_port(self):
        """Get configured server port."""
        config = self._load_config()
        return config.get("server_port", self.DEFAULT_SERVER_PORT)
    
    def save_server_port(self, port):
        """Save server port configuration."""
        try:
            config = self._load_config()
            config["server_port"] = int(port)
            self._save_config(config)
            logger.info(f"Saved server port: {port}")
            return True
        except Exception as e:
            logger.error(f"Failed to save server port: {e}")
            return False
    
    def get_temp_dir(self):
        """Get configured temporary directory path."""
        config = self._load_config()
        return config.get("temp_dir", self.DEFAULT_TEMP_DIR)
    
    def save_temp_dir(self, dir_path):
        """Save temporary directory configuration."""
        try:
            # Ensure directory exists
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            
            config = self._load_config()
            config["temp_dir"] = dir_path
            self._save_config(config)
            logger.info(f"Saved temporary directory: {dir_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save temporary directory: {e}")
            return False
            
    def save_neo4j_credentials(self, uri, username, password):
        """Save Neo4j database credentials."""
        try:
            config = self._load_config()
            
            # Try to use keyring if available
            if self.has_keyring:
                try:
                    self.keyring.set_password(self.SERVICE_NAME, self.NEO4J_URI_KEY, uri)
                    self.keyring.set_password(self.SERVICE_NAME, self.NEO4J_USER_KEY, username)
                    self.keyring.set_password(self.SERVICE_NAME, self.NEO4J_PASSWORD_KEY, password)
                    logger.info("Saved Neo4j credentials to keyring")
                except Exception as e:
                    logger.warning(f"Keyring save failed, storing in config file: {e}")
                    config["neo4j_uri"] = uri
                    config["neo4j_username"] = username
                    config["neo4j_password"] = password
            else:
                # Save in config file if keyring not available
                config["neo4j_uri"] = uri
                config["neo4j_username"] = username
                config["neo4j_password"] = password
                logger.info("Saved Neo4j credentials to config file")
                    
            self._save_config(config)
            logger.info(f"Saved Neo4j credentials for {username}@{uri}")
            return True
        except Exception as e:
            logger.error(f"Failed to save Neo4j credentials: {e}")
            return False
    
    def get_neo4j_credentials(self):
        """Get Neo4j database credentials."""
        config = self._load_config()
        uri = None
        username = None
        password = None
        
        # First check environment variables as these are often most up-to-date
        env_uri = os.environ.get("NEO4J_URI")
        env_user = os.environ.get("NEO4J_USER")
        env_pass = os.environ.get("NEO4J_PASSWORD")
        
        if env_uri and env_user and env_pass:
            logger.info(f"Retrieved Neo4j credentials from environment variables: {env_user}@{env_uri}")
            return {
                "uri": env_uri,
                "username": env_user,
                "password": env_pass
            }
        
        # Try to get credentials from keyring if available
        if self.has_keyring:
            try:
                uri = self.keyring.get_password(self.SERVICE_NAME, self.NEO4J_URI_KEY)
                username = self.keyring.get_password(self.SERVICE_NAME, self.NEO4J_USER_KEY)
                password = self.keyring.get_password(self.SERVICE_NAME, self.NEO4J_PASSWORD_KEY)
                if uri and username and password:
                    logger.info(f"Retrieved Neo4j credentials from keyring: {username}@{uri}")
                    return {
                        "uri": uri,
                        "username": username,
                        "password": password
                    }
            except Exception as e:
                logger.warning(f"Error accessing keyring for Neo4j credentials: {e}")
                # Don't retry keyring operations for this session
                global HAS_KEYRING
                HAS_KEYRING = False
                self.has_keyring = False
        
        # If not found in keyring, try config file
        if "neo4j_uri" in config and "neo4j_username" in config and "neo4j_password" in config:
            uri = config.get("neo4j_uri")
            username = config.get("neo4j_username")
            password = config.get("neo4j_password")
            if uri and username and password:
                logger.info(f"Retrieved Neo4j credentials from config file: {username}@{uri}")
                return {
                    "uri": uri,
                    "username": username,
                    "password": password
                }
        
        # If still not found, check environment variables in env_vars (from .env file)
        uri = self.env_vars.get("neo4j_uri") or self.env_vars.get("NEO4J_URI")
        username = self.env_vars.get("neo4j_username") or self.env_vars.get("NEO4J_USER")
        password = self.env_vars.get("neo4j_password") or self.env_vars.get("NEO4J_PASSWORD")
        if uri and username and password:
            logger.info(f"Retrieved Neo4j credentials from .env file: {username}@{uri}")
            return {
                "uri": uri,
                "username": username,
                "password": password
            }
        
        # As a last resort, check .env file directly
        try:
            env_file = Path(".env")
            if env_file.exists():
                logger.info("Checking .env file directly for Neo4j credentials")
                env_content = env_file.read_text()
                import re
                uri_match = re.search(r'NEO4J_URI=(.+)', env_content)
                user_match = re.search(r'NEO4J_USER=(.+)', env_content)
                pass_match = re.search(r'NEO4J_PASSWORD=(.+)', env_content)
                
                if uri_match and user_match and pass_match:
                    uri = uri_match.group(1).strip()
                    username = user_match.group(1).strip()
                    password = pass_match.group(1).strip()
                    
                    if uri and username and password:
                        logger.info(f"Found Neo4j credentials directly in .env file: {username}@{uri}")
                        return {
                            "uri": uri,
                            "username": username,
                            "password": password
                        }
        except Exception as e:
            logger.warning(f"Error reading .env file directly: {e}")
        
        logger.warning("Neo4j credentials not found in any location")
        return None
        
    def save_openai_key(self, key):
        """Save OpenAI API key."""
        try:
            config = self._load_config()
            
            # Try to use keyring if available
            if self.has_keyring:
                try:
                    self.keyring.set_password(self.SERVICE_NAME, self.OPENAI_KEY, key)
                    logger.info("Saved OpenAI key to keyring")
                except Exception as e:
                    logger.warning(f"Keyring save failed, storing in config file: {e}")
                    config["openai_key"] = key
            else:
                # Save in config file if keyring not available
                config["openai_key"] = key
                logger.info("Saved OpenAI key to config file")
                    
            self._save_config(config)
            return True
        except Exception as e:
            logger.error(f"Failed to save OpenAI API key: {e}")
            return False
    
    def get_openai_key(self):
        """Get OpenAI API key."""
        config = self._load_config()
        key = None
        
        # Try to get key from environment variable first (highest priority)
        env_key = os.environ.get("OPENAI_API_KEY")
        if env_key:
            logger.info("Using OpenAI key from OS environment variables")
            return env_key
        
        # Try to get key from our loaded env vars
        env_var_key = self.env_vars.get("openai_api_key")
        if env_var_key:
            logger.info("Using OpenAI key from loaded environment variables")
            return env_var_key
        
        # Try to get key from keyring if available
        if self.has_keyring:
            try:
                key = self.keyring.get_password(self.SERVICE_NAME, self.OPENAI_KEY)
                if key:
                    logger.info("Retrieved OpenAI key from keyring")
                    return key
            except Exception as e:
                logger.warning(f"Error accessing keyring: {e}")
                # Don't retry keyring operations for this session
                global HAS_KEYRING
                HAS_KEYRING = False
                self.has_keyring = False
        
        # If not found in keyring, try config file
        if "openai_key" in config:
            key = config.get("openai_key")
            if key:
                logger.info("Using OpenAI key from config file")
                return key
        
        # As a last resort, check .env file directly
        try:
            env_file = Path(".env")
            if env_file.exists():
                logger.info("Checking .env file directly for OpenAI API key")
                env_content = env_file.read_text()
                import re
                key_match = re.search(r'OPENAI_API_KEY=(.+)', env_content)
                
                if key_match:
                    key = key_match.group(1).strip()
                    if key:
                        logger.info("Found OpenAI API key directly in .env file")
                        # Set it in the environment so it's available for future calls
                        os.environ["OPENAI_API_KEY"] = key
                        return key
        except Exception as e:
            logger.warning(f"Error reading .env file directly: {e}")
        
        logger.warning("OpenAI API key not found in any location")
        return None

    def save_github_token(self, token):
        """Save GitHub token."""
        try:
            config = self._load_config()
            
            # Try to use keyring if available
            if self.has_keyring:
                try:
                    self.keyring.set_password(self.SERVICE_NAME, self.GITHUB_KEY, token)
                    logger.info("Saved GitHub token to keyring")
                except Exception as e:
                    logger.warning(f"Keyring save failed, storing in config file: {e}")
                    config["github_token"] = token
            else:
                # Save in config file if keyring not available
                config["github_token"] = token
                logger.info("Saved GitHub token to config file")
                    
            self._save_config(config)
            return True
        except Exception as e:
            logger.error(f"Failed to save GitHub token: {e}")
            return False
    
    def get_github_token(self):
        """Get GitHub token."""
        config = self._load_config()
        token = None
        
        # First check environment variable (highest priority)
        env_token = os.environ.get("GITHUB_TOKEN")
        if env_token:
            logger.info("Using GitHub token from OS environment variables")
            return env_token
        
        # Try to get token from our loaded env vars
        env_var_token = self.env_vars.get("github_token") or self.env_vars.get("GITHUB_TOKEN")
        if env_var_token:
            logger.info("Using GitHub token from loaded environment variables")
            return env_var_token
        
        # Try to get token from keyring if available
        if self.has_keyring:
            try:
                token = self.keyring.get_password(self.SERVICE_NAME, self.GITHUB_KEY)
                if token:
                    logger.info("Retrieved GitHub token from keyring")
                    return token
            except Exception as e:
                logger.warning(f"Error accessing keyring: {e}")
                # Don't retry keyring operations for this session
                global HAS_KEYRING
                HAS_KEYRING = False
                self.has_keyring = False
        
        # If not found in keyring, try config file
        if "github_token" in config:
            token = config.get("github_token")
            if token:
                logger.info("Using GitHub token from config file")
                return token
        
        # As a last resort, check .env file directly
        try:
            env_file = Path(".env")
            if env_file.exists():
                logger.info("Checking .env file directly for GitHub token")
                env_content = env_file.read_text()
                import re
                token_match = re.search(r'GITHUB_TOKEN=(.+)', env_content)
                
                if token_match:
                    token = token_match.group(1).strip()
                    if token:
                        logger.info("Found GitHub token directly in .env file")
                        # Set it in the environment so it's available for future calls
                        os.environ["GITHUB_TOKEN"] = token
                        return token
        except Exception as e:
            logger.warning(f"Error reading .env file directly: {e}")
        
        logger.warning("GitHub token not found in any location")
        return None

    def _load_config(self):
        """Load configuration from file."""
        try:
            if self.CONFIG_FILE.exists():
                return json.loads(self.CONFIG_FILE.read_text())
            return {"huggingface_username": ""}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {"huggingface_username": ""}

    def save_aws_credentials(self, access_key, secret_key, region=None):
        """Save AWS credentials."""
        try:
            config = self._load_config()
            
            if not region:
                region = self.DEFAULT_AWS_REGION
                
            # Try to use keyring if available
            if self.has_keyring:
                try:
                    self.keyring.set_password(self.SERVICE_NAME, self.AWS_ACCESS_KEY, access_key)
                    self.keyring.set_password(self.SERVICE_NAME, self.AWS_SECRET_KEY, secret_key)
                    self.keyring.set_password(self.SERVICE_NAME, self.AWS_REGION_KEY, region)
                    logger.info("Saved AWS credentials to keyring")
                except Exception as e:
                    logger.warning(f"Keyring save failed, storing in config file: {e}")
                    config["aws_access_key"] = access_key
                    config["aws_secret_key"] = secret_key
                    config["aws_region"] = region
            else:
                # Save in config file if keyring not available
                config["aws_access_key"] = access_key
                config["aws_secret_key"] = secret_key
                config["aws_region"] = region
                logger.info("Saved AWS credentials to config file")
                    
            self._save_config(config)
            
            # Also set the environment variables
            os.environ["AWS_ACCESS_KEY_ID"] = access_key
            os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
            os.environ["AWS_REGION"] = region
            
            logger.info(f"Saved AWS credentials with region {region}")
            return True
        except Exception as e:
            logger.error(f"Failed to save AWS credentials: {e}")
            return False
            
    def get_aws_credentials(self):
        """Get AWS credentials."""
        config = self._load_config()
        access_key = None
        secret_key = None
        region = self.DEFAULT_AWS_REGION
        
        # First check environment variables (highest priority)
        env_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        env_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        env_region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        
        if env_access_key and env_secret_key:
            logger.info("Using AWS credentials from OS environment variables")
            return {
                "access_key": env_access_key,
                "secret_key": env_secret_key,
                "region": env_region or region
            }
        
        # Try to get credentials from our loaded env vars
        env_var_access_key = self.env_vars.get("aws_access_key_id") or self.env_vars.get("AWS_ACCESS_KEY_ID")
        env_var_secret_key = self.env_vars.get("aws_secret_access_key") or self.env_vars.get("AWS_SECRET_ACCESS_KEY")
        env_var_region = self.env_vars.get("aws_region") or self.env_vars.get("AWS_REGION") or self.env_vars.get("AWS_DEFAULT_REGION")
        
        if env_var_access_key and env_var_secret_key:
            logger.info("Using AWS credentials from loaded environment variables")
            return {
                "access_key": env_var_access_key,
                "secret_key": env_var_secret_key,
                "region": env_var_region or region
            }
        
        # Try to get credentials from keyring if available
        if self.has_keyring:
            try:
                access_key = self.keyring.get_password(self.SERVICE_NAME, self.AWS_ACCESS_KEY)
                secret_key = self.keyring.get_password(self.SERVICE_NAME, self.AWS_SECRET_KEY)
                keyring_region = self.keyring.get_password(self.SERVICE_NAME, self.AWS_REGION_KEY)
                
                if access_key and secret_key:
                    logger.info("Retrieved AWS credentials from keyring")
                    return {
                        "access_key": access_key,
                        "secret_key": secret_key,
                        "region": keyring_region or region
                    }
            except Exception as e:
                logger.warning(f"Error accessing keyring: {e}")
                # Don't retry keyring operations for this session
                global HAS_KEYRING
                HAS_KEYRING = False
                self.has_keyring = False
        
        # If not found in keyring, try config file
        if "aws_access_key" in config and "aws_secret_key" in config:
            access_key = config.get("aws_access_key")
            secret_key = config.get("aws_secret_key")
            config_region = config.get("aws_region")
            
            if access_key and secret_key:
                logger.info("Using AWS credentials from config file")
                return {
                    "access_key": access_key,
                    "secret_key": secret_key,
                    "region": config_region or region
                }
        
        # As a last resort, check .env file directly
        try:
            env_file = Path(".env")
            if env_file.exists():
                logger.info("Checking .env file directly for AWS credentials")
                env_content = env_file.read_text()
                import re
                
                access_key_match = re.search(r'AWS_ACCESS_KEY_ID=(.+)', env_content)
                secret_key_match = re.search(r'AWS_SECRET_ACCESS_KEY=(.+)', env_content)
                region_match = re.search(r'AWS_REGION=(.+)', env_content) or re.search(r'AWS_DEFAULT_REGION=(.+)', env_content)
                
                if access_key_match and secret_key_match:
                    access_key = access_key_match.group(1).strip()
                    secret_key = secret_key_match.group(1).strip()
                    if region_match:
                        region = region_match.group(1).strip()
                    
                    if access_key and secret_key:
                        logger.info("Found AWS credentials directly in .env file")
                        # Set them in the environment so they're available for future calls
                        os.environ["AWS_ACCESS_KEY_ID"] = access_key
                        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
                        os.environ["AWS_REGION"] = region
                        
                        return {
                            "access_key": access_key,
                            "secret_key": secret_key,
                            "region": region
                        }
        except Exception as e:
            logger.warning(f"Error reading .env file directly: {e}")
        
        logger.warning("AWS credentials not found in any location")
        return None

    def _save_config(self, config):
        """Save configuration to file with basic security measures."""
        try:
            # Create parent directory with secure permissions if needed
            self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            # Filter out sensitive data before logging
            safe_config = config.copy()
            sensitive_keys = [
                "huggingface_token", "openapi_key", "openai_key",
                "neo4j_password", "neo4j_uri", "neo4j_username", "github_token",
                "aws_access_key", "aws_secret_key"
            ]
            for key in sensitive_keys:
                if key in safe_config:
                    safe_config[key] = "*****"
                    
            logger.debug(f"Saving configuration: {json.dumps(safe_config)}")
            
            # Write config file with restricted permissions
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Try to set file permissions to owner only (0600) on Unix systems
            try:
                import stat
                os.chmod(self.CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
                logger.debug(f"Set restricted permissions on {self.CONFIG_FILE}")
            except Exception as e:
                logger.warning(f"Could not set secure permissions on config file: {e}")
                
        except Exception as e:
            logger.error(f"Failed to save config: {e}")