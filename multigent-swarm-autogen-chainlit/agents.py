

from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMessageTermination
from autogen_agentchat.teams import Swarm

from config import EnvConfig
from helper import get_agent_system_prompt
from tools import search_with_serper_api , scrape_website


def create_agents_for_task(model_client: OpenAIChatCompletionClient) -> Swarm:

    researcher_agent = AssistantAgent(
        name="ResearcherAgent",
        model_client=model_client,
        model_client_stream=True,
        system_message=get_agent_system_prompt("ResearcherAgent") + get_agent_system_prompt("ToolRules"),
        handoffs=["ArgumentAgent"],
        tools = [search_with_serper_api , scrape_website]
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
