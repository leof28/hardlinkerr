from playwright.sync_api import sync_playwright

def run_cuj(page):
    page.on("console", lambda msg: print(f"Browser console: {msg.text}"))
    page.goto("http://localhost:5000")
    page.wait_for_timeout(2000)

    # 1. Click issues tab
    page.evaluate('document.querySelectorAll(".tab-btn").forEach(btn => { if(btn.innerText.includes("Problèmes")) btn.click() })')
    page.wait_for_timeout(1000)
    page.screenshot(path="/home/jules/verification/screenshots/issues_tab.png")

    # 2. Click settings
    page.evaluate('document.querySelectorAll(".tab-btn").forEach(btn => { if(btn.innerText.includes("Paramètres")) btn.click() })')
    page.wait_for_timeout(1000)

    # 3. Click exclusions
    page.evaluate('document.querySelectorAll(".tab-btn").forEach(btn => { if(btn.innerText.includes("Exclusions")) btn.click() })')
    page.wait_for_timeout(1000)
    page.screenshot(path="/home/jules/verification/screenshots/exclusions_tab.png")

    # 4. Click logs
    page.evaluate('document.querySelectorAll(".tab-btn").forEach(btn => { if(btn.innerText.includes("Logs")) btn.click() })')
    page.wait_for_timeout(1000)
    page.screenshot(path="/home/jules/verification/screenshots/logs_tab.png")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir="/home/jules/verification/videos",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        try:
            run_cuj(page)
        finally:
            context.close()  # MUST close context to save the video
            browser.close()
