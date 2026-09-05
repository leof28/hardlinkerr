from playwright.sync_api import sync_playwright

def run_cuj(page):
    page.goto("http://localhost:5000")
    page.wait_for_timeout(2000)

    # Check that main tabs are present and accessible
    tabs = page.locator("div[role='tablist']").first.locator("button[role='tab']")
    print(f"Found {tabs.count()} main tabs.")

    # Click on the settings tab
    page.get_by_text("⚙️ Paramètres").click()
    page.wait_for_timeout(1000)

    # Verify the settings tabs are present
    settings_tabs = page.locator("div[role='tablist']").nth(1).locator("button[role='tab']")
    print(f"Found {settings_tabs.count()} settings tabs.")

    page.screenshot(path="verification/screenshots/verification.png")
    page.wait_for_timeout(1000)

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir="verification/videos"
        )
        page = context.new_page()
        try:
            run_cuj(page)
        finally:
            context.close()
            browser.close()
