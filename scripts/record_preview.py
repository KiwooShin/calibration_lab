"""Record the real app's fitted example as MP4 and GIF (Playwright + ffmpeg)."""
import argparse
from pathlib import Path
import subprocess
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8770/calibration-lab/')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts' / 'preview')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    frames = args.output / 'frames'
    frames.mkdir(exist_ok=True)
    fps = 6
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chromium', headless=False, args=[
            '--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        page = browser.new_page(viewport={'width':1280, 'height':960}, device_scale_factor=1)
        page.goto(args.url)
        page.wait_for_function('window.calibrationApp && window.calibrationApp.hasWebGL')
        # Compact the real interface for a legible film; no measurement changes.
        page.add_style_tag(content='''
            .intro,.top-actions,.stage-explanation p,.evidence-grid,.fit-details,.settings,footer{display:none}
            .topbar{height:65px;padding:0 28px}.topbar .brand{font-size:21px}
            main{padding:18px 28px 0}.step{min-height:65px;padding:12px 16px}
            .stage-explanation{margin:16px 0}.stage-explanation h2{font-size:24px}
            .metric{padding:13px 18px}.metric-value{margin:7px 0}
            #robot-view{min-height:330px}#camera-view svg{max-height:330px}
            .scrubber{padding:12px 18px}.scrubber-top{margin-bottom:9px}
            .orbit-note{display:none}
        ''')
        page.locator('.brand').evaluate("e => e.textContent = 'Head-camera self-calibration'")
        page.locator('.topbar').evaluate("e => e.insertAdjacentHTML('beforeend', '<span style=\"color:#94a9c1;font-size:13px\">RECORDED APP DEMO · SYNTHETIC OBSERVATIONS</span>')")
        captions = [
            '1. Observe: the camera sees the arms in several poses.',
            '2. Compare: orange FK predictions miss the green observations.',
            '3. Calibrate: change the model; keep observations fixed.',
            '4. Validate: check the correction on unseen poses.'
        ]
        page.evaluate("document.body.insertAdjacentHTML('beforeend', '<div id=\"film-caption\" style=\"position:fixed;bottom:0;left:0;right:0;padding:16px 28px;background:#1b3431;border-top:1px solid #5e9b88;font-size:19px;color:#e7edf7\"></div>')")
        frame = 0
        for stage, seconds in enumerate([4, 4, 8, 6]):
            page.locator(f'[data-stage="{stage}"]').click()
            page.locator('#film-caption').evaluate('(e,t) => e.textContent=t', captions[stage])
            max_iteration = int(page.locator('#iteration').get_attribute('max'))
            for tick in range(seconds * fps):
                if stage == 0:
                    page.locator('#observation').fill(str(min(8, tick // 3)))
                elif stage == 1:
                    page.locator('#observation').fill('8')
                elif stage == 2:
                    # Accepted optimizer iterates, with a short hold at each end.
                    iteration = round(max_iteration * min(1, max(0, (tick - 6) / 30)))
                    page.locator('#iteration').fill(str(iteration))
                elif stage == 3:
                    page.locator('#observation').fill(str(min(5, tick // 6)))
                page.wait_for_timeout(45)
                page.screenshot(path=str(frames / f'{frame:04d}.png'))
                frame += 1
        browser.close()
    source = str(frames / '%04d.png')
    encoders = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True, check=True).stdout
    codec = ['-c:v', 'libx264', '-crf', '22'] if 'libx264' in encoders else ['-c:v', 'libopenh264', '-b:v', '2500k']
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(fps), '-i', source,
                    '-frames:v', str(frame), *codec, '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart', str(args.output / 'workflow.mp4')], check=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(args.output / 'workflow.mp4'),
                    '-filter_complex', 'fps=6,scale=768:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=3',
                    '-loop', '0', str(args.output / 'workflow.gif')], check=True)
    # Compare stage gives the poster meaningful discrepancies before playback.
    (args.output / 'poster.png').write_bytes((frames / '0030.png').read_bytes())
    print(f'Exported {frame / fps:.0f}s MP4 and GIF to {args.output}')


if __name__ == '__main__':
    main()
