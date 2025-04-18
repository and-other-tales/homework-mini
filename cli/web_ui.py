import logging
from api.server import start_server_with_ui, stop_server, is_server_running, get_server_info
from config.credentials_manager import CredentialsManager

logger = logging.getLogger(__name__)

def web_ui():
    print("\n----- Launch Web UI -----")
    
    # Check if server is already running
    if is_server_running():
        server_info = get_server_info()
        print(f"Server is already running.")
        
        # Ask if user wants to re-launch with web UI
        relaunch = input("Do you want to stop the current server and relaunch with web UI? (y/n): ")
        if relaunch.lower() == 'y':
            print("Stopping current server...")
            stop_server()
            
            # Choose HTTP or HTTPS
            print("\nConnection Security:")
            print("1. HTTP (standard, no security)")
            print("2. HTTPS with self-signed certificates")
            
            security_choice = input("Enter choice (1-2): ")
            use_https = security_choice == "2"
            
            if use_https:
                # Ask about certificate generation
                print("\nCertificate Options:")
                print("1. Generate new self-signed certificates")
                print("2. Use existing certificates")
                
                cert_choice = input("Enter choice (1-2): ")
                generate_cert = cert_choice == "1"
                
                cert_file = None
                key_file = None
                
                # If using existing certificates, get file paths
                if not generate_cert:
                    cert_file = input("Enter path to certificate file: ")
                    key_file = input("Enter path to key file: ")
            else:
                # HTTP mode
                use_https = False
                generate_cert = False
                cert_file = None
                key_file = None
            
            # Launch web UI with selected options
            if run_web_ui(
                use_https=use_https,
                cert_file=cert_file,
                key_file=key_file,
                generate_cert=generate_cert
            ):
                # Return to menu
                return
            else:
                print("Failed to start web UI")
        else:
            print("Continuing with current server")
    else:
        # Choose HTTP or HTTPS
        print("\nConnection Security:")
        print("1. HTTP (standard, no security)")
        print("2. HTTPS with self-signed certificates")
        
        security_choice = input("Enter choice (1-2): ")
        use_https = security_choice == "2"
        
        if use_https:
            # Ask about certificate generation
            print("\nCertificate Options:")
            print("1. Generate new self-signed certificates")
            print("2. Use existing certificates")
            
            cert_choice = input("Enter choice (1-2): ")
            generate_cert = cert_choice == "1"
            
            cert_file = None
            key_file = None
            
            # If using existing certificates, get file paths
            if not generate_cert:
                cert_file = input("Enter path to certificate file: ")
                key_file = input("Enter path to key file: ")
        else:
            # HTTP mode
            use_https = False
            generate_cert = False
            cert_file = None
            key_file = None
        
        # Launch web UI with selected options
        if run_web_ui(
            use_https=use_https,
            cert_file=cert_file,
            key_file=key_file,
            generate_cert=generate_cert
        ):
            # Ask if user wants to continue in CLI mode
            cli_continue = input("\nWeb UI is now running. Do you want to continue in CLI mode? (y/n): ")
            if cli_continue.lower() != 'y':
                print("Exiting CLI mode. The web UI will continue running in the background.")
                return
        else:
            print("Failed to start web UI")

def run_web_ui(use_https=False, cert_file=None, key_file=None, generate_cert=False):
    """Run the web UI interface with optional HTTPS support.
    
    Args:
        use_https: Whether to use HTTPS
        cert_file: Path to SSL certificate file
        key_file: Path to SSL key file
        generate_cert: Whether to generate self-signed certificates
    """
    
    # Initialize credentials and other required components
    credentials_manager = CredentialsManager()
    port = credentials_manager.get_server_port()
    
    # Get OpenAPI key
    api_key = credentials_manager.get_openapi_key()
    
    if not api_key:
        print("\nOpenAPI key not configured. Setting temporary key for this session.")
        api_key = "temporary_key_" + str(time.time())
    
    # Handle HTTPS setup
    if use_https:
        if generate_cert:
            print("\nGenerating self-signed SSL certificates...")
            try:
                from utils.generate_cert import generate_self_signed_cert
                
                # Create certs directory in project root
                certs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "certs")
                hostname = "localhost"
                
                # Generate certificates
                cert_path, key_path = generate_self_signed_cert(
                    output_dir=certs_dir,
                    days=365,
                    hostname=hostname
                )
                
                # Use the generated certificates
                cert_file = cert_path
                key_file = key_path
                
                print(f"Self-signed certificates generated successfully.")
                print(f"Certificate file: {cert_file}")
                print(f"Key file: {key_file}")
                
            except Exception as e:
                print(f"Error generating self-signed certificates: {e}")
                print("Falling back to HTTP.")
                use_https = False
        
        # Verify certificate and key files
        if use_https and (not cert_file or not key_file):
            print("\nHTTPS requested but certificate or key file not provided.")
            print("You can specify --cert-file and --key-file, or use --generate-cert to create self-signed certificates.")
            print("Falling back to HTTP.")
            use_https = False
        
        if use_https and (not os.path.exists(cert_file) or not os.path.exists(key_file)):
            print(f"\nCertificate file ({cert_file}) or key file ({key_file}) not found.")
            print("Falling back to HTTP.")
            use_https = False
    
    # Start server with UI enabled (no static/templates needed)
    protocol = "HTTPS" if use_https else "HTTP"
    print(f"\nStarting web UI on port {port} with {protocol}...")
    
    server_info = start_server_with_ui(
        api_key=api_key, 
        port=port,
        use_https=use_https,
        cert_file=cert_file,
        key_file=key_file
    )
    
    if server_info:
        print(f"Backend API running at: {server_info['web_ui_url']}")
        print(f"API Documentation: {server_info['api_docs_url']}")
        print(f"Frontend should be started separately with 'cd frontend && npm run dev'")
        
        if use_https:
            print("\nNote: Since you're using self-signed certificates, you may need to:")
            print("1. Accept the security warning in your browser when accessing the API")
            print("2. Configure your frontend to trust this certificate or disable certificate validation for development")
        
        return True
    else:
        print("Failed to start web UI")
        return False
