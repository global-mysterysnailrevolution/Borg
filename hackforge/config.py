"""Centralized configuration for HackForge.

Loads API keys and settings from environment variables and .claude/settings.json.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProviderConfig:
    api_key: str = ""
    base_url: str = ""
    timeout: int = 30


@dataclass
class AirbyteCloudConfig:
    """Configuration for Airbyte Cloud API (OAuth client credentials)."""

    client_id: str = ""
    client_secret: str = ""
    base_url: str = "https://api.airbyte.com/v1"
    token_url: str = "https://api.airbyte.com/v1/applications/token"
    timeout: int = 30


@dataclass
class HackForgeConfig:
    """All provider configurations in one place."""

    project_root: Path = field(default_factory=lambda: Path.cwd())

    # Provider configs
    tavily: ProviderConfig = field(default_factory=ProviderConfig)
    reka: ProviderConfig = field(default_factory=ProviderConfig)
    fastino: ProviderConfig = field(default_factory=ProviderConfig)
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    senso: ProviderConfig = field(default_factory=ProviderConfig)
    modulate: ProviderConfig = field(default_factory=ProviderConfig)
    yutori: ProviderConfig = field(default_factory=ProviderConfig)
    airbyte: ProviderConfig = field(default_factory=ProviderConfig)
    airbyte_cloud: AirbyteCloudConfig = field(default_factory=AirbyteCloudConfig)
    render: ProviderConfig = field(default_factory=ProviderConfig)
    anthropic: ProviderConfig = field(default_factory=ProviderConfig)

    @classmethod
    def load(cls, project_root: Path | None = None) -> HackForgeConfig:
        """Load config from environment and .claude/settings.json."""
        root = project_root or Path.cwd()
        cfg = cls(project_root=root)

        # Try loading from .claude/settings.json
        settings_path = root / ".claude" / "settings.json"
        env_from_settings: dict[str, str] = {}
        if settings_path.exists():
            with open(settings_path) as f:
                settings = json.load(f)
                env_from_settings = settings.get("env", {})

        def get(key: str) -> str:
            return os.environ.get(key, env_from_settings.get(key, ""))

        # Tavily
        cfg.tavily = ProviderConfig(
            api_key=get("TAVILY_API_KEY"),
            base_url="https://api.tavily.com",
            timeout=int(get("TAVILY_TIMEOUT") or "30"),
        )

        # Reka AI
        cfg.reka = ProviderConfig(
            api_key=get("REKA_API_KEY"),
            base_url="https://api.reka.ai/v1",
            timeout=int(get("REKA_TIMEOUT") or "60"),
        )

        # Fastino
        cfg.fastino = ProviderConfig(
            api_key=get("FASTINO_API_KEY"),
            base_url="https://api.fastino.ai/v1",
            timeout=int(get("FASTINO_TIMEOUT") or "15"),
        )

        # Neo4j
        cfg.neo4j_uri = get("NEO4J_URI") or "bolt://localhost:7687"
        cfg.neo4j_user = get("NEO4J_USER") or "neo4j"
        cfg.neo4j_password = get("NEO4J_PASSWORD")

        # Senso
        cfg.senso = ProviderConfig(
            api_key=get("SENSO_API_KEY"),
            base_url="https://api.senso.ai/v1",
            timeout=int(get("SENSO_TIMEOUT") or "30"),
        )

        # Modulate
        cfg.modulate = ProviderConfig(
            api_key=get("MODULATE_API_KEY"),
            base_url="https://api.modulate.ai/v1",
            timeout=int(get("MODULATE_TIMEOUT") or "30"),
        )

        # Yutori
        cfg.yutori = ProviderConfig(
            api_key=get("YUTORI_API_KEY"),
            base_url=get("YUTORI_MCP_URL") or "",
            timeout=int(get("YUTORI_TIMEOUT") or "120"),
        )

        # Airbyte (self-hosted)
        cfg.airbyte = ProviderConfig(
            api_key=get("AIRBYTE_API_KEY"),
            base_url=get("AIRBYTE_URL") or "http://localhost:8000/api/v1",
            timeout=int(get("AIRBYTE_TIMEOUT") or "30"),
        )

        # Airbyte Cloud (OAuth client credentials)
        cfg.airbyte_cloud = AirbyteCloudConfig(
            client_id=get("AIRBYTE_CLIENT_ID"),
            client_secret=get("AIRBYTE_CLIENT_SECRET"),
            base_url=get("AIRBYTE_CLOUD_URL") or "https://api.airbyte.com/v1",
            token_url=get("AIRBYTE_TOKEN_URL")
            or "https://api.airbyte.com/v1/applications/token",
            timeout=int(get("AIRBYTE_TIMEOUT") or "30"),
        )

        # Render
        cfg.render = ProviderConfig(
            api_key=get("RENDER_API_KEY"),
            base_url="https://api.render.com/v1",
            timeout=int(get("RENDER_TIMEOUT") or "30"),
        )

        # Anthropic (for agentic integration)
        cfg.anthropic = ProviderConfig(
            api_key=get("ANTHROPIC_API_KEY"),
            base_url="https://api.anthropic.com",
            timeout=int(get("ANTHROPIC_TIMEOUT") or "120"),
        )

        return cfg

    @property
    def ai_dir(self) -> Path:
        return self.project_root / "ai"

    @property
    def memory_dir(self) -> Path:
        return self.ai_dir / "memory"

    @property
    def research_dir(self) -> Path:
        return self.ai_dir / "research"

    @property
    def vendor_dir(self) -> Path:
        return self.ai_dir / "vendor"
