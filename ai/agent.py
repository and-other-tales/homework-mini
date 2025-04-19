"""React Agent implementation using AWS Bedrock with LangChain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Annotated, Callable, TypedDict, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langchain_aws import ChatBedrockConverse

from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

# Set up logging
import logging
logger = logging.getLogger(__name__)


@dataclass
class Configuration:
    """Configuration for the agent."""
    
    # The system prompt template
    system_prompt: str = field(
        default="""You are a helpful AI assistant. 
        
System time: {system_time}"""
    )
    
    # The model ID to use
    model_id: str = field(
        default="anthropic.claude-3-5-sonnet-20240620-v1:0"
    )
    
    # AWS region
    region: str = field(
        default="us-east-1"
    )
    
    # Temperature for text generation
    temperature: float = field(
        default=0.7
    )
    
    # Maximum tokens to generate
    max_tokens: int = field(
        default=2000
    )
    
    @classmethod
    def from_runnable_config(cls, config: Optional[RunnableConfig] = None) -> Configuration:
        """Create a Configuration instance from a RunnableConfig."""
        config = config or {}
        configurable = config.get("configurable", {})
        
        return cls(
            system_prompt=configurable.get("system_prompt", cls.system_prompt),
            model_id=configurable.get("model_id", cls.model_id),
            region=configurable.get("region", cls.region),
            temperature=configurable.get("temperature", cls.temperature),
            max_tokens=configurable.get("max_tokens", cls.max_tokens),
        )


@dataclass
class InputState:
    """Input state for the agent."""
    
    messages: List[BaseMessage] = field(default_factory=list)


@dataclass
class State(InputState):
    """The complete state of the agent."""
    
    # Flag to indicate if this is the last step (prevents infinite loops)
    is_last_step: bool = field(default=False)


# Tools for the agent
default_tools = []


@tool
def search_web(query: str) -> str:
    """Search the web for information about a topic."""
    # This is a placeholder - in production, would connect to a search API
    return f"Found results for: {query}. This is a placeholder for real search results."


default_tools.append(search_web)


@tool
def get_current_time() -> str:
    """Get the current time and date."""
    now = datetime.now()
    return f"Current time is: {now.strftime('%Y-%m-%d %H:%M:%S')}"


default_tools.append(get_current_time)


class AgentError(Exception):
    """Exception raised for agent errors."""
    pass


async def call_model(state: State, config: RunnableConfig) -> Dict[str, List[AIMessage]]:
    """Call the model to get the next action."""
    configuration = Configuration.from_runnable_config(config)
    
    try:
        # Initialize the model with tool binding
        model = ChatBedrockConverse(
            model_id=configuration.model_id,
            region_name=configuration.region,
            temperature=configuration.temperature,
            max_tokens=configuration.max_tokens,
        )
        
        model_with_tools = model.bind_tools(default_tools)
        
        # Format the system prompt
        system_message = configuration.system_prompt.format(
            system_time=datetime.now(tz=timezone.utc).isoformat()
        )
        
        # Get the model's response
        response = await model_with_tools.ainvoke(
            [SystemMessage(content=system_message)] + state.messages,
            config=config
        )
        
        # Handle the case when it's the last step and the model still wants to use a tool
        if state.is_last_step and hasattr(response, "tool_calls") and response.tool_calls:
            return {
                "messages": [AIMessage(content="I could not find a complete answer in the allowed number of steps.")]
            }
        
        # Return the model's response
        return {"messages": [response]}
        
    except Exception as e:
        logger.error(f"Error in call_model: {e}")
        # Return a failure message
        return {
            "messages": [AIMessage(content=f"I encountered an error: {str(e)}")]
        }


def route_model_output(state: State) -> str:
    """Route model output to the next node."""
    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage):
        raise AgentError(f"Expected AIMessage in output, got {type(last_message).__name__}")
    
    # If the message has tool_calls, route to the tools node
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    # Otherwise, we're done
    return "__end__"


def create_agent(tools: Optional[List[Callable]] = None):
    """Create a React agent with the specified tools."""
    # Use the provided tools or the default ones
    agent_tools = tools or default_tools
    
    # Create the state graph
    builder = StateGraph(State, input=InputState)
    
    # Add the nodes
    builder.add_node("call_model", call_model)
    builder.add_node("tools", ToolNode(agent_tools))
    
    # Set the entry point
    builder.add_edge("__start__", "call_model")
    
    # Add conditional edges
    builder.add_conditional_edges("call_model", route_model_output)
    
    # Add the cycle back to call_model
    builder.add_edge("tools", "call_model")
    
    # Compile the graph
    agent = builder.compile()
    agent.name = "ReAct Agent"
    
    return agent


async def run_agent(query: str, tools: Optional[List[Callable]] = None) -> Dict[str, Any]:
    """Run the agent with a query."""
    try:
        # Create the agent
        agent = create_agent(tools)
        
        # Set up the input state
        input_state = InputState(messages=[HumanMessage(content=query)])
        
        # Run the agent
        result = await agent.ainvoke(input_state)
        
        # Extract the relevant message
        final_message = None
        for message in reversed(result.messages):
            if isinstance(message, AIMessage) and not (hasattr(message, "tool_calls") and message.tool_calls):
                final_message = message
                break
        
        if not final_message:
            final_message = result.messages[-1]
        
        # Return the result
        return {
            "success": True,
            "response": final_message.content,
            "messages": result.messages
        }
        
    except Exception as e:
        logger.error(f"Error running agent: {e}")
        return {
            "success": False,
            "response": f"Error: {str(e)}",
            "messages": []
        }