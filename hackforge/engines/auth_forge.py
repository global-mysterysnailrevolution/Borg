"""Auth Forge Engine — Agentic Authentication and API Key Acquisition.

Automatically navigates vendor signup/developer-portal pages to acquire API
keys, storing the credentials in ``.claude/settings.json`` for immediate use
by the harness.

Pipeline per tool:
  find signup page (Tavily) → navigate & fill forms (Yutori browse)
  → extract API key from dashboard → store in settings.json → return AuthResult
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from hackforge.config import HackForgeConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class BrowseResult(BaseModel):
    """Result returned by a Yutori browse action."""

    url: str
    page_text: str = ""
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: str | None = None


class AuthResult(BaseModel):
    """Full result of an agentic auth flow for a single tool."""

    tool_name: str
    api_key: str = ""
    auth_type: str = "api_key"  # "api_key" | "oauth" | "bearer" | "unknown"
    config_path: str = ""
    setup_complete: bool = False
    manual_steps: list[str] = Field(default_factory=list)
    dashboard_url: str = ""
    docs_url: str = ""
    error: str | None = None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class AuthForgeEngine:
    """Agentically navigates vendor signup pages to acquire API keys.

    Uses:
    - **Tavily** to search for developer/API signup and documentation pages.
    - **Yutori browse** to navigate sign-up flows and fill in form fields
      (email, password, account details) automatically.
    - Local file I/O to persist keys into ``.claude/settings.json``.

    Usage::

        config = HackForgeConfig.load()
        engine = AuthForgeEngine(config)
        result = await engine.setup_tool("Tavily", "https://tavily.com")
        if result.setup_complete:
            print(f"API key: {result.api_key}")
        else:
            for step in result.manual_steps:
                print(f"Manual step needed: {step}")
    """

    def __init__(self, config: HackForgeConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def setup_tool(self, tool_name: str, vendor_url: str) -> AuthResult:
        """Full auth flow: find signup → navigate → get API key → configure.

        Args:
            tool_name: Human-readable name of the tool (e.g. ``"Tavily"``).
            vendor_url: The vendor's primary website URL.

        Returns:
            An :class:`AuthResult` with the extracted API key (if successful)
            and any manual steps required.
        """
        logger.info("AuthForge: setting up %s (%s)", tool_name, vendor_url)
        result = AuthResult(tool_name=tool_name)

        try:
            # Step 1: find the developer/API signup page
            signup_url = await self._find_signup_page(vendor_url)
            if not signup_url:
                result.manual_steps.append(
                    f"Could not find signup page for {tool_name}. "
                    f"Navigate manually to {vendor_url} and sign up."
                )
                result.error = "Signup page not found via Tavily search."
                return result

            logger.info("AuthForge: found signup page %s", signup_url)

            # Step 2: navigate the signup form via Yutori
            user_email = self._get_user_email()
            browse_result = await self._navigate_signup(signup_url, user_email)

            if not browse_result.success:
                result.manual_steps.append(
                    f"Automated signup failed. Please navigate to {signup_url} "
                    f"and complete registration manually using: {user_email}"
                )
                result.error = browse_result.error

            # Step 3: attempt to extract the API key from the resulting page
            dashboard_url = browse_result.extracted_data.get("dashboard_url", "")
            result.dashboard_url = dashboard_url

            api_key = await self._extract_api_key(
                dashboard_url or browse_result.url
            )

            if not api_key:
                result.manual_steps.append(
                    "Could not auto-extract API key. "
                    f"Please log into {vendor_url}, navigate to your dashboard or "
                    "API settings, copy your API key, and run:\n"
                    f"  hackforge auth store {tool_name} <YOUR_API_KEY>"
                )
            else:
                # Step 4: persist the key
                config_path = await self._store_credentials(tool_name, api_key)
                result.api_key = api_key
                result.config_path = str(config_path)
                result.setup_complete = True
                logger.info("AuthForge: stored API key for %s", tool_name)

        except Exception as exc:
            logger.exception("AuthForge: unexpected error setting up %s", tool_name)
            result.error = str(exc)
            result.manual_steps.append(
                f"Unexpected error during auth flow: {exc}. "
                "Please complete setup manually."
            )

        return result

    # ------------------------------------------------------------------
    # Step 1: find signup page
    # ------------------------------------------------------------------

    async def _find_signup_page(self, vendor_url: str) -> str:
        """Use Tavily to locate the developer/API signup or dashboard URL.

        Runs several targeted queries to find the exact page where a developer
        can sign up for API access.

        Args:
            vendor_url: The vendor's primary website URL.

        Returns:
            URL of the signup/developer-portal page, or empty string if none found.
        """
        from hackforge.providers.tavily_client import TavilyClient

        queries = [
            f"site:{vendor_url} developer API signup register",
            f"{vendor_url} API key developer portal signup",
            f"{vendor_url} get API key quickstart",
        ]

        async with TavilyClient(self._config.tavily) as client:
            for query in queries:
                try:
                    resp = await client.search(query, max_results=5, search_depth="basic")
                    for result in resp.results:
                        url_lower = result.url.lower()
                        # Prefer URLs that look like signup/developer pages
                        if any(
                            kw in url_lower
                            for kw in (
                                "signup", "sign-up", "register", "developer",
                                "api-keys", "apikeys", "console", "dashboard",
                                "get-started", "quickstart",
                            )
                        ):
                            return result.url
                    # Fallback: return the first result URL if any
                    if resp.results:
                        return resp.results[0].url
                except Exception as exc:
                    logger.debug("Tavily query failed: %q — %s", query, exc)

        return ""

    # ------------------------------------------------------------------
    # Step 2: navigate signup
    # ------------------------------------------------------------------

    async def _navigate_signup(
        self, signup_url: str, user_email: str
    ) -> BrowseResult:
        """Use Yutori browse to navigate the signup page and fill in forms.

        Sends an agentic browsing request to Yutori with the signup URL and
        the user's email.  Yutori will attempt to:
          - Fill the email field.
          - Generate and fill a password (returned in ``extracted_data``).
          - Submit the form.
          - Return the resulting dashboard URL if registration succeeds.

        Args:
            signup_url: URL of the signup page to navigate.
            user_email: Email address to register with.

        Returns:
            A :class:`BrowseResult` with success status and any extracted data.
        """
        if not self._config.yutori.api_key:
            logger.warning("Yutori not configured — cannot auto-navigate signup")
            return BrowseResult(
                url=signup_url,
                success=False,
                error="Yutori API key not configured.",
            )

        try:
            async with httpx.AsyncClient(timeout=self._config.yutori.timeout) as client:
                response = await client.post(
                    f"{self._config.yutori.base_url}/browse/agent",
                    headers={
                        "Authorization": f"Bearer {self._config.yutori.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "url": signup_url,
                        "goal": (
                            "Complete the developer signup/registration form. "
                            "Use the provided email address. Generate a strong password. "
                            "After registering, navigate to the API keys or developer dashboard "
                            "and return the dashboard URL and any visible API keys."
                        ),
                        "form_data": {
                            "email": user_email,
                        },
                        "extract": ["dashboard_url", "api_key", "api_token"],
                        "max_steps": 15,
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()

                return BrowseResult(
                    url=data.get("final_url", signup_url),
                    page_text=data.get("page_text", ""),
                    extracted_data=data.get("extracted", {}),
                    success=data.get("success", False),
                    error=data.get("error"),
                )

        except httpx.HTTPStatusError as exc:
            logger.warning("Yutori browse HTTP error: %s", exc)
            return BrowseResult(
                url=signup_url,
                success=False,
                error=f"Yutori HTTP error: {exc.response.status_code}",
            )
        except Exception as exc:
            logger.warning("Yutori browse failed: %s", exc)
            return BrowseResult(
                url=signup_url,
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Step 3: extract API key
    # ------------------------------------------------------------------

    async def _extract_api_key(self, dashboard_url: str) -> str | None:
        """Attempt to extract an API key from a dashboard page.

        Uses two strategies:
          1. Yutori agent browse with explicit goal to find and copy the API key.
          2. Regex scan of raw page HTML for common API key patterns.

        Args:
            dashboard_url: URL of the dashboard or API-keys page.

        Returns:
            The API key string if found, else ``None``.
        """
        if not dashboard_url:
            return None

        # Strategy 1: Yutori agent extraction
        if self._config.yutori.api_key:
            key = await self._extract_key_via_yutori(dashboard_url)
            if key:
                return key

        # Strategy 2: direct HTTP + regex
        return await self._extract_key_via_regex(dashboard_url)

    async def _extract_key_via_yutori(self, dashboard_url: str) -> str | None:
        """Ask Yutori to navigate to the dashboard and extract the API key.

        Args:
            dashboard_url: URL of the API dashboard page.

        Returns:
            API key string or ``None``.
        """
        try:
            async with httpx.AsyncClient(timeout=self._config.yutori.timeout) as client:
                response = await client.post(
                    f"{self._config.yutori.base_url}/browse/agent",
                    headers={
                        "Authorization": f"Bearer {self._config.yutori.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "url": dashboard_url,
                        "goal": (
                            "Find the API key, access token, or secret key on this page. "
                            "Look for input fields, code blocks, or 'copy' buttons. "
                            "Return the key value exactly as shown."
                        ),
                        "extract": ["api_key", "api_token", "access_token", "secret_key"],
                        "max_steps": 5,
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                extracted: dict[str, Any] = data.get("extracted", {})

                for field in ("api_key", "api_token", "access_token", "secret_key"):
                    if extracted.get(field):
                        return str(extracted[field])
        except Exception as exc:
            logger.debug("Yutori key extraction failed: %s", exc)

        return None

    async def _extract_key_via_regex(self, page_url: str) -> str | None:
        """Fetch a page directly and scan for API key patterns via regex.

        Common patterns:
          - ``tvly-...``  (Tavily)
          - ``sk-...``    (OpenAI style)
          - ``Bearer ...``
          - Long hex/base64 tokens in form inputs

        Args:
            page_url: URL to fetch and scan.

        Returns:
            First matching API key, or ``None``.
        """
        patterns = [
            # Labelled key patterns — value in group 1
            r'(?:api[_-]?key|access[_-]?token|secret[_-]?key)["\s:=]+([A-Za-z0-9_\-\.]{20,})',
            # OpenAI-style
            r'\b(sk-[A-Za-z0-9]{20,})\b',
            # Tavily-style
            r'\b(tvly-[A-Za-z0-9]{20,})\b',
            # Generic long token
            r'value=["\']([A-Za-z0-9_\-\.]{32,})["\']',
        ]

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(page_url, headers={"User-Agent": "HackForge/0.1"})
                resp.raise_for_status()
                page_text = resp.text

            for pattern in patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return match.group(1)
        except Exception as exc:
            logger.debug("Regex key extraction failed for %s: %s", page_url, exc)

        return None

    # ------------------------------------------------------------------
    # Step 4: store credentials
    # ------------------------------------------------------------------

    async def _store_credentials(self, tool_name: str, api_key: str) -> Path:
        """Persist an API key into ``.claude/settings.json``.

        The key is stored under ``env`` using the conventional naming scheme
        ``TOOLNAME_API_KEY`` (uppercase, spaces replaced with underscores).

        Args:
            tool_name: Human-readable tool name (e.g. ``"My Tool"``).
            api_key: The API key to store.

        Returns:
            Path to the settings file that was written.
        """
        env_key = f"{tool_name.upper().replace(' ', '_').replace('-', '_')}_API_KEY"
        settings_path = self._config.project_root / ".claude" / "settings.json"

        # Load or create the settings structure
        settings: dict[str, Any] = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not parse existing settings.json: %s", exc)

        # Merge the new key
        env_section: dict[str, str] = settings.setdefault("env", {})
        env_section[env_key] = api_key

        # Write back
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(settings, indent=2), encoding="utf-8"
        )

        logger.info("Stored %s=%s... in %s", env_key, api_key[:8], settings_path)
        return settings_path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_user_email(self) -> str:
        """Retrieve the configured user email for signup forms.

        Checks ``.claude/settings.json`` for a ``USER_EMAIL`` entry, then
        falls back to the ``USER_EMAIL`` environment variable.

        Returns:
            Email string, or a placeholder if not configured.
        """
        import os

        # Try env first
        email = os.environ.get("USER_EMAIL", "")
        if email:
            return email

        # Try settings.json
        settings_path = self._config.project_root / ".claude" / "settings.json"
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
                email = settings.get("env", {}).get("USER_EMAIL", "")
                if email:
                    return email
            except (json.JSONDecodeError, OSError):
                pass

        logger.warning(
            "USER_EMAIL not configured — using placeholder for signup forms. "
            "Set USER_EMAIL in .claude/settings.json or as an environment variable."
        )
        return "hackforge-user@example.com"
