"""Independent Ta SNAP trajectory, restart, RDF and energy validation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np


def digest(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()


def frames(path):
    lines = path.read_text().splitlines()
    result = []
    index = 0
    while index < len(lines):
        assert lines[index] == 'ITEM: TIMESTEP'
        step = int(lines[index + 1])
        assert lines[index + 2] == 'ITEM: NUMBER OF ATOMS'
        count = int(lines[index + 3])
        assert lines[index + 4].startswith('ITEM: BOX BOUNDS pp pp pp')
        box = np.array([list(map(float, line.split())) for line in lines[index + 5:index + 8]])
        columns = lines[index + 8].split()[2:]
        atoms = np.array([list(map(float, line.split())) for line in lines[index + 9:index + 9 + count]])
        assert atoms.shape == (count, len(columns)) and np.isfinite(atoms).all()
        assert np.array_equal(atoms[:, columns.index('id')], np.arange(1, count + 1))
        result.append({'step': step, 'box': box, 'atoms': atoms, 'columns': columns})
        index += 9 + count
    return result


def coordinates(frame):
    return frame['atoms'][:, [frame['columns'].index(c) for c in ('x', 'y', 'z')]]


def atom_error(expected, actual):
    assert expected['columns'] == actual['columns']
    differences = expected['atoms'] - actual['atoms']
    lengths = expected['box'][:, 1] - expected['box'][:, 0]
    for axis, name in enumerate(('x', 'y', 'z')):
        column = expected['columns'].index(name)
        differences[:, column] -= lengths[axis] * np.rint(differences[:, column] / lengths[axis])
    return float(np.max(np.abs(differences)))


def rdf(frame):
    positions = coordinates(frame)
    lengths = frame['box'][:, 1] - frame['box'][:, 0]
    distances = []
    for i in range(len(positions) - 1):
        delta = positions[i + 1:] - positions[i]
        delta -= lengths * np.rint(delta / lengths)
        distances.extend(np.linalg.norm(delta, axis=1))
    counts, edges = np.histogram(distances, bins=120, range=(0, 6))
    shells = 4 * np.pi / 3 * np.diff(edges ** 3)
    return (edges[:-1] + edges[1:]) / 2, 2 * counts * np.prod(lengths) / (len(positions) ** 2 * shells)


def validate(output, inputs):
    original = frames(output / 'trajectory.dump')
    continued = frames(output / 'trajectory_resume.dump')
    assert [f['step'] for f in original] == list(range(0, 101, 10)), 'missing initial trajectory frames'
    assert [f['step'] for f in continued] == list(range(100, 151, 10)), 'incorrect restart steps'
    for frame in original + continued:
        assert len(frame['atoms']) == 128, 'wrong BCC Ta atom count'
        assert np.all(frame['atoms'][:, frame['columns'].index('type')] == 1)
        assert np.allclose(frame['box'][:, 1] - frame['box'][:, 0], 4 * 3.316, atol=1e-10)
    assert atom_error(original[-1], continued[0]) < 1e-12, 'restart changed positions or velocities'
    assert np.max(np.abs(coordinates(original[-1]) - coordinates(original[0]))) > 1e-6, 'no actual dynamics'
    assert np.max(np.abs(coordinates(continued[-1]) - coordinates(continued[0]))) > 1e-6, 'no actual continuation'
    for trajectory, name in [(original, 'rdf.csv'), (continued, 'rdf_resume.csv')]:
        expected_r, expected_g = rdf(trajectory[-1])
        delivered = np.genfromtxt(output / name, delimiter=',', names=True)
        assert np.allclose(delivered['r_angstrom'], expected_r, atol=5e-7)
        assert np.allclose(delivered['g_r'], expected_g, atol=5e-7), 'RDF differs from independent pair counts'
    run = json.loads((output / 'run.json').read_text())
    assert run['status'] == 'completed' and run['parameters']['steps'] == 100
    assert run['parameters']['nrep'] == 4 and run['parameters']['ensemble'] == 'NVE'
    for name, value in run['upstream'].items():
        assert value == digest(inputs / name), 'potential/binary provenance mismatch'
    for name in ['initial.data', 'final.restart', 'final_resume.restart']:
        assert (output / name).stat().st_size > 100
    thermodynamics = np.genfromtxt(output / 'thermo.csv', delimiter=',', names=True)
    assert np.array_equal(thermodynamics['Step'], np.arange(0, 101, 10))
    assert np.isfinite(thermodynamics['TotEng']).all()
    drift = float(np.max(np.abs(thermodynamics['TotEng'] - thermodynamics['TotEng'][0])))
    assert drift < 1e-3, 'NVE energy drift exceeds fixed debug tolerance'
    return {'atoms': 128, 'initial_steps': 100, 'resumed_steps': 50, 'energy_drift_ev_per_atom': drift}


def reference(inputs, output, destination):
    destination.mkdir(parents=True)
    for name in ['Ta06A.snap', 'Ta06A.snapcoeff', 'Ta06A.snapparam']:
        shutil.copy2(inputs / 'lammps/potentials' / name, destination / name)
    script = '\n'.join([
        'units metal', f'read_data {output / "initial.data"}', 'include Ta06A.snap',
        'timestep 0.5e-3', 'neighbor 1.0 bin', 'neigh_modify every 1 delay 0 check yes',
        'fix integrate all nve', 'thermo 10', 'thermo_style custom step temp pe ke etotal press vol',
        'thermo_modify norm yes', 'dump independent all custom 10 reference.dump id type x y z vx vy vz',
        'dump_modify independent sort id format float %.17g', 'run 150',
    ]) + '\n'
    (destination / 'reference.in').write_text(script)
    command = [str(inputs / 'lammps/bin/lmp'), '-k', 'on', 'g', '1', '-sf', 'kk', '-pk', 'kokkos', 'newton', 'on', 'neigh', 'half', '-in', 'reference.in']
    result = subprocess.run(command, cwd=destination, text=True, capture_output=True, timeout=180)
    (destination / 'stdout.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert 'KOKKOS mode' in result.stdout and 'is enabled' in result.stdout and 'GPU' in result.stdout
    expected = frames(destination / 'reference.dump')
    delivered = frames(output / 'trajectory.dump') + frames(output / 'trajectory_resume.dump')[1:]
    assert len(expected) == len(delivered) == 16
    max_error = max(atom_error(e, a) for e, a in zip(expected, delivered))
    assert max_error < 1e-8, 'independent uninterrupted GPU trajectory does not match restart delivery'
    return {'independent_gpu_frames': 16, 'max_reference_atom_error': max_error}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('task_id', nargs='?', default='GPUv1-F06')
    parser.add_argument('--input', type=Path, default=Path('/workspace/input'))
    parser.add_argument('--artifacts', type=Path, default=Path('/artifacts/output'))
    args = parser.parse_args()
    assert args.task_id == 'GPUv1-F06'
    destination = Path('/workspace/evaluation')
    destination.mkdir(exist_ok=True)
    report = validate(args.artifacts, args.input)
    report.update(reference(args.input, args.artifacts, destination / 'independent_reference'))
    # The same validator must reject missing frames, altered IDs and wrong RDF.
    negative = destination / 'negative'
    shutil.copytree(args.artifacts, negative)
    rejected = []
    for name, contents in [
        ('trajectory.dump', (negative / 'trajectory.dump').read_text().replace('ITEM: TIMESTEP\n100\n', 'ITEM: TIMESTEP\n90\n')),
        ('rdf.csv', 'r_angstrom,g_r\n0.025,0\n'),
        ('run.json', json.dumps({**json.loads((negative / 'run.json').read_text()), 'status': 'incomplete'})),
    ]:
        path = negative / name
        original = path.read_text()
        path.write_text(contents)
        try:
            validate(negative, args.input)
        except (AssertionError, ValueError, IndexError):
            rejected.append(name)
        else:
            raise AssertionError('negative control was accepted: ' + name)
        finally:
            path.write_text(original)
    report.update({'passed': True, 'negative_controls_rejected': rejected, 'reference_large_tested': False})
    (destination / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
