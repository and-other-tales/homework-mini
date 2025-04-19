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

    async def run_setup_wizard(self):
        self.query_one(ListView).append(Label("Running Setup Wizard..."))

        # Initialize credentials manager
        credentials_manager = CredentialsManager()

        # Step 1: HuggingFace credentials
        hf_username = input("Enter your HuggingFace username: ")
        hf_token = input("Enter your HuggingFace token: ")
        credentials_manager.save_huggingface_credentials(hf_username, hf_token)
        self.query_one(ListView).append(Label("HuggingFace credentials saved."))

        # Step 2: OpenAI API key
        openai_key = input("Enter your OpenAI API key: ")
        credentials_manager.save_openai_key(openai_key)
        self.query_one(ListView).append(Label("OpenAI API key saved."))

        # Step 3: Neo4j credentials
        neo4j_uri = input("Enter your Neo4j URI: ")
        neo4j_username = input("Enter your Neo4j username: ")
        neo4j_password = input("Enter your Neo4j password: ")
        credentials_manager.save_neo4j_credentials(neo4j_uri, neo4j_username, neo4j_password)
        self.query_one(ListView).append(Label("Neo4j credentials saved."))

        # Step 4: GitHub token
        github_token = input("Enter your GitHub token: ")
        credentials_manager.save_github_token(github_token)
        self.query_one(ListView).append(Label("GitHub token saved."))

        self.query_one(ListView).append(Label("Setup Wizard completed."))

    async def api_credentials(self):
        self.query_one(ListView).append(Label("Managing API Credentials..."))

        # Initialize credentials manager
        credentials_manager = CredentialsManager()

        # HuggingFace credentials
        hf_username, hf_token = credentials_manager.get_huggingface_credentials()
        self.query_one(ListView).append(Label(f"HuggingFace Username: {hf_username}"))
        self.query_one(ListView).append(Label(f"HuggingFace Token: {'*' * len(hf_token) if hf_token else 'Not Set'}"))

        # OpenAI API key
        openai_key = credentials_manager.get_openai_key()
        self.query_one(ListView).append(Label(f"OpenAI API Key: {'*' * len(openai_key) if openai_key else 'Not Set'}"))

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
        credentials_manager = CredentialsManager()

        # Server port
        server_port = credentials_manager.get_server_port()
        self.query_one(ListView).append(Label(f"Current Server Port: {server_port}"))
        new_port = input("Enter new server port (or press Enter to keep current): ")
        if new_port:
            credentials_manager.save_server_port(new_port)
            self.query_one(ListView).append(Label(f"Server port updated to: {new_port}"))

        # Temporary directory
        temp_dir = credentials_manager.get_temp_dir()
        self.query_one(ListView).append(Label(f"Current Temporary Directory: {temp_dir}"))
        new_temp_dir = input("Enter new temporary directory (or press Enter to keep current): ")
        if new_temp_dir:
            credentials_manager.save_temp_dir(new_temp_dir)
            self.query_one(ListView).append(Label(f"Temporary directory updated to: {new_temp_dir}"))

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
