"""One-shot Facebook playback diagnostic; no retries or access bypass."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

URL = 'https://www.facebook.com/deusdigitalis/videos/'
REPORT = Path('deus_test_report.json')
STATE = '''v => ({paused:v.paused, readyState:v.readyState,
 networkState:v.networkState, currentTime:v.currentTime,
 duration:Number.isFinite(v.duration)?v.duration:null,
 ended:v.ended, visible:!!(v.offsetWidth||v.offsetHeight),
 error:v.error?{code:v.error.code,message:v.error.message}:null})'''


def safe_url(url):
    parts = urlsplit(url)
    return f'{parts.scheme}://{parts.hostname or ""}{parts.path}' if parts.scheme in ('http','https') else parts.scheme


def main():
    result = dict(url=URL, success=False, states={}, media_events=[],
                  javascript_errors=[], console_errors=[], network_failures=[],
                  http_errors=[], media_responses=[], access_signals={})
    def add(key, item):
        if len(result[key]) < 100:
            result[key].append(item)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.on('pageerror', lambda error: add('javascript_errors', str(error)[:500]))
            page.on('console', lambda msg: add('console_errors', msg.text[:500]) if msg.type == 'error' else None)
            page.on('requestfailed', lambda req: add('network_failures', dict(url=safe_url(req.url), type=req.resource_type, failure=req.failure)))
            def response(res):
                kind = res.request.resource_type
                if res.status >= 400:
                    add('http_errors', dict(url=safe_url(res.url), status=res.status, type=kind))
                if kind == 'media' or res.headers.get('content-type','').startswith(('video/','audio/')):
                    add('media_responses', dict(url=safe_url(res.url), status=res.status, type=kind))
            page.on('response', response)
            try:
                nav = page.goto(URL, wait_until='domcontentloaded', timeout=45000)
                result['navigation_status'] = nav.status if nav else None
                result['final_url'] = safe_url(page.url)
                result['access_signals'] = page.evaluate('''() => {
                    const t = (document.body?.innerText || '').toLowerCase();
                    return {password_field:!!document.querySelector('input[type=password]'),
                    login_url:/\\/(login|checkpoint)(\\/|$)/.test(location.pathname),
                    login_text:/log in to continue|inicia sesi[oó]n para continuar/.test(t),
                    unavailable_text:/content isn't available|contenido no est[aá] disponible/.test(t)};
                }''')
                signals = result['access_signals']
                if signals['login_url'] or signals['password_field'] or signals['login_text'] or signals['unavailable_text'] or (nav and nav.status >= 400):
                    raise RuntimeError('Possible access restriction or authentication requirement; test stopped.')
                video = page.locator('video').first
                video.wait_for(state='attached', timeout=20000)
                result['video_count'] = page.locator('video').count()
                result['states']['before'] = video.evaluate(STATE, timeout=3000)
                video.evaluate('''v => {
                    window.__testMediaEvents = [];
                    for (const name of ['play','playing','pause','waiting','stalled','error','emptied','loadedmetadata','loadeddata','canplay','abort','suspend']) {
                        v.addEventListener(name, () => window.__testMediaEvents.push({event:name,time:v.currentTime,readyState:v.readyState}), {passive:true});
                    }
                    v.muted = true;
                }''', timeout=3000)
                try:
                    start = video.evaluate('v => v.currentTime', timeout=3000)
                    video.evaluate('v => v.play()', timeout=5000)
                    page.wait_for_function('(start) => { const v = document.querySelector("video"); return v && v.currentTime > start + 0.5; }', arg=start, timeout=10000)
                    result['success'] = True
                    result['detail'] = 'Playback clock advanced.'
                finally:
                    try:
                        result['states']['after'] = video.evaluate(STATE, timeout=3000)
                        result['media_events'] = page.evaluate('window.__testMediaEvents || []')
                    except Exception as exc:
                        result['diagnostic_error'] = str(exc)
            except Exception as exc:
                result['detail'] = str(exc)
                result['diagnosis'] = 'Playback not confirmed; no retry performed.'
                try:
                    page.screenshot(path='deus_test_failure.png', timeout=5000)
                    result['screenshot'] = 'deus_test_failure.png'
                except Exception as shot_error:
                    result['screenshot_error'] = str(shot_error)
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
