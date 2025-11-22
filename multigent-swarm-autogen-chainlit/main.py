
from agents import create_agents_for_task
from functools import cache
from autogen_agentchat.messages import ModelClientStreamingChunkEvent, ToolCallRequestEvent
from autogen_agentchat.teams import Swarm
from autogen_agentchat.base import TaskResult

from autogen_ext.models.openai import OpenAIChatCompletionClient
import chainlit as cl
from typing import cast
from config import EnvConfig


@cache
def get_gemini_mode_client() -> OpenAIChatCompletionClient:
    return OpenAIChatCompletionClient(
        model=EnvConfig.GEMINI_MODEL,
        api_key=EnvConfig.GEMINI_API_KEY
    )


@cl.on_chat_start
async def new_start() -> None:

    model_client = get_gemini_mode_client()

    team = create_agents_for_task(model_client=model_client)

    cl.user_session.set("team", team)


@cl.set_starters  # type: ignore
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
            # LLM's send complete message right after streaming chunks
            await current_stream_message.send()
            current_stream_message = None
        elif isinstance(evt, ToolCallRequestEvent):
            tool_call_message = f"[{evt.source}] is calling tools \n"
            tool_call_message += "\n".join(
                [f"{tool.name} : {tool.arguments}" for tool in evt.content])
            await cl.Message(content=tool_call_message, author=evt.source).send()
        elif isinstance(evt, TaskResult):
            final_message = "Task Result:\n"
            if evt.stop_reason:
                final_message += f"Stopped because: {evt.stop_reason}\n"
            await cl.Message(content=final_message).send()
        else:
            continue
            unknown_message = f"Unknown event type: {type(evt)} \n"
            unknown_message += f" with content: {evt}"
            await cl.Message(content=unknown_message).send()
