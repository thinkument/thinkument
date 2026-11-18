"""Physical browser resources and their stable public namespace."""
from pathlib import Path

STATIC_ROOT = Path(__file__).with_name("static").resolve()
STATIC_PREFIX = "_funneled_apps/examples/metal/shared_rendering"
