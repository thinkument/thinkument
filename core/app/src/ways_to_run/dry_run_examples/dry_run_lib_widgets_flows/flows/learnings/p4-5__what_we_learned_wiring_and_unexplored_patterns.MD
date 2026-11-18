# Task B — exact wiring understanding

## Formal answers proved by Program 4

A consuming widget does **not** see a global dictionary containing every prior
widget's latest attributes. It sees a dictionary keyed by the **authored wire
names** at:

```python
fill_data["fill_shell"]["args"]["__kernel"]["past_wires"]
```

For a wire declared with `multiplicity="one"`, that wire slot is one
runtime-write row mapping. For `multiplicity="many"`, it is a list of
runtime-write row mappings. An optional wire that resolves no history is absent.

The exact lifecycle value is:

```python
row["value"]
```

The exact class-authored state attributes are:

```python
row["value"]["state"]
```

That state mapping is flat. A widget must know the source widget's documented
state attribute name when it wants one particular semantic fact, such as
`representative_number` or `target_number`. It does not need to guess the
container path, and it may inspect or pass onward the complete state mapping.

The helper `wire_state_index_v1(fill_shell)` converts the public runtime packet
into a uniform convenience view:

```python
{
    "<wire_name>": {
        "container_kind": "one_row" | "row_list",
        "row_count": 1,
        "rows": [
            {
                "source": {
                    "public_step_name": "...",
                    "datum_id": "...",
                },
                "state": {
                    "<source widget state attr>": "<value>",
                },
            },
        ],
    },
}
```

The helper retains a list under `rows` even for a one-wire, while preserving the
formal source shape in `container_kind`.

`from={"self": "previous"}` is only a ThinkProgramTM authoring shorthand. Once
lowered and resolved, it appears in the same `past_wires` mapping under the
authored wire name. There is no separate runtime “auto-wire” container.

The rows are the selected historical runtime writes, not a magical live object.
With `select="latest"`, they are the latest matching selected rows at the time
the step is built. The lifecycle state in each row is therefore the committed
state of that source appearance.

Authored widget args remain at:

```python
fill_data["fill_shell"]["args"]
```

The platform-owned runtime observation is nested at:

```python
fill_data["fill_shell"]["args"]["__kernel"]
```

Program 4 emits these facts as a `wiring.proof` datum event during mount. A
downstream listener hears that event between the surrounding
`controller.loop.start` and `controller.loop.end`, exactly like other widget
lifecycle messages.




## Rare cases closed by P5

Repeated appearances with history.select="all". Most programs need onlythe latest prior value, which is why earlier demos use latest. P5 invokes thesame logical daily widget twice and then consumes both physical runtime-writerows through one many-wire. This proves that “same logical widget kept alive”is a useful creative model while history still preserves distinct physicalappearances.

Optional wire absence becoming presence. Optional wires are normallydesigned away in simple examples. The first completeness-probe appearance hasno prior self row, so self_previous is absent. The second appearance receivesthe first probe row through the same ordinary wire grammar.

Missing-signal fallback. Named @signal_catcher methods are clearer andsafer, so they should remain the default. A widget may nevertheless declaremissing_signal_handler_outcome="fallback_to_fill_handler". P5 sends anunrecognized signal-only action and proves that _on_fill receives it withouta special catcher.

Prefill hints versus pre-computed fills. Prefill is presentation/defaultguidance. Pre-computed fills are the widget's working committed overlay used toderive changed_fills. P5 first supplies a note as a hint, then preserves thatnote as pre-computed data after a rejected token. Resubmitting the same notewith a corrected token makes only the token appear in changed_fills.

Direct custom events. self.message(...) is the normal UI message artery,but widgets may also emit any dead-JSON event name/channel/audience. P5 emitscompleteness.proof during mount and the poller hears it inside the controllerenvelope.

Eventless malformed request rejection. Earlier rows intentionally containvalid action packets. P5 adds a malformed signal.info value. Productionnormalization raises before controller start, the canonical high-water does notmove, and polling from the prior cursor returns no events. This is categoricallydifferent from lifecycle semantic rejection, which is an admitted controllerenvelope.

Remaining intentional exclusions

Role-modulated release and write grants depend on session role metadata andbelong in the role sheet. FunkTM generated dispatches, role cycling, and chainreceipts belong in the FunkTM sheet. Multi-process exclusion belongs to thehosting transaction tests. These are not missing ordinary ThinkProgramTM orThinkWidgetTM creative seams.