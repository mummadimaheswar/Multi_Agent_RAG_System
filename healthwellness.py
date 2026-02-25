from agents.runner import run_agent

async def run_health_agent(**kw):
    return await run_agent("health", **kw)

__all__ = ["run_health_agent"]
