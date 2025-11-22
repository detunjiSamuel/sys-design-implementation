from functools import cache


@cache
def get_agent_system_prompt(agent: str) -> str:
    path = f"prompts/{agent}_system_prompt.md"
    with open(path, "r") as f:
        return f.read()