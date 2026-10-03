"""Export a fully interactive static site: python build_static.py --output PATH."""
import argparse
import json
from pathlib import Path
import shutil
from calibration.dataset import simulate
from calibration.solver import calibrate

ROOT = Path(__file__).resolve().parent


def build(output):
    output = Path(output).resolve()
    if output == ROOT or output in ROOT.parents or output == ROOT / 'web':
        raise ValueError('Choose a separate output directory')
    shutil.copytree(ROOT / 'web', output, dirs_exist_ok=True)
    html = (output / 'index.html').read_text().replace(
        '<html lang="en">', '<html lang="en" data-compute="browser">')
    html = html.replace('<footer><span>', '<footer><span>Runs in your browser · ')
    (output / 'index.html').write_text(html)
    data, truth = simulate()
    (output / 'demo.json').write_text(json.dumps(calibrate(data, 'synthetic', truth), allow_nan=False))
    sources = {name: (ROOT / 'calibration' / name).read_text()
               for name in ['__init__.py', 'geometry.py', 'dataset.py', 'solver.py']}
    (output / 'python-sources.json').write_text(json.dumps(sources))
    # Also works on a dedicated GitHub Pages repo without Jekyll.
    (output / '.nojekyll').touch()
    print(f'Static browser lab exported to {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='artifacts/site')
    build(parser.parse_args().output)
