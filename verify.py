from playwright.sync_api import sync_playwright
import json

def handle_route(route):
    url = route.request.url
    if '/api/status' in url:
        route.fulfill(status=200, content_type="application/json", body="[]")
    elif '/api/genres' in url:
        route.fulfill(status=200, content_type="application/json", body='[{"name": "Action", "folder": "Action", "enabled": true}]')
    elif '/api/studios' in url:
        route.fulfill(status=200, content_type="application/json", body='[{"name": "20th Century Studios", "folder": "Fox", "enabled": false}, {"name": "Lionsgate", "folder": "Lionsgate", "enabled": true}, {"name": "SmallStudio", "folder": "SmallStudio", "enabled": true}]')
    elif '/api/platforms' in url:
        route.fulfill(status=200, content_type="application/json", body='[{"name": "Netflix", "folder": "Netflix", "enabled": true}]')
    else:
        route.continue_()

def run_cuj(page):
    page.route("**/*", handle_route)
    page.goto("http://localhost:5000")
    page.wait_for_timeout(3000)

    page.evaluate('document.querySelectorAll(".tab-btn").forEach(btn => { if(btn.innerText.includes("Paramètres")) btn.click() })')
    page.wait_for_timeout(2000)

    page.evaluate('document.querySelectorAll(".tab-btn").forEach(btn => { if(btn.innerText.includes("Studios")) btn.click() })')
    page.wait_for_timeout(1000)
    page.screenshot(path="/home/jules/verification/screenshots/verification1.png")

    page.evaluate('document.querySelectorAll("button").forEach(btn => { if(btn.innerText.includes("Classiques uniquement")) btn.click() })')
    page.wait_for_timeout(1000)

    page.screenshot(path="/home/jules/verification/screenshots/verification_final.png")
    page.wait_for_timeout(1000)  # Hold final state for the video

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
