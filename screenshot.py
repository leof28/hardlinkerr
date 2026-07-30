from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto('http://localhost:5000', wait_until="networkidle")

        # Trigger a refresh on the library tab (or another tab) which generates a toast on success/error
        # Using evaluate since the button text might be different based on language
        # Or let's trigger it through settings tab save button
        page.click("text=⚙️ Paramètres")
        page.wait_for_timeout(500)
        page.click("button:has-text('Sauvegarder')")

        page.wait_for_timeout(500) # Wait for toast to appear
        page.screenshot(path="toast_screenshot.png")

        browser.close()

if __name__ == "__main__":
    run()
