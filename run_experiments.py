"""Regenerate all five experiments, JSON evidence, and a standalone summary plot."""
from pathlib import Path
import json
import time
import numpy as np
from experiments import ghost, redundancy, active_selection, observability, compliance
from self_observation import self_observation

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


def export_self_observation(data):
    import matplotlib.pyplot as plt
    from self_observation import project, to_camera
    d = data['selfvision']
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), layout='constrained')
    teal, amber, purple = '#5ce1cc', '#ffbf69', '#aaa4fa'
    sample = d['samples'][4]
    ax = axes[0, 0]
    for side in range(2):
        mask = np.array(sample['used'][side])
        seen = np.array(sample['observed_uv'][side])[mask]
        before = project(to_camera(np.array(sample['iterations'][0][side]['landmarks'])))[0][mask]
        after = project(to_camera(np.array(sample['iterations'][-1][side]['landmarks'])))[0][mask]
        ax.scatter(*seen.T, color=teal, s=30, label='Perception' if side == 0 else None)
        ax.scatter(*before.T, color=amber, marker='+', s=45, label='Nominal FK' if side == 0 else None)
        ax.scatter(*after.T, color=purple, marker='x', s=35, label='Calibrated FK' if side == 0 else None)
    ax.set(xlim=(0, 960), ylim=(600, 0), title='Head-camera projection of 3D landmarks', xlabel='u [pixel]', ylabel='v [pixel]')
    ax.legend()
    ax = axes[0, 1]
    for key, label, color in [('landmark_mm', 'All arm + hand landmarks', teal), ('palm_mm', 'Palm centers', amber)]:
        ax.plot([f['metrics'][key] for f in d['frames']], 'o-', color=color, label=label)
    ax.set(title='Generalization to 160 unseen configurations', xlabel='Accepted optimizer iteration', ylabel='Held-out 3D position RMS [mm]')
    ax.legend()
    ax = axes[1, 0]
    labels = [c['label'].replace(' ', '\n', 1) for c in d['comparison']]
    x = np.arange(len(labels))
    ax.bar(x-.17, [c['landmark_mm'] for c in d['comparison']], width=.34, color=teal, label='All landmarks')
    ax.bar(x+.17, [c['palm_mm'] for c in d['comparison']], width=.34, color=amber, label='Palm centers')
    ax.set(xticks=x, xticklabels=labels, title='Same camera frames, different landmark subsets', ylabel='Held-out 3D position RMS [mm]')
    ax.legend()
    ax = axes[1, 1]
    for side, color, label in [(0, teal, 'Left arm'), (1, amber, 'Right arm')]:
        ax.plot(range(1, 8), np.array(d['true_parameters'])[side, :7], '--', color=color, alpha=.5, label=label+' truth')
        ax.plot(range(1, 8), np.array(d['estimated_parameters'])[side, :7], 'o', color=color, label=label+' fit')
    ax.set(title='Recovered encoder offsets (also fits 4 link lengths)', xlabel='Joint index', ylabel='Offset [degrees]')
    ax.legend(ncol=2, fontsize=9)
    for ax in axes.flat:
        ax.grid(alpha=.12)
    fig.suptitle('Self-observation: head-camera positions calibrate both arm chains', fontsize=18)
    fig.supxlabel('Synthetic perception • 2 mm lateral / 4 mm depth noise • 15% dropout + 4% outliers • known camera transform • no orientation input', fontsize=9)
    fig.savefig(ROOT/'results'/'self-observation.png', dpi=160)
    fig.savefig(ROOT/'results'/'self-observation.pdf')
    plt.close(fig)


def main():
    data = {'meta': {'model': 'Generic seven-revolute-joint arm chains; not NEO geometry',
                     'version': 2, 'primary': 'selfvision', 'units': 'meters, radians internally; mm, degrees in displays',
                     'evaluation': 'Noise-free synthetic truth on 160 unseen joint configurations'}}
    for key, experiment in [('selfvision', self_observation), ('ghost', ghost), ('redundancy', redundancy),
                            ('active', active_selection), ('observability', observability),
                            ('compliance', compliance)]:
        start = time.monotonic()
        data[key] = experiment()
        print(f'{key}: completed in {time.monotonic()-start:.2f}s', flush=True)
    (ROOT / 'results').mkdir(exist_ok=True)
    (ROOT / 'results' / 'data.json').write_text(json.dumps(data, allow_nan=False, separators=(',', ':')))
    export_plot(data)
    export_self_observation(data)
    print('Saved results/data.json, overview reports, and primary self-observation reports')


if __name__ == '__main__':
    main()
