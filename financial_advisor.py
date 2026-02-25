from agents.runner import run_agent

async def run_financial_agent(**kw):
    return await run_agent("financial", **kw)

__all__ = ["run_financial_agent"]
