"""One-shot playback smoke test for a public Facebook page."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = 'https://www.facebook.com/deusdigitalis/videos/'
REPORT = Path('deus_test_report.json')

def main():
    result = {'url': URL, 'success': False}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(URL, wait_until='domcontentloaded', timeout=45000)
                video = page.locator('video').first
                video.wait_for(state='attached', timeout=20000)
                video.evaluate('(v) => { v.muted = true; }')
                video.evaluate('(v) => v.play()')
                start = video.evaluate('(v) => v.currentTime')
                page.wait_for_function('(start) => { const v = document.querySelector("video"); return v && v.currentTime > start + 0.5; }', arg=start, timeout=10000)
                result['success'] = True
                result['detail'] = 'Playback clock advanced.'
            finally:
                browser.close()
    except Exception as exc:
        result['detail'] = str(exc)
    finally:
        REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    return 0 if result['success'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
