from __future__ import annotations

"""Compatibility import for the now server-neutral sufficience DOM helpers.

Task C adds a Django scripted-live-run membrane.  The direct DOM grammar is not
Flask-specific, so its single implementation now lives with the server-agnostic
scripted live-run atelier and both hosts import that implementation.
"""

from ways_to_run.live_run_DOMscripted_atelier.sufficience_dom_support import *  # noqa: F401,F403
from ways_to_run.live_run_DOMscripted_atelier.sufficience_dom_support import __all__
