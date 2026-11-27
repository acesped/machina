"""Prueba supervisada de reproducción en Facebook. Ejecutar localmente.
Instalación: pip install playwright && python -m playwright install chromium
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

URL = 'https://www.facebook.com/deusdigitalis/videos/'
REPORT = Path('deus_test_report.json')

async def main():
    report = {'url': URL, 'authenticated': None, 'success': False, 'events': [], 'played_seconds': 0, 'mode': 'manual_supervised'}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
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
