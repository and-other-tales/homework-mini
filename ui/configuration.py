import logging
from config.credentials_manager import CredentialsManager
from huggingface.dataset_manager import DatasetManager
from neo4j.graph_store import GraphStore
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header,
    Footer,
    Button,
    TextInput,
    Label,
    Panel,
    Markdown,
    Status,
    ListView,
    Checkbox,
    Frame,
)

logger = logging.getLogger(__name__)

class ConfigurationApp(App):
    CSS_PATH = "tui_app.css"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Container(
            Horizontal(
                Vertical(
                    Label("Configuration Menu"),
                    Button("Setup Wizard", id="setup_wizard"),
                    Button("API Credentials", id="api_credentials"),
                    Button("Server & Dataset Configuration", id="server_config"),
                    Button("Knowledge Graph Configuration", id="kg_config"),
                    Button("Return to Main Menu", id="return_main"),
                    id="left_panel",
                ),
                Vertical(
                    Panel(Markdown("## Configuration Options")),
                    ListView(id="config_list"),
                    Container(
                        TextInput(placeholder="Enter value here...", id="config_input"),
                        Button("Save", id="save_config"),
                        id="input_container",
                        classes="hide"
                    ),
                    id="right_panel",
                ),
                id="main_container",
            )
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "setup_wizard":
            await self.run_setup_wizard()
        elif event.button.id == "api_credentials":
            await self.api_credentials()
        elif event.button.id == "server_config":
            await self.server_config()
        elif event.button.id == "kg_config":
            await self.kg_config()
        elif event.button.id == "return_main":
            self.exit()
        elif event.button.id == "save_config":
            await self._process_config_input()

    # Track current configuration state
    current_config = None
    current_config_step = None
    credentials_manager = None
    config_steps = [
        "hf_username", "hf_token", "aws_access_key", "aws_secret_key", "aws_region",
        "neo4j_uri", "neo4j_username", "neo4j_password", "github_token"
    ]
    config_values = {}
    
    async def run_setup_wizard(self):
        self.query_one(ListView).append(Label("Running Setup Wizard..."))
        self.query_one(ListView).append(Label("Enter your credentials in the fields below:"))
        
        # Initialize credentials manager
        self.credentials_manager = CredentialsManager()
        
        # Start the wizard
        self.current_config = "setup_wizard"
        self.current_config_step = 0
        self.config_values = {}
        
        # Setup the first step
        await self._show_config_prompt("HuggingFace username")
    
    async def _show_config_prompt(self, prompt_text):
        """Show a configuration prompt for the current step."""
        input_container = self.query_one("#input_container")
        input_container.remove_class("hide")
        
        input_field = self.query_one("#config_input")
        input_field.placeholder = f"Enter {prompt_text}..."
        input_field.value = ""
        input_field.focus()
    
    async def _process_config_input(self):
        """Process the current configuration input."""
        input_field = self.query_one("#config_input")
        value = input_field.value
        
        if self.current_config == "setup_wizard":
            step_name = self.config_steps[self.current_config_step]
            self.config_values[step_name] = value
            
            # Show the entered value (mask sensitive values)
            if step_name in ["hf_token", "openai_key", "neo4j_password", "github_token"]:
                display_value = "*" * len(value) if value else "(empty)"
            else:
                display_value = value
                
            self.query_one(ListView).append(Label(f"Set {step_name}: {display_value}"))
            
            # Move to next step
            self.current_config_step += 1
            
            # If we have more steps, show the next prompt
            if self.current_config_step < len(self.config_steps):
                step_name = self.config_steps[self.current_config_step]
                prompt_text = step_name.replace("_", " ").title()
                await self._show_config_prompt(prompt_text)
            else:
                # We're done with the wizard, save all values
                await self._save_wizard_config()
        elif self.current_config == "server_config":
            if self.current_config_step == 0:  # Server port
                self.credentials_manager.save_server_port(value)
                self.query_one(ListView).append(Label(f"Server port updated to: {value}"))
                
                # Move to next step (temp directory)
                self.current_config_step += 1
                await self._show_config_prompt("temporary directory path")
            elif self.current_config_step == 1:  # Temp directory
                self.credentials_manager.save_temp_dir(value)
                self.query_one(ListView).append(Label(f"Temporary directory updated to: {value}"))
                
                # We're done
                input_container = self.query_one("#input_container")
                input_container.add_class("hide")
                self.current_config = None
                self.query_one(ListView).append(Label("Server configuration completed."))
    
    async def _save_wizard_config(self):
        """Save all wizard configuration values."""
        input_container = self.query_one("#input_container")
        input_container.add_class("hide")
        
        try:
            # Save HuggingFace credentials
            self.credentials_manager.save_huggingface_credentials(
                self.config_values.get("hf_username", ""),
                self.config_values.get("hf_token", "")
            )
            self.query_one(ListView).append(Label("HuggingFace credentials saved."))
            
            # Save AWS credentials
            self.credentials_manager.save_aws_credentials(
                self.config_values.get("aws_access_key", ""),
                self.config_values.get("aws_secret_key", ""),
                self.config_values.get("aws_region", "us-east-1")
            )
            self.query_one(ListView).append(Label("AWS credentials saved."))
            
            # Save Neo4j credentials
            self.credentials_manager.save_neo4j_credentials(
                self.config_values.get("neo4j_uri", ""),
                self.config_values.get("neo4j_username", ""),
                self.config_values.get("neo4j_password", "")
            )
            self.query_one(ListView).append(Label("Neo4j credentials saved."))
            
            # Save GitHub token
            self.credentials_manager.save_github_token(self.config_values.get("github_token", ""))
            self.query_one(ListView).append(Label("GitHub token saved."))
            
            self.query_one(ListView).append(Label("Setup Wizard completed."))
        except Exception as e:
            self.query_one(ListView).append(Label(f"Error saving configuration: {e}"))
        
        # Reset wizard state
        self.current_config = None

    async def api_credentials(self):
        self.query_one(ListView).append(Label("Managing API Credentials..."))

        # Initialize credentials manager
        credentials_manager = CredentialsManager()

        # HuggingFace credentials
        hf_username, hf_token = credentials_manager.get_huggingface_credentials()
        self.query_one(ListView).append(Label(f"HuggingFace Username: {hf_username}"))
        self.query_one(ListView).append(Label(f"HuggingFace Token: {'*' * len(hf_token) if hf_token else 'Not Set'}"))

        # AWS credentials
        aws_credentials = credentials_manager.get_aws_credentials()
        if aws_credentials:
            self.query_one(ListView).append(Label(f"AWS Access Key: {'*' * 8 + aws_credentials.get('access_key', '')[-4:] if aws_credentials.get('access_key') else 'Not Set'}"))
            self.query_one(ListView).append(Label(f"AWS Secret Key: {'*' * 12 if aws_credentials.get('secret_key') else 'Not Set'}"))
            self.query_one(ListView).append(Label(f"AWS Region: {aws_credentials.get('region', 'us-east-1')}"))
        else:
            self.query_one(ListView).append(Label("AWS Credentials: Not Set"))
        
        # Neo4j credentials
        neo4j_credentials = credentials_manager.get_neo4j_credentials()
        if neo4j_credentials:
            self.query_one(ListView).append(Label(f"Neo4j URI: {neo4j_credentials.get('uri', 'Not Set')}"))
            self.query_one(ListView).append(Label(f"Neo4j Username: {neo4j_credentials.get('username', 'Not Set')}"))
            self.query_one(ListView).append(Label(f"Neo4j Password: {'*' * len(neo4j_credentials.get('password', '')) if neo4j_credentials.get('password') else 'Not Set'}"))
        else:
            self.query_one(ListView).append(Label("Neo4j Credentials: Not Set"))

        # GitHub token
        github_token = credentials_manager.get_github_token()
        self.query_one(ListView).append(Label(f"GitHub Token: {'*' * len(github_token) if github_token else 'Not Set'}"))

    async def server_config(self):
        self.query_one(ListView).append(Label("Configuring Server & Datasets..."))

        # Initialize credentials manager
        self.credentials_manager = CredentialsManager()

        # Server port
        server_port = self.credentials_manager.get_server_port()
        self.query_one(ListView).append(Label(f"Current Server Port: {server_port}"))
        
        # Temporary directory
        temp_dir = self.credentials_manager.get_temp_dir()
        self.query_one(ListView).append(Label(f"Current Temporary Directory: {temp_dir}"))
        
        # Setup for server config input
        self.current_config = "server_config"
        self.current_config_step = 0
        
        # Prompt for server port
        await self._show_config_prompt(f"new server port (current: {server_port})")

    async def kg_config(self):
        self.query_one(ListView).append(Label("Configuring Knowledge Graph..."))

        # Initialize graph store
        graph_store = GraphStore()

        # Test connection
        if graph_store.test_connection():
            self.query_one(ListView).append(Label("Connected to Neo4j successfully."))
        else:
            self.query_one(ListView).append(Label("Failed to connect to Neo4j."))

        # Initialize schema
        if graph_store.initialize_schema():
            self.query_one(ListView).append(Label("Knowledge graph schema initialized."))
        else:
            self.query_one(ListView).append(Label("Failed to initialize knowledge graph schema."))

        # List graphs
        graphs = graph_store.list_graphs()
        if graphs:
            self.query_one(ListView).append(Label("Available Knowledge Graphs:"))
            for graph in graphs:
                self.query_one(ListView).append(Label(f"- {graph['name']} (Created: {graph['created_at']}, Updated: {graph['updated_at']})"))
        else:
            self.query_one(ListView).append(Label("No knowledge graphs found."))

def configuration():
    app = ConfigurationApp()
    app.run()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    configuration()
