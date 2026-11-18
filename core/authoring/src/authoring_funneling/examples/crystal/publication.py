"""Direct publication for Crystal, fully independent of Metal."""
from pathlib import Path
from bootstrap_higher_app.app_pack_contract import PackPublicationRowV1
from authoring_funneling.a_typed_PSMCW_authoring.profile import TypedAuthoringProfile
from .declare_pack import app_pack_manifest_v1, register_app_pack_v1
from .widgets import widget_rows

STATIC_ROOT = Path(__file__).with_name("rendering").resolve()
STATIC_PREFIX = "_funneled_apps/examples/crystal/rendering"


def authoring_profile_v1():
    return TypedAuthoringProfile("crystal", profile_id="crystal.typed_ports.v1", widget_ids=widget_rows())


def publication_rows():
    return (PackPublicationRowV1(app_pack_manifest_v1, authoring_profile_v1),)


def shared_static_roots_v1():
    """Crystal has no auxiliary static roots; its assets mount via its manifest."""
    return ()
