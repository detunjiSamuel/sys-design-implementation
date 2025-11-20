
from typing import cast
import chainlit as cl
import os
from dotenv import load_dotenv
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMessageTermination
from autogen_agentchat.teams import Swarm
from autogen_agentchat.messages import ModelClientStreamingChunkEvent
from functools import cache

load_dotenv()


class EnvConfig:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY" , "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    MAX_MESSAGE_BEFRORRE_TERMINATION: int = 5


@cache
def get_gemini_mode_client() -> OpenAIChatCompletionClient:
    return OpenAIChatCompletionClient(
        model=EnvConfig.GEMINI_MODEL,
        api_key=EnvConfig.GEMINI_API_KEY
    )


@cache
def get_agent_system_prompt(agent: str) -> str:
    path = f"prompts/{agent}_system_prompt.md"
    with open(path, "r") as f:
        return f.read()


def create_agents_for_task(model_client: OpenAIChatCompletionClient) -> Swarm:

    researcher_agent = AssistantAgent(
        name="ResearcherAgent",
        model_client=model_client,
        model_client_stream=True,
        system_message=get_agent_system_prompt("ResearcherAgent"),
        handoffs=["ArgumentAgent"]
    )

    argument_agent = AssistantAgent(
        name="ArgumentAgent",
        model_client=model_client,
        model_client_stream=True,
        system_message=get_agent_system_prompt("ArgumentAgent"),
        handoffs=["CriticAgent"]
    )

    critic_agent = AssistantAgent(
        name="CriticAgent",
        model_client=model_client,
        model_client_stream=True,
        system_message=get_agent_system_prompt("CriticAgent"),
        handoffs=["DecisionAgent"]
    )

    # final agent that makes decisions
    decision_agent = AssistantAgent(
        name="DecisionAgent",
        model_client=model_client,
        model_client_stream=True,
        system_message=get_agent_system_prompt("DecisionAgent")
    )

    termination = MaxMessageTermination(
        max_messages=EnvConfig.MAX_MESSAGE_BEFRORRE_TERMINATION) | TextMessageTermination("TERMINATE")

    team = Swarm(
        participants=[
            researcher_agent,
            argument_agent,
            critic_agent,
            decision_agent
        ],
        termination_condition=termination,
    )

    return team


@cl.on_chat_start
async def new_start() -> None:

    model_client = get_gemini_mode_client()

    team = create_agents_for_task(model_client=model_client)

    cl.user_session.set("team", team)


@cl.set_starters # type: ignore
async def set_starters() -> list[cl.Starter]:
    return [
        cl.Starter(
            label="Phone decision",
            message="Should and 80 year old use an iphone or andriod"
        )
    ]


@cl.on_message
async def message_handler(message: cl.Message) -> None:

    team = cast(Swarm, cl.user_session.get("team"))

    stream = team.run_stream(task=message.content)

    current_stream_message: cl.Message | None = None

    async for evt in stream:

        if isinstance(evt, ModelClientStreamingChunkEvent):
            if current_stream_message is None:
                source_block = "[" + evt.source + "]: "
                current_stream_message = cl.Message(content=source_block)
            await current_stream_message.stream_token(evt.content)
        elif current_stream_message is not None:
            await current_stream_message.send()
            current_stream_message = None
            import sys
            sys.exit(0)
        else:
            print("Unknown message type received in stream")
