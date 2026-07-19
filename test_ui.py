from playwright.sync_api import sync_playwright
import time

def test_modal_escape():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://localhost:5000")

        # Wait for data to load
        time.sleep(2)

        # See if we can click a movie card to open modal
        cards = page.locator('.movie-card')
        if cards.count() > 0:
            cards.first.click()
            time.sleep(1)

            # Modal should be open
            print("Modal open? ", page.locator('.modal-box').is_visible())

            # Press Escape
            page.keyboard.press('Escape')
            time.sleep(1)

            # Modal should be closed
            print("Modal open after escape? ", page.locator('.modal-box').is_visible())
        else:
            print("No movie cards found to test.")

        browser.close()

if __name__ == '__main__':
    test_modal_escape()
