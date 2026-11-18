from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from _thinkprogram._iomicrosTM.core.api_fills import (
    build_datum_validator,
    coerce_accepted_macro_fill_for_datum,
    datum_fill_data_meets_its_structural_micros_shell,
)
from __exceptions.engine import (
    InvalidExternalFillError,
)

from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    _MISSING,
)

from _thinkprogram._iomicrosTM.tiny_helpers import (
    DeadJSONError,
    assert_dead_json,
)


def _invalidate_fill_basic_logistical_problems(
        self,
        fill,
        datum_widgets_on_this_span,
        touched_datum_widgets_that_indeed_need_fills,
        *,
        signal=None,
    ):

    signal_target = ""
    if isinstance(signal, Mapping):
        signal_target = str(signal.get("datum_id") or "").strip()

    if fill is None and not signal_target:
        self.last_error = {
            "__SPAN__": "missing fill payload"
        }
        return False

    if fill is None:
        fill = {}

    if not isinstance(fill, Mapping):
        raise InvalidExternalFillError(
            "fill must be an object"
        )

    self._enforce_manual_fill_size_limits(fill=fill)

    try:
        assert_dead_json(
            fill,
            path="external_fill",
        )
    except DeadJSONError as e:
        raise InvalidExternalFillError(str(e)) from e

    # fill structure, while it met the basic logistical gate,
    # addresses datums not on this span
    extraneous = sorted(
        [
            str(k)
            for k in fill.keys()
            if str(k) not in set(datum_widgets_on_this_span)
        ]
    )
    if extraneous:
        self.last_error = {
            "__SPAN__": (
                f"extraneous fields: {extraneous}"
            )
        }
        return False

    for fid in datum_widgets_on_this_span:
        if fid in fill and fid not in touched_datum_widgets_that_indeed_need_fills:
            raise InvalidExternalFillError("A datum that does not need inputs was given some")

    if fill and not touched_datum_widgets_that_indeed_need_fills:
        self.last_error = {
            "__SPAN__": (
                "manual fill touched no pending fields"
            )
        }
        return False

    if signal_target:
        if signal_target not in set(datum_widgets_on_this_span):
            self.last_error = {
                "__SPAN__": (
                    f"signal target not on current span: {signal_target!r}"
                )
            }
            return False

        if signal_target not in set(touched_datum_widgets_that_indeed_need_fills):
            self.last_error = {
                "__SPAN__": (
                    f"signal target is not pending: {signal_target!r}"
                )
            }
            return False

    return True


def _manual_datum_validators_backend_for_span_v1(
    *,
    cache: Any,
    datums_by_id: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Cache-backed validator backend for this span's datum shells.

    This owns the repeated transition concern:

        datum shell
            -> DatumFillValidator backend
            -> cached validators_by_id

    The validator object is intentionally reused through the manual IO cache
    because it is derived from the datum's micros and macro validators. The
    transition algorithm should not need to care how validator instances are
    built, stored, or lazily completed.
    """

    validators_raw = (
        cache.get("validators_by_id")
        if isinstance(cache, Mapping)
        else {}
    )

    if isinstance(validators_raw, dict):
        validators_by_id = validators_raw
    else:
        validators_by_id: Dict[str, Any] = {}
        if isinstance(cache, dict):
            cache["validators_by_id"] = validators_by_id

    for fid in datums_by_id:
        validator = validators_by_id.get(fid)
        if validator is None:
            datum = datums_by_id.get(fid)
            validator = build_datum_validator(datum)
            validators_by_id[fid] = validator

    return validators_by_id


def _candidate_manual_datum_fill_for_transition_v1(
    *,
    fid: str,
    fill: Mapping[str, Any],
    existing: Mapping[str, Any],
) -> Any:
    """
    Resolve this datum's candidate fill for the transition attempt.

    Existing semantics are preserved:

      - if the external fill omitted this datum, use its existing value
      - if both existing and provided are mappings, shallow-merge provided over existing
      - otherwise provided replaces existing
    """

    base_existing = existing.get(fid, None)
    provided = fill.get(fid, _MISSING)

    if provided is _MISSING:
        return base_existing

    if (
        isinstance(base_existing, Mapping)
        and isinstance(provided, Mapping)
    ):
        merged = dict(base_existing)
        merged.update(dict(provided))
        return merged

    return provided


def _partially_validate_manual_datum_fill_for_transition_v1(
    *,
    fid: str,
    datum: Mapping[str, Any],
    validator: Any,
    fill: Mapping[str, Any],
    existing: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    The transition-time validation/coercion pipeline for one touched datum.

    This helper establishes the canonical runtime invariant:

        raw existing/provided fill
            -> candidate macro fill
            -> partial validator backend pass on raw data
            -> dead-JSON membrane
            -> accepted-fill coercion using datum micros + MICRO_TYPES
            -> dead-JSON membrane
            -> validator backend pass on canonical/coerced data
            -> dead-JSON membrane
            -> structural micros-shell satisfaction

    After this function returns, "partially_validated" means:

        validator-accepted + micro-type-canonicalized

    Therefore datomaton widgets should receive canonical values in
    q["partial_fill"], while q["raw_fill"] remains the original submitted data.
    """

    candidate = _candidate_manual_datum_fill_for_transition_v1(
        fid=fid,
        fill=fill,
        existing=existing,
    )

    partially_validated_raw = (
        validator.parse_and_validate_fill(
            raw=candidate,
            enforce_required_micros=False,
            enforce_micro_lambdas=True,
            enforce_macro_lambdas=True,
        )
    )
    assert_dead_json(
        partially_validated_raw,
        path=(
            "manual_partially_validated_raw"
            f"[{fid}]"
        ),
    )

    partially_coerced = (
        coerce_accepted_macro_fill_for_datum(
            datum=datum,
            accepted=partially_validated_raw,
        )
    )
    assert_dead_json(
        partially_coerced,
        path=(
            "manual_partially_coerced"
            f"[{fid}]"
        ),
    )

    partially_validated = (
        validator.parse_and_validate_fill(
            raw=partially_coerced,
            enforce_required_micros=False,
            enforce_micro_lambdas=True,
            enforce_macro_lambdas=True,
        )
    )
    assert_dead_json(
        partially_validated,
        path=(
            "manual_partially_validated_canonical"
            f"[{fid}]"
        ),
    )

    structurally_satisfied = (
        datum_fill_data_meets_its_structural_micros_shell(
            datum,
            partially_validated,
        )
    )

    return {
        "candidate": candidate,
        "partially_validated": partially_validated,
        "structurally_satisfied": structurally_satisfied,
    }


def _fully_validate_manual_datum_fill_for_commit_v1(
    *,
    fid: str,
    validator: Any,
    partially_validated: Any,
    datum: Optional[Mapping[str, Any]] = None,
) -> Any:
    """
    Final required-micros validation for a datum that is about to commit.

    Partial validation above is allowed to tolerate missing required micros
    because lifecycle widgets may need to inspect incomplete data. This helper
    marks the explicit boundary where the fill becomes commit-worthy.

    If datum is supplied, this helper also re-applies accepted-fill coercion and
    revalidates the canonical result. The datum parameter is optional for
    backwards compatibility with existing call sites; however, new call sites
    should pass datum=datum so the final commit gate is independently canonical.
    """

    validated_raw = (
        validator.parse_and_validate_fill(
            raw=partially_validated,
            enforce_required_micros=True,
            enforce_micro_lambdas=True,
            enforce_macro_lambdas=True,
        )
    )
    assert_dead_json(
        validated_raw,
        path=f"manual_validated_raw[{fid}]",
    )

    if datum is None:
        return validated_raw

    validated_coerced = (
        coerce_accepted_macro_fill_for_datum(
            datum=datum,
            accepted=validated_raw,
        )
    )
    assert_dead_json(
        validated_coerced,
        path=f"manual_validated_coerced[{fid}]",
    )

    validated = (
        validator.parse_and_validate_fill(
            raw=validated_coerced,
            enforce_required_micros=True,
            enforce_micro_lambdas=True,
            enforce_macro_lambdas=True,
        )
    )
    assert_dead_json(
        validated,
        path=f"manual_validated_canonical[{fid}]",
    )

    return validated