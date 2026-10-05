import json,os,sys
from pathlib import Path
from buildkit import Session
s=Session('/workspace/input','/workspace/output',2);s.prepare()
py=Path('/workspace/testvenv/bin/python')
s.run([sys.executable,'-m','venv','/workspace/testvenv'],cwd='/workspace',phase='probe',name='venv',timeout=300)
s.run([str(py),'-m','pip','install','--no-index','--find-links=/opt/wheelhouse','/artifacts/tensorflow_cpu-2.18.0-cp312-cp312-linux_x86_64.whl'],cwd='/workspace',phase='probe',name='install_own_wheel',timeout=300)
reports=s.output/'upstream_test_reports';reports.mkdir()
s.test('softmax_source_script',[str(py),str(s.src/'tensorflow/python/kernel_tests/nn_ops/softmax_op_test.py'),'--xml_output_file='+str(reports/'softmax.xml')],cwd=s.consumer,parser='unittest_cases',env={'CUDA_VISIBLE_DEVICES':'','TF_CPP_MIN_LOG_LEVEL':'2'},timeout=300)
s.test('load_capture_source_script',[str(py),str(s.src/'tensorflow/python/saved_model/load_test.py'),'--xml_output_file='+str(reports/'load.xml')],cwd=s.consumer,parser='unittest_cases',env={'CUDA_VISIBLE_DEVICES':'','TF_CPP_MIN_LOG_LEVEL':'2','TESTBRIDGE_TEST_ONLY':'*LoadTest.test_capture_variables*'},timeout=300)
print('ORIGINAL_SOURCE_SCRIPT_XML',[(p.name,p.stat().st_size) for p in reports.iterdir()],flush=True)
