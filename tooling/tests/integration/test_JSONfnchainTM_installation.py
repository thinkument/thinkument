"""Install both independent packages into a fresh venv via an isolated wheel.

A build-backend-free PEP427 wheel fixture is constructed for environments without
`build`/`poetry-core`, and the source pyproject packaging includes are verified.
This exercises pip wheel installation and isolated runtime import, but is not a
substitute for a full parent-project Poetry wheel build when backend is installed.
"""
import os
from pathlib import Path
import subprocess
import sys
import venv
import zipfile
import re


def _independent_wheel(root, destination):
    # Standalone minimal wheel fixture of exactly the two independent packages.
    name='independent_tooling'
    dist=f'{name}-0.1.0.dist-info'
    wheel=destination/'independent_tooling-0.1.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for package in ('bindings2bindingsTM','JSONfnchainTM'):
            for file in sorted((root/'src'/package).glob('*.py')):
                z.write(file,f'{package}/{file.name}')
        z.writestr(f'{dist}/WHEEL','Wheel-Version: 1.0\nGenerator: JSONfnchainTM installation test\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
        z.writestr(f'{dist}/METADATA','Metadata-Version: 2.1\nName: independent-tooling\nVersion: 0.1.0\nRequires-Python: >=3.10\n')
        z.writestr(f'{dist}/RECORD','')
    return wheel


def test_wheel_installs_without_thinkument(tmp_path):
    root=Path(__file__).resolve().parents[2]
    config=(root/'pyproject.toml').read_text()
    includes=set(re.findall(r'include\s*=\s*["\']([^"\']+)["\']', config))
    assert {'bindings2bindingsTM','JSONfnchainTM','DOMScriptrTM','serviceCredsTM'}<=includes
    wheel=_independent_wheel(root,tmp_path)
    venv.EnvBuilder(with_pip=True).create(tmp_path/'environment')
    python=(tmp_path/'environment'/('Scripts' if os.name=='nt' else 'bin')/
            ('python.exe' if os.name=='nt' else 'python'))
    env=dict(os.environ); env.pop('PYTHONPATH',None)
    subprocess.run([str(python),'-m','pip','install','--no-deps','--no-index',str(wheel)],
                   check=True,env=env,cwd=tmp_path,capture_output=True)
    subprocess.run([str(python),'-I','-c',r'''
import sys
from bindings2bindingsTM import D, Dict, List, compile_binding
from JSONfnchainTM import FunctionVocab, compile_flow, execute_flow, FlowPlan
v=FunctionVocab()
v.register(name='test.echo',fn=lambda a,c:{'value':a['value']},
           inputs=Dict({'value':str}),output=Dict({'value':str}),version='1')
p=compile_flow({'steps':[{'id':'a','fn':'test.echo','args':{'value':'$parameters.text'}}],
                'returns':'$a.value'},
               {'parameters':Dict({'text':str})},str,v)
assert execute_flow(FlowPlan.from_json(p.to_json(),vocab=v),
                    {'parameters':{'text':'independent'}},vocab=v)=='independent'
assert compile_binding({},int,D.add(1,2)).evaluate({})==3
assert not any(x.startswith(('thinkument','DOMScriptrTM','serviceCredsTM','django','celery','playwright')) for x in sys.modules)
'''],check=True,env=env,cwd=tmp_path,capture_output=True)
