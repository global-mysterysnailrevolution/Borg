"""Auth Forge Engine — Yutori-Powered OAuth + API Key Acquisition.

Automatically navigates vendor signup/developer-portal pages to acquire API
keys using Yutori's cloud browser agent. Supports Google OAuth, GitHub SSO,
and email/password signup flows.

Pipeline per tool:
  find signup page (Tavily) → Yutori navigates signup (OAuth or email)
  → extract API key from dashboard → store in settings.json → return AuthResult

Uses the real Yutori Browsing API:
  POST https://api.yutori.com/v1/browsing/tasks  (create task)
  GET  https://api.yutori.com/v1/browsing/tasks/{id}  (poll status)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from hackforge.config import HackForgeConfig
from hackforge.pipeline_bus import PipelineBus

logger = logging.getLogger(__name__)

YUTORI_API = "https://api.yutori.com/v1"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


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
    view_url: str = ""  # Yutori live browser view URL
    error: str | None = None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class AuthForgeEngine:
    """Navigates vendor signup pages via Yutori cloud browser to acquire API keys.

    Uses:
    - **Tavily** to search for developer/API signup and documentation pages.
    - **Yutori Browsing API** to navigate sign-up flows, handle OAuth, and
      extract API keys from dashboards.
    - Local file I/O to persist keys into ``.claude/settings.json`` and ``.env``.

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

    def __init__(
        self,
        config: HackForgeConfig,
        bus: PipelineBus | None = None,
    ) -> None:
        self._config = config
        self._bus = bus

    # ------------------------------------------------------------------
    # Pipeline bus helper
    # ------------------------------------------------------------------

    async def _emit(self, step: str, message: str, data: dict[str, Any] | None = None) -> None:
        if self._bus:
            await self._bus.emit_step("auth_forge", step, message, data or {})

    async def _emit_error(self, step: str, message: str) -> None:
        if self._bus:
            await self._bus.emit_error("auth_forge", step, message)

    # ------------------------------------------------------------------
    # Yutori Browsing API helpers
    # ------------------------------------------------------------------

    async def _create_task(
        self,
        start_url: str,
        task: str,
        *,
        require_auth: bool = False,
        output_schema: dict[str, Any] | None = None,
        max_steps: int = 30,
    ) -> dict[str, Any]:
        """Create a Yutori browsing task.

        Returns dict with task_id, view_url, status.
        """
        payload: dict[str, Any] = {
            "start_url": start_url,
            "task": task,
            "max_steps": max_steps,
            "agent": "navigator-n1-latest",
        }
        if require_auth:
            payload["require_auth"] = True
        if output_schema:
            payload["output_schema"] = output_schema

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{YUTORI_API}/browsing/tasks",
                headers={
                    "X-API-Key": self._config.yutori.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def _poll_task(
        self,
        task_id: str,
        timeout: float = 120,
        poll_interval: float = 3,
    ) -> dict[str, Any]:
        """Poll a Yutori browsing task until it succeeds or fails.

        Returns the final task response dict.
        """
        elapsed = 0.0
        while elapsed < timeout:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{YUTORI_API}/browsing/tasks/{task_id}",
                    headers={"X-API-Key": self._config.yutori.api_key},
                )
                resp.raise_for_status()
                data = resp.json()

            status = data.get("status", "")
            if status in ("succeeded", "failed"):
                return data

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        return {"status": "timeout", "result": None, "error": f"Task timed out after {timeout}s"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def setup_tool(self, tool_name: str, vendor_url: str) -> AuthResult:
        """Full auth flow: find signup → navigate → get API key → store.

        Args:
            tool_name: Human-readable name of the tool (e.g. ``"Tavily"``).
            vendor_url: The vendor's primary website URL.

        Returns:
            An :class:`AuthResult` with the extracted API key (if successful)
            and any manual steps required.
        """
        logger.info("AuthForge: setting up %s (%s)", tool_name, vendor_url)
        result = AuthResult(tool_name=tool_name)

        if not self._config.yutori.api_key:
            result.error = "Yutori API key not configured"
            result.manual_steps.append(
                f"Yutori API key required. Navigate to {vendor_url} and sign up manually."
            )
            await self._emit_error("start", "Yutori API key not configured")
            return result

        try:
            # Step 1: find the developer/API signup page
            await self._emit("search", f"Searching for {tool_name} developer signup page...")
            signup_url = await self._find_signup_page(tool_name, vendor_url)
            if not signup_url:
                signup_url = vendor_url  # fallback to vendor homepage
                await self._emit("search", f"No specific signup page found, using {vendor_url}")

            await self._emit("search", f"Found signup page: {signup_url}")

            # Step 2: navigate the signup form via Yutori (with OAuth support)
            await self._emit("navigate", f"Yutori navigating to {signup_url}...")
            user_email = self._get_user_email()
            nav_result = await self._navigate_signup(signup_url, user_email, tool_name)

            result.view_url = nav_result.get("view_url", "")
            if result.view_url:
                await self._emit("navigate", f"Watch live: {result.view_url}", {"view_url": result.view_url})

            # Poll for navigation completion
            task_id = nav_result.get("task_id", "")
            if task_id:
                await self._emit("navigate", "Waiting for Yutori to complete signup flow...")
                nav_data = await self._poll_task(task_id, timeout=self._config.yutori.timeout)
                nav_status = nav_data.get("status", "")

                if nav_status == "failed":
                    await self._emit_error("navigate", f"Signup navigation failed: {nav_data.get('result', 'unknown error')}")
                    result.manual_steps.append(
                        f"Automated signup failed. Navigate to {signup_url} and sign up manually."
                    )
                elif nav_status == "succeeded":
                    await self._emit("navigate", "Signup navigation completed successfully")
                    # Check if the nav result already contains an API key
                    structured = nav_data.get("structured_result") or {}
                    if isinstance(structured, dict) and structured.get("api_key"):
                        result.api_key = structured["api_key"]
                        result.dashboard_url = structured.get("dashboard_url", "")
                        await self._emit("extract", f"API key found during signup: {result.api_key[:8]}...")
                else:
                    await self._emit_error("navigate", f"Signup navigation timed out")
                    result.manual_steps.append("Navigation timed out. Try again or sign up manually.")

            # Step 3: If we don't have a key yet, try extracting from dashboard
            if not result.api_key:
                dashboard_url = result.dashboard_url or signup_url
                await self._emit("extract", f"Extracting API key from {dashboard_url}...")
                api_key, extract_view_url = await self._extract_api_key(tool_name, dashboard_url)

                if extract_view_url:
                    result.view_url = extract_view_url

                if api_key:
                    result.api_key = api_key
                    await self._emit("extract", f"API key extracted: {api_key[:8]}...")
                else:
                    await self._emit_error("extract", "Could not auto-extract API key")
                    result.manual_steps.append(
                        f"Could not auto-extract API key. Log into {vendor_url}, "
                        "go to API settings, copy your key, and paste it in the .env file."
                    )

            # Step 4: Store the key if we got one
            if result.api_key:
                await self._emit("store", f"Storing API key for {tool_name}...")
                config_path = await self._store_credentials(tool_name, result.api_key)
                result.config_path = str(config_path)
                result.setup_complete = True
                result.auth_type = "api_key"
                await self._emit("complete", f"{tool_name} API key acquired and stored!")
                logger.info("AuthForge: stored API key for %s", tool_name)
            else:
                await self._emit_error("complete", f"Could not acquire API key for {tool_name}")

        except httpx.HTTPStatusError as exc:
            error_msg = f"Yutori API error: {exc.response.status_code}"
            logger.exception("AuthForge: HTTP error setting up %s", tool_name)
            result.error = error_msg
            result.manual_steps.append(f"{error_msg}. Sign up manually at {vendor_url}.")
            await self._emit_error("error", error_msg)

        except Exception as exc:
            logger.exception("AuthForge: unexpected error setting up %s", tool_name)
            result.error = str(exc)
            result.manual_steps.append(
                f"Unexpected error: {exc}. Complete setup manually at {vendor_url}."
            )
            await self._emit_error("error", str(exc))

        return result

    # ------------------------------------------------------------------
    # Step 1: find signup page
    # ------------------------------------------------------------------

    async def _find_signup_page(self, tool_name: str, vendor_url: str) -> str:
        """Use Tavily to locate the developer/API signup or dashboard URL."""
        if not self._config.tavily.api_key:
            return ""

        queries = [
            f"{tool_name} developer API signup get API key",
            f"site:{vendor_url} developer API key dashboard",
            f"{tool_name} API documentation quickstart",
        ]

        try:
            async with httpx.AsyncClient(timeout=self._config.tavily.timeout) as client:
                for query in queries:
                    try:
                        resp = await client.post(
                            f"{self._config.tavily.base_url}/search",
                            json={
                                "api_key": self._config.tavily.api_key,
                                "query": query,
                                "max_results": 5,
                                "search_depth": "basic",
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()

                        for r in data.get("results", []):
                            url_lower = r.get("url", "").lower()
                            if any(
                                kw in url_lower
                                for kw in (
                                    "signup", "sign-up", "register", "developer",
                                    "api-keys", "apikeys", "console", "dashboard",
                                    "get-started", "quickstart", "docs", "api",
                                )
                            ):
                                return r["url"]

                        # Fallback: first result
                        results = data.get("results", [])
                        if results:
                            return results[0]["url"]
                    except Exception as exc:
                        logger.debug("Tavily query failed: %s — %s", query, exc)
        except Exception as exc:
            logger.debug("Tavily search failed: %s", exc)

        return ""

    # ------------------------------------------------------------------
    # Step 2: navigate signup via Yutori
    # ------------------------------------------------------------------

    async def _navigate_signup(
        self,
        signup_url: str,
        user_email: str,
        tool_name: str,
    ) -> dict[str, Any]:
        """Use Yutori Browsing API to navigate the signup page.

        Uses require_auth=True for OAuth-optimized browsing.

        Returns the task creation response with task_id and view_url.
        """
        task_description = (
            f"Navigate to this {tool_name} page and sign up for developer/API access. "
            f"Look for these options in order of preference:\n"
            f"1. 'Sign in with Google' or 'Continue with Google' button\n"
            f"2. 'Sign in with GitHub' or 'Continue with GitHub' button\n"
            f"3. Email/password registration form\n\n"
            f"If using email signup, use: {user_email}\n\n"
            f"After signing in or registering, navigate to the API keys page, "
            f"developer dashboard, or settings where API keys are managed. "
            f"If you see an API key or access token, note it."
        )

        output_schema = {
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "string",
                    "description": "API key or access token if visible",
                },
                "dashboard_url": {
                    "type": "string",
                    "description": "URL of the API dashboard or keys page",
                },
                "auth_method": {
                    "type": "string",
                    "description": "How authentication was completed: google_oauth, github_oauth, email_signup, or failed",
                },
            },
        }

        return await self._create_task(
            start_url=signup_url,
            task=task_description,
            require_auth=True,
            output_schema=output_schema,
            max_steps=50,
        )

    # ------------------------------------------------------------------
    # Step 3: extract API key
    # ------------------------------------------------------------------

    async def _extract_api_key(
        self, tool_name: str, dashboard_url: str
    ) -> tuple[str | None, str]:
        """Attempt to extract an API key from a dashboard page via Yutori.

        Returns (api_key_or_None, view_url).
        """
        if not dashboard_url:
            return None, ""

        # Strategy 1: Yutori with structured extraction
        try:
            task_description = (
                f"Find the API key, access token, or secret key on this {tool_name} page. "
                f"Look for:\n"
                f"- Input fields or code blocks containing long alphanumeric strings\n"
                f"- 'Copy' or 'Show' buttons next to API keys\n"
                f"- A 'Create API Key' or 'Generate Key' button — click it if needed\n"
                f"- Settings or API sections in the navigation\n\n"
                f"Return the API key value exactly as shown."
            )

            output_schema = {
                "type": "object",
                "properties": {
                    "api_key": {
                        "type": "string",
                        "description": "The API key, access token, or secret key value",
                    },
                    "key_name": {
                        "type": "string",
                        "description": "The label or name of the key",
                    },
                    "dashboard_url": {
                        "type": "string",
                        "description": "Current page URL",
                    },
                },
            }

            create_resp = await self._create_task(
                start_url=dashboard_url,
                task=task_description,
                output_schema=output_schema,
                max_steps=15,
            )

            view_url = create_resp.get("view_url", "")
            task_id = create_resp.get("task_id", "")

            if task_id:
                if self._bus:
                    await self._emit("extract", f"Yutori extracting key... Watch: {view_url}", {"view_url": view_url})

                result = await self._poll_task(task_id, timeout=90)

                if result.get("status") == "succeeded":
                    # Check structured result first
                    structured = result.get("structured_result") or {}
                    if isinstance(structured, dict) and structured.get("api_key"):
                        return structured["api_key"], view_url

                    # Check plain text result for key patterns
                    text_result = result.get("result", "")
                    if text_result:
                        key = self._extract_key_from_text(text_result)
                        if key:
                            return key, view_url

            return None, view_url

        except Exception as exc:
            logger.debug("Yutori key extraction failed: %s", exc)
            return None, ""

    def _extract_key_from_text(self, text: str) -> str | None:
        """Extract an API key from text using common patterns."""
        patterns = [
            r'(?:api[_-]?key|access[_-]?token|secret[_-]?key)["\s:=]+([A-Za-z0-9_\-\.]{20,})',
            r'\b(sk-[A-Za-z0-9_\-]{20,})\b',
            r'\b(tvly-[A-Za-z0-9_\-]{20,})\b',
            r'\b(yt_[A-Za-z0-9_\-]{20,})\b',
            r'\b([A-Za-z0-9]{32,})\b',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    # ------------------------------------------------------------------
    # Step 4: store credentials
    # ------------------------------------------------------------------

    async def _store_credentials(self, tool_name: str, api_key: str) -> Path:
        """Persist an API key into ``.claude/settings.json`` and ``.env``.

        The key is stored using the conventional naming scheme
        ``TOOLNAME_API_KEY`` (uppercase, spaces/hyphens → underscores).
        """
        env_key = f"{tool_name.upper().replace(' ', '_').replace('-', '_')}_API_KEY"

        # --- Update .claude/settings.json ---
        settings_path = self._config.project_root / ".claude" / "settings.json"
        settings: dict[str, Any] = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not parse settings.json: %s", exc)

        env_section: dict[str, str] = settings.setdefault("env", {})
        env_section[env_key] = api_key

        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

        # --- Also append to .env if not already present ---
        env_path = self._config.project_root / ".env"
        if env_path.exists():
            env_content = env_path.read_text(encoding="utf-8")
            if f"{env_key}=" not in env_content:
                with open(env_path, "a", encoding="utf-8") as f:
                    f.write(f"\n# {tool_name} — auto-acquired by AuthForge\n")
                    f.write(f"{env_key}={api_key}\n")

        logger.info("Stored %s=%s... in %s", env_key, api_key[:8], settings_path)
        return settings_path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_user_email(self) -> str:
        """Retrieve the configured user email for signup forms."""
        import os

        email = os.environ.get("USER_EMAIL", "")
        if email:
            return email

        settings_path = self._config.project_root / ".claude" / "settings.json"
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
                email = settings.get("env", {}).get("USER_EMAIL", "")
                if email:
                    return email
            except (json.JSONDecodeError, OSError):
                pass

        return "borg-agent@hackforge.dev"
