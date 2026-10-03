"""Regenerate all five experiments, JSON evidence, and a standalone summary plot."""
from pathlib import Path
import json
import time
import numpy as np
from experiments import ghost, redundancy, active_selection, observability, compliance

ROOT = Path(__file__).resolve().parent


def export_plot(data):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'figure.facecolor': '#0c1422', 'axes.facecolor': '#111e30',
                         'text.color': '#e1e9f6', 'axes.labelcolor': '#a8b8ce',
                         'xtick.color': '#a8b8ce', 'ytick.color': '#a8b8ce',
                         'axes.edgecolor': '#354258', 'font.size': 10,
                         'savefig.facecolor': '#0c1422'})
    cyan, amber = '#5ce1cc', '#ffbf69'
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), layout='constrained')
    ax = axes.flat[0]
    g = data['ghost']
    ax.plot([f['metrics']['position_mm'] for f in g['frames']], 'o-', color=cyan)
    ax.set(title='01  Fix the ghost arm', xlabel='Accepted optimizer iteration', ylabel='Held-out position RMS [mm]')
    ax = axes.flat[1]
    r = data['redundancy']
    for key, label, color in [('before', 'Before', amber), ('after', 'Replanned after fit', cyan)]:
        trace = np.array(r[key]['trace_mm'])
        ax.plot(np.linspace(0, 1, len(trace)), np.linalg.norm(trace, axis=1), label=label, color=color)
    ax.set(title='02  Hold the hand, move the elbow', xlabel='Trajectory progress', ylabel='Physical hand drift [mm]')
    ax.legend()
    ax = axes.flat[2]
    curve = data['active']['curve']
    x = [r['count'] for r in curve]
    ax.plot(x, [r['greedy_mm'] for r in curve], 'o-', color=cyan, label='Information gain')
    ax.plot(x, [r['random_median_mm'] for r in curve], 'o-', color=amber, label='Random median')
    ax.fill_between(x, [r['random_q25_mm'] for r in curve], [r['random_q75_mm'] for r in curve], color=amber, alpha=.15)
    ax.set(title='03  Choose the next pose', xlabel='Measurement budget', ylabel='Held-out position RMS [mm]', yscale='log')
    ax.legend()
    ax = axes.flat[3]
    colors = [amber, cyan, '#f48cae', '#aaa4fa']
    for (key, case), color in zip(data['observability']['cases'].items(), colors):
        ax.plot(range(1, 11), np.maximum(case['singular_values'], 1e-9), 'o-', color=color, label=key.replace('_', ' '))
    ax.set(title='04  What is observable?', xlabel='Singular value index', ylabel='Whitened sensitivity / degree', yscale='log')
    ax.legend(fontsize=8)
    ax = axes.flat[4]
    curve = data['compliance']['curve']
    for key, label, color in [('geometry_mm', 'Unloaded rigid fit', amber), ('mixed_geometry_mm', 'Mixed-load rigid fit', '#aaa4fa'), ('elastic_mm', 'Compliance fit', cyan)]:
        ax.plot([r['payload'] for r in curve], [r[key] for r in curve], 'o-', label=label, color=color)
    ax.set(title='05  Geometry or arm flex?', xlabel='Payload [kg]', ylabel='Held-out position RMS [mm]')
    ax.legend(fontsize=8)
    ax = axes.flat[5]
    ax.axis('off')
    ax.text(.05, .88, 'CALIBRATION LAB', fontsize=22, fontweight='bold', color=cyan)
    ax.text(.05, .75, 'Seven joints. Five experiments.', fontsize=16)
    ax.text(.05, .62, 'Generic arm • synthetic observations\nKnown camera and base frames\nPosition and orientation evaluated separately\nFixed seeds • held-out configurations\n\nEducational model, not 1X NEO hardware results.', fontsize=11, linespacing=1.8, va='top')
    for ax in axes.flat[:5]:
        ax.grid(alpha=.15)
    fig.suptitle('A measured hand pose becomes a better robot model', fontsize=21)
    fig.savefig(ROOT / 'results' / 'overview.png', dpi=160)
    fig.savefig(ROOT / 'results' / 'overview.pdf')
    plt.close(fig)


def main():
    data = {'meta': {'model': 'Generic seven-revolute-joint arm; not NEO geometry',
                     'version': 1, 'units': 'meters, radians internally; mm, degrees in displays',
                     'evaluation': 'Noise-free synthetic truth on 160 unseen joint configurations'}}
    for key, experiment in [('ghost', ghost), ('redundancy', redundancy),
                            ('active', active_selection), ('observability', observability),
                            ('compliance', compliance)]:
        start = time.monotonic()
        data[key] = experiment()
        print(f'{key}: completed in {time.monotonic()-start:.2f}s', flush=True)
    (ROOT / 'results').mkdir(exist_ok=True)
    (ROOT / 'results' / 'data.json').write_text(json.dumps(data, allow_nan=False, separators=(',', ':')))
    export_plot(data)
    print('Saved results/data.json, overview.png, and overview.pdf')


if __name__ == '__main__':
    main()
