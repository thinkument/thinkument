# Crystal

Crystal demonstrates the direct, one-publication/one-pack pattern. It is
independent of Metal's widget library, aesthetic slots, renderer catalogues,
and chromeset generator. It exports a checked HAI `appPack` with its own
browser module and styles.

Crystal's computation sheet is mixed:

- `crystal.seed` and `crystal.consumer` are Layer A/B service-ready strict
  Python widgets, declared in `widgets.py`.
- `crystal.json_ideator` is a Layer C widget compiled from
  `json_widgets/crystal_ideator.json` and added to Crystal's local widget
  registry. Layer C lowers to the same strict lifecycle and typed profile.

`declare_pack.py` defines the manifest and registrar. `publication.py` pairs
that manifest with `TypedAuthoringProfile('crystal')` and publishes one row.
`rendering/index.js` and `styles.css` provide Crystal's own standalone
presentation. The typed flow example demonstrates a wire from `crystal.seed`
to `crystal.consumer` without chrome-specific metadata.

Crystal is the cross-funnel example: Python is available for imperative
strict widgets, while JSON is the preferred portable form when the approved
operation vocabulary expresses the behavior. Both authoring forms use the
same strict profile and runtime lifecycle. See the
[authoring funnel guide](../../../../about/scaling_app_packs/1_layers_of_authoring_funneling.MD).
