"""Passive Facebook availability diagnostic; no playback commands or access bypass."""
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
    result = dict(url=URL, success=False, status='failed', diagnostic_completed=False, states={}, media_events=[],
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
                page.wait_for_timeout(2500)
                result['access_signals'] = page.evaluate(r"""() => {
                    const visible = e => !!(e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
                    const passwords = [...document.querySelectorAll('input[type=password]')];
                    const dialogs = [...document.querySelectorAll('[role=dialog],dialog[open],[aria-modal=true]')].filter(visible);
                    const t = (document.body?.innerText || '').toLowerCase();
                    return {password_field:passwords.length>0,
                    password_visible:passwords.some(visible),
                    login_url:/\/(login|checkpoint)(\/|$)/.test(location.pathname),
                    login_text:/log in to continue|inicia sesi[oó]n para continuar/.test(t),
                    unavailable_text:/content isn't available|contenido no est[aá] disponible/.test(t),
                    authentication_dialog:dialogs.some(d=>d.querySelector('input[type=password]') || /log in|inicia sesi[oó]n/i.test(d.innerText)),
                    visible_dialogs:dialogs.length};
                }""")
                signals = result['access_signals']
                videos = page.locator('video')
                result['video_count'] = videos.count()
                result['states']['before'] = videos.evaluate_all('vs => vs.map(' + STATE + ')')
                result['access_assessment'] = ('restriction_indicated' if signals['login_url'] or signals['login_text'] or signals['unavailable_text'] or signals['authentication_dialog'] or (nav and nav.status >= 400) else 'authentication_field_present_unconfirmed' if signals['password_field'] else 'no_explicit_restriction_observed')
                result['media_http_success'] = any(200 <= r['status'] < 300 for r in result['media_responses'])
                page.wait_for_timeout(3000)
                result['states']['after'] = videos.evaluate_all('vs => vs.map(' + STATE + ')')
                result['status'] = 'failed' if result['access_assessment'] == 'restriction_indicated' else 'inconclusive'
                result['detail'] = 'Passive diagnostic only; no playback requested. HTTP success is not proof of playback.'
                result['diagnostic_completed'] = True
                result['screenshot'] = 'deus_test_failure.png'
                page.screenshot(path=result['screenshot'], timeout=5000)

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
    return 0 if result['diagnostic_completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
