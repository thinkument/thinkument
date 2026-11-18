from .contracts import *
from .contracts import __all__ as _contract_exports
from .context import bind_provider_v1


def __getattr__(name):
    if name in ("EconomicsWidgetMixin", "EconomicsPoweredDatumLifecycleWidget"):
        from . import template_thinkwidget_economics_powered as mould

        return getattr(mould, name)
    raise AttributeError(name)


__all__ = _contract_exports + [
    "bind_provider_v1",
    "EconomicsWidgetMixin",
    "EconomicsPoweredDatumLifecycleWidget",
]
