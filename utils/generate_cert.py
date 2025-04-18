#!/usr/bin/env python3
"""
Utility script to generate self-signed SSL certificates for the API server.

This script generates a self-signed SSL certificate and private key that can be used
for HTTPS connections to the API server in development environments.

Usage:
    python generate_cert.py [--output-dir DIR] [--days DAYS] [--hostname HOSTNAME]

Options:
    --output-dir DIR     Directory where certificate files will be saved (default: ./certs)
    --days DAYS          Validity period in days (default: 365)
    --hostname HOSTNAME  Hostname to use in certificate (default: localhost)
"""

import argparse
import os
import datetime
import subprocess
import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_self_signed_cert(output_dir="./certs", days=365, hostname="localhost"):
    """
    Generate a self-signed SSL certificate using OpenSSL.
    
    Args:
        output_dir (str): Directory to save the certificate files
        days (int): Validity period in days
        hostname (str): Hostname to use in the certificate
        
    Returns:
        tuple: Paths to the certificate and key files
    """
    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Define output file paths
    cert_path = os.path.join(output_dir, f"{hostname}.crt")
    key_path = os.path.join(output_dir, f"{hostname}.key")
    
    # Check if OpenSSL is available
    try:
        subprocess.run(["openssl", "version"], check=True, capture_output=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error("OpenSSL not found. Please install OpenSSL and try again.")
        sys.exit(1)
    
    # Generate private key and certificate
    try:
        # Create configuration with Subject Alternative Name
        config_path = os.path.join(output_dir, "openssl.cnf")
        with open(config_path, "w") as f:
            f.write(f"""[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
C = US
ST = California
L = San Francisco
O = Development
OU = API Server
CN = {hostname}

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = {hostname}
DNS.2 = localhost
IP.1 = 127.0.0.1
IP.2 = ::1
""")
        
        # Generate RSA private key
        logger.info(f"Generating private key: {key_path}")
        subprocess.run([
            "openssl", "genrsa",
            "-out", key_path,
            "2048"
        ], check=True)
        
        # Generate self-signed certificate
        logger.info(f"Generating self-signed certificate: {cert_path}")
        subprocess.run([
            "openssl", "req",
            "-new",
            "-x509",
            "-key", key_path,
            "-out", cert_path,
            "-days", str(days),
            "-config", config_path
        ], check=True)
        
        # Set appropriate permissions
        os.chmod(key_path, 0o600)  # Read/write for owner only
        os.chmod(cert_path, 0o644)  # Read for everyone, write for owner
        
        # Remove temporary config file
        os.remove(config_path)
        
        logger.info(f"Self-signed certificate generated successfully.")
        logger.info(f"Certificate file: {cert_path}")
        logger.info(f"Private key file: {key_path}")
        
        return cert_path, key_path
    
    except subprocess.SubprocessError as e:
        logger.error(f"Error generating certificate: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Generate self-signed SSL certificate for development")
    parser.add_argument("--output-dir", default="./certs", help="Output directory for certificate files")
    parser.add_argument("--days", type=int, default=365, help="Validity period in days")
    parser.add_argument("--hostname", default="localhost", help="Hostname for the certificate")
    
    args = parser.parse_args()
    
    # Resolve output directory to absolute path
    output_dir = os.path.abspath(args.output_dir)
    
    # Generate certificate
    cert_path, key_path = generate_self_signed_cert(output_dir, args.days, args.hostname)
    
    logger.info("\nTo use this certificate with the API server, update your configuration or start the server with:")
    logger.info(f"python main.py --use-https --cert-file {cert_path} --key-file {key_path}")

if __name__ == "__main__":
    main()