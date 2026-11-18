from __future__ import annotations


from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from _thinkprogram._iomicrosTM.tiny_helpers import (
    JSONShapeBase,
    norm_tags,
    shallow_dc,
)


from typing import Any, Dict, List, Mapping, Optional

# =============================================================================
# _multiframespec dataclass
# =============================================================================


@dataclass
class MultiframeSpec(JSONShapeBase):
    """
    Canonical dead-JSON multi-frame form specification.

    Span mappings are deliberately open extension envelopes. Validation here
    covers only the structural fields consumed by App Table itself.
    """

    tokens: Optional[
        Dict[str, Dict[str, Any]]
    ] = None
    datums: List[Dict[str, Any]] = None  # type: ignore[assignment]
    frames: List[Dict[str, Any]] = None  # type: ignore[assignment]
    boxed: Optional[Dict[str, Any]] = None
    fills: Optional[Dict[str, Any]] = None
    refs: Optional[
        List[Dict[str, Any]]
    ] = None
    app_form_id: Optional[str] = None

    def __post_init__(self) -> None:
        raw = {
            "tokens": self.tokens,
            "datums": self.datums or [],
            "frames": self.frames or [],
            "boxed": self.boxed,
            "fills": self.fills or {},
            "refs": self.refs or [],
            "app_form_id": self.app_form_id,
        }

        canon = normalize__multiframespec_json(raw)

        self.tokens = canon.get("tokens")
        self.datums = (
            canon.get("datums") or []
        )
        self.frames = (
            canon.get("frames") or []
        )
        self.boxed = canon.get("boxed")
        self.fills = (
            canon.get("fills") or {}
        )
        self.refs = canon.get("refs") or []
        self.app_form_id = canon.get(
            "app_form_id"
        )

    def _validate(self) -> None:
        def _mget(
            obj: Any,
            key: str,
            default: Any = None,
        ) -> Any:
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(
                obj,
                key,
                default,
            )

        def _assert_id(
            value: Any,
            path: str,
        ) -> str:
            if value is None:
                raise AssertionError(
                    f"{path} must be a "
                    "non-empty string; got null"
                )

            normalized = str(value)
            if not normalized.strip():
                raise AssertionError(
                    f"{path} must be a "
                    "non-empty string; "
                    f"got {value!r}"
                )

            if (
                normalized.strip().lower()
                == "none"
            ):
                raise AssertionError(
                    f"{path} must not be "
                    f"'None'; got {value!r}"
                )

            return normalized

        def _assert_tags(
            obj: Any,
            path: str,
        ) -> None:
            raw_tags = _mget(
                obj,
                "tags",
                None,
            )
            if raw_tags is None:
                return

            if isinstance(raw_tags, str):
                raw_tags = [raw_tags]

            assert isinstance(
                raw_tags,
                list,
            ), (
                f"{path}.tags must be "
                "a list of strings"
            )

            for tag in raw_tags:
                assert (
                    isinstance(tag, str)
                    and tag.strip()
                ), (
                    f"{path}.tags has "
                    "empty/non-string tag"
                )

        assert self.datums is not None, (
            "datums must be provided "
            "(use [] if empty)"
        )
        assert self.frames is not None, (
            "frames must be provided "
            "(use [] if empty)"
        )
        assert isinstance(
            self.datums,
            list,
        ), "datums must be a list"
        assert isinstance(
            self.frames,
            list,
        ), "frames must be a list"

        datum_ids: List[str] = []

        for datum_index, datum in enumerate(
            self.datums or []
        ):
            datum_path = (
                f"datums[{datum_index}]"
            )
            _assert_tags(
                datum,
                datum_path,
            )

            datum_id = _assert_id(
                _mget(datum, "id", None),
                f"{datum_path}.id",
            )
            datum_ids.append(datum_id)

            _assert_id(
                _mget(
                    datum,
                    "title",
                    None,
                ),
                f"{datum_path}.title",
            )

            micros = _mget(
                datum,
                "micros",
                None,
            )
            assert isinstance(
                micros,
                list,
            ), (
                f"{datum_id}: micros "
                "must be a list"
            )

            for micro_index, micro in enumerate(
                micros or []
            ):
                micro_path = (
                    f"{datum_path}."
                    f"micros[{micro_index}]"
                )
                _assert_tags(
                    micro,
                    micro_path,
                )
                _assert_id(
                    _mget(
                        micro,
                        "name",
                        None,
                    ),
                    f"{micro_path}.name",
                )

        assert (
            len(datum_ids)
            == len(set(datum_ids))
        ), "duplicate datum ids"

        for datum in self.datums or []:
            datum_id = str(
                _mget(
                    datum,
                    "id",
                    "<datum>",
                )
            )
            micros = list(
                _mget(
                    datum,
                    "micros",
                    [],
                )
                or []
            )

            micro_names: List[str] = []
            for micro in micros:
                micro_name = _assert_id(
                    _mget(
                        micro,
                        "name",
                        None,
                    ),
                    (
                        f"{datum_id}: "
                        "micro name"
                    ),
                )
                micro_names.append(
                    micro_name
                )

            assert (
                len(micro_names)
                == len(set(micro_names))
            ), (
                f"{datum_id}: duplicate "
                "micro names"
            )

            for micro in micros:
                micro_name = str(
                    _mget(
                        micro,
                        "name",
                        "",
                    )
                    or ""
                )
                micro_type = str(
                    _mget(
                        micro,
                        "type",
                        "text",
                    )
                    or ""
                )
                assert micro_type, (
                    f"{datum_id}."
                    f"{micro_name}: "
                    "micro type must be "
                    "non-empty"
                )

        for frame_index, frame in enumerate(
            self.frames or []
        ):
            frame_path = (
                f"frames[{frame_index}]"
            )
            _assert_tags(
                frame,
                frame_path,
            )
            _assert_id(
                _mget(
                    frame,
                    "id",
                    None,
                ),
                f"{frame_path}.id",
            )

            spans = (
                _mget(
                    frame,
                    "spans",
                    None,
                )
                or []
            )
            assert isinstance(
                spans,
                list,
            ), (
                f"{frame_path}.spans "
                "must be a list"
            )

            for span_index, span in enumerate(
                spans
            ):
                span_path = (
                    f"{frame_path}."
                    f"spans[{span_index}]"
                )
                assert isinstance(
                    span,
                    dict,
                ), (
                    f"{span_path} must "
                    "be a mapping"
                )

                _assert_tags(
                    span,
                    span_path,
                )

                span_id = _assert_id(
                    _mget(
                        span,
                        "id",
                        None,
                    ),
                    f"{span_path}.id",
                )

                owns_raw = list(
                    _mget(
                        span,
                        "owns",
                        [],
                    )
                    or []
                )
                owns: List[str] = []

                for owns_index, owned in enumerate(
                    owns_raw
                ):
                    owns.append(
                        _assert_id(
                            owned,
                            (
                                f"{span_path}."
                                f"owns[{owns_index}]"
                            ),
                        )
                    )

                for owned_id in owns:
                    assert (
                        owned_id
                        in datum_ids
                    ), (
                        f"span {span_id}: "
                        "unknown datum id "
                        f"{owned_id!r} -- "
                        "ids available are: "
                        f"{datum_ids}"
                    )

                # Deliberately do not inspect any remaining span keys.
                #
                # Canonicalization preserves them as dead JSON. Their names,
                # value schemas, and semantics belong to whichever higher
                # layer authored or consumes them.

    def validate(self) -> None:
        self._validate()



def normalize__multiframespec_json(raw: Mapping[str, Any]) -> Dict[str, Any]:
    def _assert_nonempty_str(val: Any, path: str) -> str:
        if val is None:
            raise ValueError(f"{path} must be a non-empty string; got null")

        s = str(val)
        if not s.strip() or s.strip().lower() == "none":
            raise ValueError(f"{path} must be a non-empty string; got {val!r}")

        return s

    def _humanize_id(s: str) -> str:
        return s.replace("_", " ").replace(".", " ").strip().title()

    spec: Dict[str, Any] = deepcopy(dict(raw or {}))

    datums_in = list(spec.get("datums") or [])
    datums_out: list[Dict[str, Any]] = []

    for i, d in enumerate(datums_in):
        d_dict = shallow_dc(d)

        did = _assert_nonempty_str(d_dict.get("id"), f"datums[{i}].id")

        title_raw = d_dict.get("title")
        title = (
            _humanize_id(did)
            if title_raw is None or not str(title_raw).strip()
            else str(title_raw)
        )

        micros_in = list(d_dict.get("micros") or [])
        micros_out: list[Dict[str, Any]] = []

        for j, m in enumerate(micros_in):
            m_dict = shallow_dc(m)

            mname_raw = m_dict.get("name")
            mname = (
                "value"
                if mname_raw is None or not str(mname_raw).strip()
                else str(mname_raw)
            )
            m_dict["name"] = mname

            mtype_raw = m_dict.get("type", "text")
            m_dict["type"] = str(mtype_raw or "text")

            m_dict["tags"] = norm_tags(m_dict.get("tags"))
            micros_out.append(m_dict)

        d_dict["id"] = did
        d_dict["title"] = title
        d_dict["micros"] = micros_out
        d_dict["tags"] = norm_tags(d_dict.get("tags"))
        datums_out.append(d_dict)

    spec["datums"] = datums_out

    frames_in = list(spec.get("frames") or [])
    frames_out: list[Dict[str, Any]] = []

    for fi, fr in enumerate(frames_in):
        fr_dict = shallow_dc(fr)

        fr_id = _assert_nonempty_str(fr_dict.get("id"), f"frames[{fi}].id")
        fr_dict["id"] = fr_id

        spans_in = list(fr_dict.get("spans") or [])
        spans_out: list[Dict[str, Any]] = []

        for si, sp in enumerate(spans_in):
            sp_dict = shallow_dc(sp)

            sp_id = _assert_nonempty_str(
                sp_dict.get("id"),
                f"frames[{fi}].spans[{si}].id",
            )

            owns_in = list(sp_dict.get("owns") or [])
            owns_out = [
                _assert_nonempty_str(
                    o,
                    f"frames[{fi}].spans[{si}].owns[{oi}]",
                )
                for oi, o in enumerate(owns_in)
            ]

            sp_dict["id"] = sp_id
            sp_dict["owns"] = owns_out

            if sp_dict.get("role") is not None:
                sp_role = _assert_nonempty_str(
                    sp_dict.get("role"),
                    f"frames[{fi}].spans[{si}].role",
                )
                sp_dict["role"] = sp_role

            sp_dict["tags"] = norm_tags(sp_dict.get("tags"))
            spans_out.append(sp_dict)

        fr_dict["spans"] = spans_out
        fr_dict["tags"] = norm_tags(fr_dict.get("tags"))
        frames_out.append(fr_dict)

    spec["frames"] = frames_out

    spec.setdefault("boxed", None)
    spec.setdefault("fills", {})
    spec.setdefault("refs", [])
    spec.setdefault("tokens", None)
    spec.setdefault("app_form_id", None)

    return spec
