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

class TUIApp(App):
    CSS_PATH = "tui_app.css"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Container(
            Horizontal(
                Vertical(
                    Label("AI Assistant"),
                    TextInput(placeholder="Enter your query here..."),
                    Button("Submit", id="submit_button"),
                    id="left_panel",
                ),
                Vertical(
                    Panel(Markdown("## AI Assistant Responses")),
                    ListView(id="response_list"),
                    id="right_panel",
                ),
                id="main_container",
            )
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit_button":
            query = self.query_one(TextInput).value
            response = await self.get_ai_response(query)
            self.query_one(ListView).append(Label(response))

    async def get_ai_response(self, query: str) -> str:
        # Placeholder for AI response logic
        return f"Response to: {query}"

if __name__ == "__main__":
    TUIApp().run()
