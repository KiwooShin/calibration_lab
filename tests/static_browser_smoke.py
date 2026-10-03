"""Exercise the exported site with no API server, including the actual Wasm solver."""
import argparse
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from calibration.dataset import simulate
from calibration.solver import calibrate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8770/calibration-lab/')
    parser.add_argument('--headed', action='store_true')
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chromium', headless=not args.headed,
            args=['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        page = browser.new_page(viewport={'width':1440, 'height':1050})
        errors, api_requests = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: api_requests.append(r.url) if '/api/' in r.url else None)
        page.goto(args.url)
        page.wait_for_function('window.calibrationApp && window.calibrationApp.hasWebGL')
        baseline = page.evaluate('window.calibrationApp.result.final.validation_rms_mm')
        page.locator('#next-stage').click()
        page.locator('#next-stage').click()
        page.wait_for_function('!window.calibrationApp.busy', timeout=240000)
        assert page.evaluate('window.calibrationApp.stage') == 2, page.locator('#status').inner_text()
        actual = page.evaluate('window.calibrationApp.result.final.validation_rms_mm')
        assert abs(actual - baseline) < .01, (actual, baseline)
        print(f'Browser SciPy default fit matches native Python: {actual:.4f} mm', flush=True)
        page.locator('[data-stage="3"]').click()
        assert page.evaluate('window.calibrationApp.result.samples[window.calibrationApp.sampleIndex].split') == 'validation'
        dataset, _ = simulate(count=24, noise_mm=0, missing=0, outliers=0)
        native = calibrate(dataset)
        page.locator('#file-input').set_input_files({'name':'observations.json', 'mimeType':'application/json', 'buffer':json.dumps(dataset).encode()})
        page.wait_for_function('!window.calibrationApp.busy', timeout=120000)
        result = page.evaluate('window.calibrationApp.result')
        assert result['source'] == 'imported', page.locator('#status').inner_text()
        assert 'truth_rms_mm' not in result['final']
        assert abs(result['final']['validation_rms_mm'] - native['final']['validation_rms_mm']) < .001
        assert result['rank'] == 18
        with page.expect_download() as download:
            page.locator('#export-button').click()
        assert json.loads(Path(download.value.path()).read_text())['source'] == 'imported'
        page.locator('#file-input').set_input_files({'name':'invalid.json', 'mimeType':'application/json', 'buffer':b'{}'})
        page.wait_for_function('!window.calibrationApp.busy', timeout=30000)
        assert 'schema_version' in page.locator('#status').inner_text()
        page.locator('#data-settings').evaluate('(e) => e.open = true')
        page.locator('#frame-count').select_option('24')
        page.locator('#noise').fill('0')
        page.locator('#missing').select_option('0')
        page.locator('#outliers').select_option('0')
        page.locator('#run-demo').click()
        page.wait_for_function('!window.calibrationApp.busy', timeout=120000)
        assert page.evaluate('window.calibrationApp.result.source') == 'synthetic'
        assert page.evaluate('window.calibrationApp.result.final.truth_rms_mm') < .001
        page.set_viewport_size({'width':375, 'height':900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors, errors
        assert not api_requests, api_requests
        print('Passed: live browser fit, held-out frames, import, export, invalid data, regeneration, mobile, no backend requests.', flush=True)
        browser.close()


if __name__ == '__main__':
    main()
