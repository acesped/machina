"""One-shot playback smoke test with diagnostics for a public Facebook page."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = 'https://www.facebook.com/deusdigitalis/videos/'
REPORT = Path('deus_test_report.json')

STATE = '''v => ({paused: v.paused, readyState: v.readyState,
    networkState: v.networkState, currentTime: v.currentTime,
    duration: Number.isFinite(v.duration) ? v.duration : null,
    ended: v.ended, visible: !!(v.offsetWidth || v.offsetHeight),
    error: v.error ? {code: v.error.code, message: v.error.message} : null})'''


def main():
    result = {'url': URL, 'success': False, 'states': {}, 'media_events': []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(URL, wait_until='domcontentloaded', timeout=45000)
                result['final_url'] = page.url
                video = page.locator('video').first
                video.wait_for(state='attached', timeout=20000)
                result['video_count'] = page.locator('video').count()
                result['states']['before'] = video.evaluate(STATE, timeout=3000)
                video.evaluate('''v => {
                    window.__testMediaEvents = [];
                    for (const name of ['play','playing','pause','waiting','stalled','error','emptied','loadeddata']) {
                        v.addEventListener(name, () => window.__testMediaEvents.push({event:name, time:v.currentTime}), {passive:true});
                    }
                    v.muted = true;
                }''', timeout=3000)
                try:
                    start = video.evaluate('v => v.currentTime', timeout=3000)
                    video.evaluate('v => v.play()', timeout=5000)
                    page.wait_for_function('(start) => { const v = document.querySelector("video"); return v && v.currentTime > start + 0.5; }', arg=start, timeout=10000)
                    result['success'] = True
                    result['detail'] = 'Playback clock advanced.'
                except Exception as exc:
                    result['detail'] = str(exc)
                    result['diagnosis'] = 'Playback interrupted or not confirmed; no retry performed.'
                finally:
                    try:
                        result['states']['after'] = video.evaluate(STATE, timeout=3000)
                        result['media_events'] = page.evaluate('window.__testMediaEvents || []')
                    except Exception as exc:
                        result['diagnostic_error'] = str(exc)
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
