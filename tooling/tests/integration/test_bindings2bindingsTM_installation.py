"""Build and execute the independent-tooling wheel in a fresh Python with no Thinkument."""
import os
from pathlib import Path
import subprocess
import sys
import venv


def test_independent_wheel(tmp_path):
    root=Path(__file__).resolve().parents[2]
    env=dict(os.environ);env.pop('PYTHONPATH',None)
    subprocess.run([sys.executable,'-m','build','--wheel','--no-isolation','--outdir',str(tmp_path/'wheels'),str(root)],check=True,env=env,cwd=tmp_path,capture_output=True)
    venv.EnvBuilder(with_pip=True).create(tmp_path/'environment')
    python=tmp_path/'environment'/'bin'/'python'
    wheel=next((tmp_path/'wheels').glob('*.whl'))
    subprocess.run([str(python),'-m','pip','install','--no-deps',str(wheel)],check=True,env=env,cwd=tmp_path,capture_output=True)
    subprocess.run([str(python),'-I','-c',"""
import sys
from importlib import metadata
from bindings2bindingsTM import compile_binding, BindingPlan, D, List, Dict, Nullable, infer_expression_type
p=compile_binding({'entries':List(Dict({'title':str}))},List(str),D.map(D.ref('entries'),D.text('$',D.item('title'))))
assert BindingPlan.from_json(p.to_json()).evaluate({'entries':[{'title':'independent'}]})==['$independent']
assert infer_expression_type({'numbers':List(int)},D.sum(D.ref('numbers'))).kind=='int'
q=compile_binding({'groups':List(Dict({'prefix':str,'numbers':List(int)}))},List(List(str)),
  D.map(D.ref('groups'),D.map(D.filter(D.item('numbers'),D.gt(D.item(),1)),
  D.text(D.outer('prefix'),D.item()))))
assert BindingPlan.from_json(q.to_json()).evaluate({'groups':[{'prefix':'n','numbers':[1,2,3]}]})==[['n2','n3']]
assert compile_binding({},int,D.to_int(3.0)).evaluate({})==3
assert compile_binding({'s':List(float)},float,D.sum(D.ref('s'))).evaluate({'s':[]})==0.0
assert compile_binding({'s':str},str,D.sugar('$s')).evaluate({'s':'portable'})=='portable'

assert not any(n.startswith(('DOMScriptrTM','playwright','_thinkprogram','thinkument')) for n in sys.modules)
import importlib.util
assert importlib.util.find_spec('stripe_pay') is None
assert not any('stripe' in r.lower() or 'decouple' in r.lower() for r in (metadata.requires('independent-tooling') or []))
for name in ('think-app','think-backend','service-innovations'):
    try: metadata.distribution(name)
    except metadata.PackageNotFoundError: pass
    else: raise AssertionError(name+' unexpectedly installed')
"""],check=True,env=env,cwd=tmp_path,capture_output=True)
