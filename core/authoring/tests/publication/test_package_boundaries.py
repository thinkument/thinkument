"""Enforce production import direction independently of host integration tests."""
import ast
from pathlib import Path
import subprocess
import sys

def test_framework_production_has_no_creativity_or_financial_imports():
    root=Path(__file__).resolve().parents[4].parent
    for path in (root/'thinkument/framework/think-app/src').rglob('*.py'):
        if 'app_pack_publication_registrar' in path.parts or 'epsilinesTM_serveragnostic/subapps' in str(path):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names=[node.module or ''] if isinstance(node,ast.ImportFrom) else [n.name for n in node.names] if isinstance(node,ast.Import) else []
            assert not any(n.split('.')[0] in {'authoring_funneling','service_tracked_widget_computation','service_ready_typed_PSMCW_authoring','_funneled_apps','_creativity_registrar','storagics','wallet_economics'} for n in names),path

def test_core_imports_without_service_or_eager_examples():
    subprocess.run([sys.executable,'-c',"import sys; import authoring_funneling.a_typed_PSMCW_authoring; assert not any(n == 'home' or n.startswith('home.') or '.examples' in n or n == 'authoring_funneling.a_typed_PSMCW_authoring.program' for n in sys.modules)"],check=True)

def test_no_core_imports_service_or_central_registrar():
    import authoring_funneling
    src=Path(authoring_funneling.__file__).resolve().parent.parent
    for name in ['authoring_pure_backend_no_funnel', 'authoring_funneling', 'authoring_funneling_templates', 'authoring_funneling_preloaded_assets']:
        for path in (src/name).rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.ImportFrom):
                    assert (node.module or '').split('.')[0] not in {'home','public','web_RESTful'},path
