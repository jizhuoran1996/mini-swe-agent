#!/usr/bin/env python3
# Independent consumer for the freshly built ONNX Runtime CPU wheel.
# Runs outside the source tree and validates CPU inference against NumPy.
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from onnx import TensorProto, helper

BIAS = np.array([0.5, -1.0, 0.25, 2.0], dtype=np.float32)


def build_model():
    a = helper.make_tensor_value_info('A', TensorProto.FLOAT, [2, 3])
    b = helper.make_tensor_value_info('B', TensorProto.FLOAT, [3, 4])
    c = helper.make_tensor_value_info('C', TensorProto.FLOAT, [2, 4])
    bias = helper.make_tensor('bias', TensorProto.FLOAT, [4], BIAS.tolist())
    nodes = [
        helper.make_node('MatMul', ['A', 'B'], ['mm']),
        helper.make_node('Add', ['mm', 'bias'], ['add_out']),
        helper.make_node('Relu', ['add_out'], ['C']),
    ]
    graph = helper.make_graph(nodes, 'f10_graph', [a, b], [c], initializer=[bias])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 17)])
    model.ir_version = 8
    return model


def native_libraries():
    package = Path(ort.__file__).resolve().parent
    found = []
    for path in sorted(package.rglob('*')):
        if path.is_file() and '.so' in path.name:
            found.append({'name': str(path.relative_to(package)), 'bytes': path.stat().st_size,
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', default=None)
    args = parser.parse_args()

    model = build_model()
    payload = model.SerializeToString()
    assert payload, 'serialized graph must be nonempty'
    onnx.checker.check_model(model)

    session = ort.InferenceSession(payload, providers=['CPUExecutionProvider'])
    providers = session.get_providers()
    assert providers[0] == 'CPUExecutionProvider', providers
    inputs = {value.name for value in session.get_inputs()}
    assert inputs == {'A', 'B'}, sorted(inputs)
    assert session.get_outputs()[0].name == 'C'

    rng = np.random.default_rng(20240517)
    trials = []
    for trial in range(2):
        a = rng.standard_normal((2, 3)).astype(np.float32)
        b = rng.standard_normal((3, 4)).astype(np.float32)
        got = session.run(['C'], {'A': a, 'B': b})[0]
        want = np.maximum(a @ b + BIAS, 0.0).astype(np.float32)
        assert got.shape == (2, 4) and got.dtype == np.float32, (got.shape, got.dtype)
        assert np.allclose(got, want, atol=1e-5, rtol=1e-5), (got, want)
        trials.append({'trial': trial, 'max_abs_err': float(np.max(np.abs(got - want)))})

    libraries = native_libraries()
    assert libraries, 'the installed wheel must ship a native shared library'
    report = {'onnxruntime_module': ort.__file__, 'onnxruntime_version': ort.__version__,
              'onnx_module': onnx.__file__, 'providers': providers,
              'graph_ops': [node.op_type for node in model.graph.node],
              'graph_sha256': hashlib.sha256(payload).hexdigest(),
              'native_libraries': libraries, 'trials': trials}
    print('CONSUMER_OK ' + json.dumps(report['trials']))
    print('native libraries: ' + json.dumps([lib['name'] for lib in libraries]))
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
