from agents.runner import run_agent

async def run_travel_agent(**kw):
    return await run_agent("travel", **kw)

__all__ = ["run_travel_agent"]
