from typing import Dict, List, Optional
from app.config import get_settings
from app.providers.base import BaseAgentProvider
from app.providers.antigravity_real import AntigravityRealAgentProvider
from app.providers.antigravity_sdk import AntigravitySDKProvider
from app.providers.antigravity_cli import AntigravityCliProvider
from app.providers.simulated import SimulatedAgentProvider
from app.providers.extensions import ClaudeCodeProvider, GeminiCliProvider


class ProviderRegistry:
    """Central registry for all agent implementation providers."""

    def __init__(self):
        self._providers: Dict[str, BaseAgentProvider] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register(AntigravityRealAgentProvider())
        self.register(AntigravitySDKProvider())
        self.register(AntigravityCliProvider())
        self.register(SimulatedAgentProvider())
        self.register(ClaudeCodeProvider())
        self.register(GeminiCliProvider())

    def register(self, provider: BaseAgentProvider):
        self._providers[provider.provider_id] = provider

    def get_provider(self, provider_id: Optional[str] = None) -> BaseAgentProvider:
        settings = get_settings()
        target_id = provider_id or settings.DEFAULT_AGENT_PROVIDER

        if target_id in self._providers:
            return self._providers[target_id]

        # Prioritize real local Antigravity Agent
        if target_id in ("antigravity", "antigravity_real"):
            return self._providers.get("antigravity_real") or self._providers.get("antigravity_sdk") or self._providers["simulated"]

        # Default fallback
        return self._providers.get("simulated", next(iter(self._providers.values())))

    def list_providers(self) -> List[Dict[str, str]]:
        return [
            {
                "provider_id": p.provider_id,
                "display_name": p.display_name,
            }
            for p in self._providers.values()
        ]


# Singleton instance
provider_registry = ProviderRegistry()
