"""Run script for launching the unified Antigravity Core & ChatGPT MCP Bridge server."""

import os
from app.config import get_settings
from main import run_unified_bridge

if __name__ == "__main__":
    settings = get_settings()
    port = int(os.environ.get("PORT", settings.PORT))
    run_unified_bridge(host=settings.HOST, port=port)
