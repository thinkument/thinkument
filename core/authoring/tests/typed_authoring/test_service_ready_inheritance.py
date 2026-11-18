"""The typed base uses the real cooperative service execution mould."""
from epsilinesTM_serveragnostic.subapps import ServiceReadyWidget
from epsilinesTM_serveragnostic.subapps.analytics import AnalyticaPoweredDatumLifecycleWidget
from authoring_funneling.a_typed_PSMCW_authoring import StrictServiceWidget
from authoring_funneling.examples.metal.shared_widgets.base import LibraryWidget

def test_single_combined_mould_in_typed_mro():
    assert issubclass(StrictServiceWidget, ServiceReadyWidget)
    assert issubclass(LibraryWidget, StrictServiceWidget)
    assert StrictServiceWidget.__mro__.count(AnalyticaPoweredDatumLifecycleWidget) == 1
    assert StrictServiceWidget.execute_vendor_operation_v1 is ServiceReadyWidget.execute_vendor_operation_v1

def test_pure_typed_widget_needs_no_host_bindings():
    from support.typed_second_pack import Echo, profile, draft
    from authoring_funneling.a_typed_PSMCW_authoring import compile_strict_program
    body = compile_strict_program(draft()['P'])['run']['program']
    args = {**body['widgets']['echo'].get('args', {}), **body['flow'][0]['overrides']['args']['echo']}
    events = []
    widget = Echo(q={}, emit=lambda payload, **kw: events.append(kw['name']) or {})
    widget._on_mount({}, {'fill_shell': {'id': 'echo', 'args': args, 'micros': []}, 'current_fills': {}}, {}, {})
    assert events == ['audit-ins', 'audit-outs']
    assert widget.outputs.read('result', 'message') == 'Independent $pack'
