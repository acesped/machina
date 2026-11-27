"""Prueba supervisada local y diagnóstico pasivo en CI.
Instalación: pip install playwright && python -m playwright install chromium
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

URL = 'https://www.facebook.com/deusdigitalis/videos/'
REPORT = Path('deus_test_report.json')

async def main():
    report = {'url': URL, 'authenticated': None, 'success': False, 'events': [], 'played_seconds': 0, 'mode': 'manual_supervised'}
    ci = os.getenv('GITHUB_ACTIONS', '').lower() == 'true' or os.getenv('CI', '').lower() == 'true'
    no_display = sys.platform.startswith('linux') and not (os.getenv('DISPLAY') or os.getenv('WAYLAND_DISPLAY'))
    headless = ci or no_display or not sys.stdin.isatty()
    report.update(headless=headless, diagnostic_completed=False, status='failed')
    if headless:
        report['mode'] = 'headless_diagnostic'
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                response = await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
                report['navigation_status'] = response.status if response else None
                if headless:
                    report['final_url'] = page.url
                    report['page_title'] = await page.title()
                    report['authenticated'] = any(c['name'] == 'c_user' and c['value'] for c in await context.cookies('https://www.facebook.com'))
                    report['password_visible'] = await page.locator('input[type=password]:visible').count() > 0
                    report['visible_dialogs'] = await page.locator('[role=dialog]:visible').count()
                    report['video_count'] = await page.locator('video').count()
                    report['states'] = await page.locator('video').evaluate_all("""vs => vs.map(v => ({paused:v.paused, readyState:v.readyState, currentTime:v.currentTime, duration:Number.isFinite(v.duration)?v.duration:null, ended:v.ended}))""")
                    report['diagnostic_completed'] = True
                    report['status'] = 'inconclusive'
                    report['detail'] = 'Diagnóstico sin pantalla completado; no se solicitó reproducción. La prueba supervisada requiere ejecución local.'
                    report['played_seconds'] = None
                    try:
                        await page.screenshot(path='deus_test_diagnostic.png', timeout=10000)
                    except Exception:
                        report['screenshot_error'] = 'No se pudo guardar la captura.'
                    return 0
                print('Inicia sesión manualmente si es necesario. Abre una publicación de video y déjala pausada al inicio.')
                await asyncio.to_thread(input, 'Pulsa Enter aquí cuando esté preparada: ')
                # La cookie es una señal, no una garantía de autorización.
                cookies = await context.cookies('https://www.facebook.com')
                report['authenticated'] = any(c['name'] == 'c_user' and c['value'] for c in cookies)
                if not report['authenticated']:
                    raise RuntimeError('No se detectó una sesión autenticada.')
                report['video_url'] = page.url.split('?')[0] if '/videos/' in page.url else page.url
                report['video_title'] = await page.title()
                og = page.locator('meta[property="og:title"]').first
                if await og.count():
                    report['video_title'] = await og.get_attribute('content') or report['video_title']
                report['title_source'] = 'page metadata; may be generic'
                videos = page.locator('video:visible')
                if await videos.count() != 1:
                    raise RuntimeError('Abre una publicación individual con un único reproductor visible.')
                video = videos.first
                await video.evaluate('''v => {
                    v.__deusEvents = [];
                    for (const event of ['playing','pause','ended','waiting','error']) {
                        v.addEventListener(event, () => v.__deusEvents.push({event, currentTime:v.currentTime, timestamp:new Date().toISOString()}));
                    }
                }''')
                snapshot = '''v => ({duration:Number.isFinite(v.duration)?v.duration:null, currentTime:v.currentTime, paused:v.paused, ended:v.ended, readyState:v.readyState, played_ranges:Array.from({length:v.played.length},(_,i)=>({start:v.played.start(i),end:v.played.end(i)})), events:v.__deusEvents||[]})'''
                before = await video.evaluate(snapshot)
                report['before'] = before
                if not before['paused'] or before['played_ranges']:
                    raise RuntimeError('La prueba necesita un reproductor pausado y sin reproducción previa.')
                print('Inicia el video manualmente en el navegador. Al terminar, pausa el video o deja que finalice.')
                await asyncio.to_thread(input, 'Pulsa Enter aquí para finalizar la medición: ')
                after = await video.evaluate(snapshot)
                report['after'] = after
                report['events'] = after['events']
                report['duration'] = after['duration']
                report['played_seconds'] = round(sum(r['end']-r['start'] for r in after['played_ranges']), 3)
                report['success'] = report['played_seconds'] > 0 and any(e['event']=='playing' for e in report['events'])
                report['detail'] = 'Reproducción observada' if report['success'] else 'Reproducción no confirmada'
                report['diagnostic_completed'] = True
                report['status'] = 'passed' if report['success'] else 'failed'
            except Exception as exc:
                report['detail'] = str(exc)
            finally:
                await browser.close()
    except Exception as exc:
        report['detail'] = str(exc)
    finally:
        report['timestamp'] = datetime.now(timezone.utc).isoformat()
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
    return 0 if report['success'] else 1

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
