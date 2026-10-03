"""Optional: server.py must be running. Use --headed under Xvfb on this ARM64 host."""
from pathlib import Path
import json,sys
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from calibration.dataset import simulate


def main():
    out=ROOT/'artifacts'/'screenshots';out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chromium',headless='--headed' not in sys.argv,
                                  args=['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8765',wait_until='networkidle')
        page.wait_for_function('window.calibrationApp && window.calibrationApp.hasWebGL')
        assert page.locator('#iteration').is_disabled()
        assert page.locator('#robot-view canvas').count()==1
        assert page.locator('#camera-view svg').count()==1
        assert page.evaluate('window.calibrationApp.stage')==0
        page.screenshot(path=str(out/'01-observe.png'),full_page=True)
        page.locator('#next-stage').click()
        assert page.evaluate('window.calibrationApp.stage')==1
        assert '3D' in page.locator('#residual-inspector').inner_text()
        page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(100)
        page.screenshot(path=str(out/'02-compare.png'),full_page=True)

        # The Compare action really calls the solver endpoint.
        with page.expect_response('**/api/demo') as response:
            page.locator('#next-stage').click()
        assert response.value.status==200
        page.wait_for_function('window.calibrationApp.stage===2 && !window.calibrationApp.busy')
        page.locator('#iteration').fill('0')
        before=page.evaluate('JSON.stringify(window.calibrationApp.result.samples[window.calibrationApp.sampleIndex].observed_camera)')
        page.locator('#iteration').fill(page.locator('#iteration').get_attribute('max'))
        after=page.evaluate('JSON.stringify(window.calibrationApp.result.samples[window.calibrationApp.sampleIndex].observed_camera)')
        assert before==after
        assert page.locator('#error-chart svg').count()==1
        page.locator('#observation').fill('4')
        assert page.evaluate('window.calibrationApp.iteration')>0
        page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(100)
        page.screenshot(path=str(out/'03-calibrate.png'),full_page=True)

        page.locator('[data-stage="3"]').click()
        assert page.evaluate('window.calibrationApp.result.samples[window.calibrationApp.sampleIndex].split')=='validation'
        page.locator('#observation').fill(page.locator('#observation').get_attribute('max'))
        assert page.evaluate('window.calibrationApp.result.samples[window.calibrationApp.sampleIndex].split')=='validation'
        page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(100)
        page.screenshot(path=str(out/'04-validate.png'),full_page=True)
        with page.expect_download() as download:page.locator('#export-button').click()
        model=json.loads(Path(download.value.path()).read_text())
        assert len(model['model']['left']['joint_offsets_rad'])==7

        # Real-data path: uploading a dataset must remove simulation-only claims.
        dataset,_=simulate(count=24,noise_mm=0,missing=0,outliers=0)
        with page.expect_response('**/api/calibrate') as response:
            page.locator('#file-input').set_input_files({'name':'observations.json','mimeType':'application/json','buffer':json.dumps(dataset).encode()})
        assert response.value.status==200
        page.wait_for_function('window.calibrationApp.result.source==="imported" && !window.calibrationApp.busy')
        page.locator('#iteration').fill(page.locator('#iteration').get_attribute('max'))
        assert 'Simulation geometry' not in page.locator('#metrics').inner_text()
        assert page.evaluate('window.calibrationApp.result.final.validation_rms_mm')<1e-5
        page.locator('#landmark-select').select_option('7')
        page.locator('#arm-select').select_option('1')
        assert page.locator('#residual-inspector').inner_text()

        # Demo settings use the numerical endpoint, not a cosmetic update.
        page.locator('#data-settings summary').click()
        page.locator('#noise').fill('0');page.locator('#missing').select_option('0');page.locator('#outliers').select_option('0')
        page.locator('#run-demo').click()
        page.wait_for_function('window.calibrationApp.result.source==="synthetic" && window.calibrationApp.result.settings.noise_mm===0 && !window.calibrationApp.busy')
        assert page.evaluate('window.calibrationApp.result.final.truth_rms_mm')<1e-5
        page.locator('#iteration').fill('0')
        page.set_viewport_size({'width':390,'height':844})
        page.locator('[data-stage="1"]').click()
        page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(150)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(out/'05-mobile.png'),full_page=True)
        assert page.request.post('http://127.0.0.1:8765/api/demo',data={'noise_mm':100}).status==400
        assert page.request.post('http://127.0.0.1:8765/api/calibrate',data={}).status==400
        assert page.request.get('http://127.0.0.1:8765/guide.html').status==200
        assert not errors,errors
        browser.close()
        print('Browser checks passed: four stages, fixed observations, held-out-only validation, both fit endpoints, import/export, mobile layout, WebGL.')


if __name__=='__main__':main()
