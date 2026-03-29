import asyncio
from typing import Optional

from pydantic import Field

from app.config import config
from app.tool.base import BaseTool, ToolResult
from app.tool.browser_use_tool import BrowserUseTool


NOTEBOOKLM_URL = "https://notebooklm.google.com"
GOOGLE_SIGNIN_URL = "https://accounts.google.com"


class NotebookLMLogin(BaseTool):
    """Tool to automate Google login for NotebookLM."""

    name: str = "notebooklm_login"
    description: str = (
        "Log into NotebookLM using Google credentials configured in config.toml. "
        "Navigates to NotebookLM, handles the Google sign-in flow (email, password), "
        "and verifies successful login."
    )
    parameters: dict = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    browser_tool: BrowserUseTool = Field(default_factory=BrowserUseTool, exclude=True)

    async def execute(self, **kwargs) -> ToolResult:
        """Execute the NotebookLM login flow."""
        # Validate config
        if not config.notebooklm:
            return ToolResult(
                error="NotebookLM credentials not configured. "
                "Add [notebooklm] section with 'email' and 'password' to config/config.toml"
            )

        email = config.notebooklm.email
        password = config.notebooklm.password

        if not email or not password:
            return ToolResult(
                error="NotebookLM email or password is empty in config.toml"
            )

        try:
            # Initialize the browser
            context = await self.browser_tool._ensure_browser_initialized()
            page = await context.get_current_page()

            # Step 1: Navigate to NotebookLM
            await page.goto(NOTEBOOKLM_URL)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            # Check if already logged in
            current_url = page.url
            if "notebooklm.google.com" in current_url and "accounts.google.com" not in current_url:
                # May already be logged in, check for sign-in button
                sign_in_button = await page.query_selector(
                    'a[href*="accounts.google.com"], button:has-text("Sign in"), '
                    'a:has-text("Sign in"), [data-action="sign in"]'
                )
                if not sign_in_button:
                    return ToolResult(output="Already logged into NotebookLM.")
                await sign_in_button.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)

            # Step 2: Handle Google sign-in - Email entry
            current_url = page.url
            if "accounts.google.com" in current_url:
                result = await self._enter_email(page, email)
                if result.error:
                    return result

                # Step 3: Handle password entry
                result = await self._enter_password(page, password)
                if result.error:
                    return result

            # Step 4: Wait for redirect back to NotebookLM
            await self._wait_for_notebooklm(page)

            # Step 5: Verify login success
            await asyncio.sleep(3)
            current_url = page.url
            if "notebooklm.google.com" in current_url and "accounts.google.com" not in current_url:
                return ToolResult(
                    output=f"Successfully logged into NotebookLM as {email}. Current URL: {current_url}"
                )
            else:
                return ToolResult(
                    error=f"Login may not have completed. Current URL: {current_url}. "
                    "There may be additional verification steps (2FA, captcha) that require manual intervention."
                )

        except Exception as e:
            return ToolResult(error=f"NotebookLM login failed: {str(e)}")

    async def _enter_email(self, page, email: str) -> ToolResult:
        """Enter email address in Google sign-in form."""
        try:
            # Wait for email input field
            email_input = await page.wait_for_selector(
                'input[type="email"], input[name="identifier"], #identifierId',
                timeout=10000,
            )
            if not email_input:
                return ToolResult(error="Could not find email input field on Google sign-in page")

            await email_input.fill(email)
            await asyncio.sleep(0.5)

            # Click Next button
            next_button = await page.query_selector(
                '#identifierNext, button:has-text("Next"), '
                'div[role="button"]:has-text("Next"), '
                'input[type="submit"]'
            )
            if next_button:
                await next_button.click()
            else:
                await page.keyboard.press("Enter")

            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            return ToolResult(output="Email entered successfully")

        except Exception as e:
            return ToolResult(error=f"Failed to enter email: {str(e)}")

    async def _enter_password(self, page, password: str) -> ToolResult:
        """Enter password in Google sign-in form."""
        try:
            # Wait for password input field
            password_input = await page.wait_for_selector(
                'input[type="password"], input[name="Passwd"]',
                timeout=10000,
            )
            if not password_input:
                return ToolResult(error="Could not find password input field on Google sign-in page")

            await password_input.fill(password)
            await asyncio.sleep(0.5)

            # Click Next button
            next_button = await page.query_selector(
                '#passwordNext, button:has-text("Next"), '
                'div[role="button"]:has-text("Next"), '
                'input[type="submit"]'
            )
            if next_button:
                await next_button.click()
            else:
                await page.keyboard.press("Enter")

            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            return ToolResult(output="Password entered successfully")

        except Exception as e:
            return ToolResult(error=f"Failed to enter password: {str(e)}")

    async def _wait_for_notebooklm(self, page, timeout: int = 30) -> None:
        """Wait for redirect back to NotebookLM after login."""
        for _ in range(timeout):
            current_url = page.url
            if "notebooklm.google.com" in current_url and "accounts.google.com" not in current_url:
                return
            await asyncio.sleep(1)

    async def cleanup(self):
        """Clean up browser resources."""
        await self.browser_tool.cleanup()
