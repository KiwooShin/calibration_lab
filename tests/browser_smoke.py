"""Optional end-to-end check; start server.py first, then run this script.

Requires `pip install playwright && python -m playwright install chromium`.
"""
from pathlib import Path
import json
import sys
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'results' / 'screenshots'
OUTPUT.mkdir(exist_ok=True)


def check_browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chromium', headless='--headed' not in sys.argv,
                                    args=['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('http://127.0.0.1:8765', wait_until='networkidle')
        page.wait_for_function('window.calibrationLab && window.calibrationLab.hasWebGL')
        assert page.locator('#viewport canvas').count() == 1
        assert page.locator('.metric').count() == 4
        assert page.locator('#chart-one svg').count() == 1
        page.screenshot(path=str(OUTPUT / '01-ghost.png'), full_page=True)

        # Run a new numerical fit through the actual control/API path.
        page.locator('#noise').fill('0')
        page.locator('#sample-count').fill('48')
        page.locator('#run-calibration').click()
        page.wait_for_function('window.calibrationLab.data.ghost.count === 48')
        assert page.evaluate('window.calibrationLab.data.ghost.final.position_mm') < 1e-5
        page.locator('#timeline').fill('0')  # Pause playback.
        page.locator('#ghost-view').select_option('workspace')
        assert 'ERROR MAP' in page.locator('#scene-badge').inner_text()
        page.locator('#timeline').fill(page.locator('#timeline').get_attribute('max'))
        with page.expect_download() as download:
            page.locator('#export-data').click()
        exported = download.value
        payload = json.loads(Path(exported.path()).read_text())
        assert payload['count'] == 48
        with page.expect_download() as download:
            page.locator('#snapshot').click()
        assert Path(download.value.path()).read_bytes().startswith(b'\x89PNG')

        page.locator('[data-module="redundancy"]').click()
        page.locator('#timeline').fill('65')
        assert page.locator('.comparison tbody tr').count() == 3
        page.locator('#sweep-mode').select_option('after')
        page.locator('#timeline').fill('70')
        assert 'CALIBRATED PLANNER' in page.locator('#scene-badge').inner_text()
        page.screenshot(path=str(OUTPUT / '02-redundancy.png'), full_page=True)

        page.locator('[data-module="active"]').click()
        page.locator('#budget').select_option('12')
        assert page.evaluate('window.calibrationLab.index') == 11
        page.locator('#point-view').select_option('selected')
        page.locator('#point-view').select_option('gain')
        page.screenshot(path=str(OUTPUT / '03-active-selection.png'), full_page=True)

        page.locator('[data-module="observability"]').click()
        assert '7 / 10' in page.locator('#metrics').inner_text()
        page.locator('#timeline').fill('64')
        assert '0.0000 mm' in page.locator('#frame-readout').inner_text()
        page.screenshot(path=str(OUTPUT / '04-observability.png'), full_page=True)
        page.locator('#measurement').select_option('pose')
        assert '10 / 10' in page.locator('#metrics').inner_text()
        page.locator('#obs-coverage').select_option('narrow')
        assert '9900' in page.locator('#metrics').inner_text()

        page.locator('[data-module="compliance"]').click()
        page.locator('#prediction').select_option('elastic')
        page.locator('#exaggeration').select_option('1')
        page.locator('#payload').select_option('3')
        assert '3.00 KG' in page.locator('#scene-badge').inner_text()
        page.locator('#prediction').select_option('rigid')
        page.locator('#exaggeration').select_option('5')
        page.screenshot(path=str(OUTPUT / '05-compliance.png'), full_page=True)

        # Controls remain usable on a narrow viewport, without page overflow.
        page.set_viewport_size({'width': 390, 'height': 844})
        page.locator('[data-module="ghost"]').click()
        page.locator('#ghost-view').select_option('arm')
        page.wait_for_timeout(200)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(OUTPUT / '06-mobile.png'), full_page=True)
        for body in [{'count': -1}, {'noise_mm': 100}, {'spread': 'invalid'}, []]:
            assert page.request.post('http://127.0.0.1:8765/api/ghost', data=body).status == 400
        assert not errors, errors
        browser.close()
        print('Browser checks passed: five modules, live calibration, exports, WebGL, mobile layout, API validation.')


if __name__ == '__main__':
    check_browser()
