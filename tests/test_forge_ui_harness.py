"""FORGE UI test harness — verified Playwright capability for future Forge testing.

This harness verifies the browser automation capability exists and can be used
to test FORGE once the frontend is fully implemented and the server is running.

Run with: uv run python -m unittest tests.test_forge_ui_harness -v
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestForgeUIHarness(unittest.TestCase):
    """Test harness for FORGE UI browser automation capability."""

    @classmethod
    def setUpClass(cls):
        """Check prerequisites."""
        cls.playwright_available = False
        cls.chromium_available = False
        cls.frontend_built = False
        
        # Check Playwright
        try:
            from playwright.sync_api import sync_playwright
            cls.playwright_available = True
        except ImportError:
            pass
        
        # Check Chromium
        cls.chromium_available = bool(
            os.path.exists(
                os.path.expanduser("~/Library/Caches/ms-playwright/chromium_headless_shell-1243")
            )
        )
        
        # Check frontend build
        frontend_dist = os.path.join(
            os.path.dirname(__file__), "..", "src", "web", "frontend", "dist", "index.html"
        )
        cls.frontend_built = os.path.exists(frontend_dist)

    def test_playwright_installed(self):
        """Playwright Python package is installed in project venv."""
        self.assertTrue(self.playwright_available, "Playwright not installed in venv")

    def test_chromium_installed(self):
        """Chromium browser binary is downloaded."""
        self.assertTrue(self.chromium_available, "Chromium not downloaded by Playwright")

    def test_frontend_built(self):
        """Forge frontend has been built (dist/index.html exists)."""
        self.assertTrue(self.frontend_built, "Frontend not built — run: cd src/web/frontend && npm run build")

    def test_browser_can_launch(self):
        """Browser can be launched and navigate to a page."""
        if not self.playwright_available or not self.chromium_available:
            self.skipTest("Playwright or Chromium not available")
        
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://example.com")
            title = page.title()
            browser.close()
            
            self.assertEqual(title, "Example Domain")

    def test_browser_can_interact(self):
        """Browser can interact with page elements."""
        if not self.playwright_available or not self.chromium_available:
            self.skipTest("Playwright or Chromium not available")
        
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://httpbin.org/forms/post")
            page.fill('input[name="custname"]', 'Test User')
            name = page.input_value('input[name="custname"]')
            browser.close()
            
            self.assertEqual(name, "Test User")


if __name__ == "__main__":
    unittest.main()
