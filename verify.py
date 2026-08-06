from playwright.sync_api import sync_playwright

def run_cuj(page):
    page.goto("http://localhost:5000")
    page.wait_for_timeout(2000)

    # Mock the API response to ensure MovieCards are rendered
    page.route("**/api/status**", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body='{"movies": [{"path": "/media/movies/Test (2024)", "title": "Test Movie", "poster": "https://via.placeholder.com/130x195", "hardlinks": []}]}'
    ))
    page.route("**/api/genres**", lambda route: route.fulfill(status=200, json=[]))
    page.route("**/api/studios**", lambda route: route.fulfill(status=200, json=[]))
    page.route("**/api/platforms**", lambda route: route.fulfill(status=200, json=[]))

    # Reload page to apply mocks
    page.reload()
    page.wait_for_timeout(2000)

    # Click the checkbox on the first MovieCard
    page.locator('.checkbox-overlay').first.click()
    page.wait_for_timeout(500)

    # Focus the checkbox using Tab to verify keyboard navigation (focus-visible)
    # First tab might go to the search input, so we tab a few times
    page.keyboard.press("Tab")
    page.wait_for_timeout(100)
    page.keyboard.press("Tab")
    page.wait_for_timeout(100)
    page.keyboard.press("Tab")
    page.wait_for_timeout(100)

    # Actually just click the card to give it focus, then tab to the checkbox if it's reachable,
    # or just use space
    page.locator('.movie-card').first.focus()
    page.keyboard.press("Space") # Selects the movie via card
    page.wait_for_timeout(500)

    # Try focusing the checkbox directly
    page.locator('.checkbox-overlay input').first.focus()
    page.keyboard.press("Space")
    page.wait_for_timeout(500)

    # Take screenshot at the key moment
    page.screenshot(path="/home/jules/verification/screenshots/verification.png")
    page.wait_for_timeout(1000)

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir="/home/jules/verification/videos"
        )
        page = context.new_page()
        try:
            run_cuj(page)
        finally:
            context.close()
            browser.close()
