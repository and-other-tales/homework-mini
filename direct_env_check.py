#!/usr/bin/env python3

import os
from pathlib import Path
import re

def main():
    """Directly check .env file for OpenAI API key."""
    print("Checking for OpenAI API key in .env file...")
    
    # Check .env file directly
    env_paths = [
        Path(".env"),
        Path("../.env"),
        Path(os.path.join(os.path.dirname(__file__), "../.env")),
    ]
    
    env_key_found = False
    for env_path in env_paths:
        if env_path.exists():
            print(f"Found .env file at {env_path.absolute()}")
            try:
                env_content = env_path.read_text()
                key_match = re.search(r'OPENAI_API_KEY=(.+)', env_content)
                
                if key_match:
                    env_key = key_match.group(1).strip()
                    masked_key = env_key[:4] + "..." + env_key[-4:] if len(env_key) > 8 else "***"
                    print(f"Found OpenAI API key in .env file: {masked_key}")
                    
                    # Try setting in environment
                    os.environ["OPENAI_API_KEY"] = env_key
                    print("Set API key in environment for this process")
                    
                    env_key_found = True
                    break
                else:
                    print(f"No OpenAI API key pattern found in {env_path}")
                    # Show some content for debugging (without showing any secrets)
                    lines = env_content.split("\n")
                    safe_lines = []
                    for line in lines:
                        if line.strip() and not any(secret in line.lower() for secret in ["key", "token", "password", "secret"]):
                            safe_lines.append(line)
                        elif line.strip():
                            key_name = line.split("=")[0] if "=" in line else line
                            safe_lines.append(f"{key_name}=*****")
                    print(f"Content structure preview: {len(lines)} lines total")
                    print("\n".join(safe_lines[:5]) + ("\n..." if len(safe_lines) > 5 else ""))
            except Exception as e:
                print(f"Error reading {env_path}: {e}")
        else:
            print(f"No .env file found at {env_path.absolute()}")
    
    if not env_key_found:
        print("OpenAI API key not found in any .env file")
    
    # Check if the key is in environment now
    if "OPENAI_API_KEY" in os.environ:
        env_key = os.environ["OPENAI_API_KEY"]
        masked_key = env_key[:4] + "..." + env_key[-4:] if len(env_key) > 8 else "***"
        print(f"OpenAI API key is now in environment: {masked_key}")
    else:
        print("OpenAI API key is not in environment")

if __name__ == "__main__":
    main()