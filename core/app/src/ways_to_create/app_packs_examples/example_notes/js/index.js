const text = (value) => String(value ?? "");

const element = (documentRef, tag, attrs = {}, textContent = null) => {
  const node = documentRef.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    node.setAttribute(name, String(value));
  }
  if (textContent !== null) node.textContent = String(textContent);
  return node;
};

const renderNoteWidget = ({ documentRef, widget, api }) => {
  const card = element(documentRef, "article", {
    "data-hai-widget-card": "1",
    "data-hai-widget-id": widget.datum_id,
    "data-hai-renderer": "example_notes.note.v1",
    class: "hai-widget hai-example-note",
  });

  card.append(
    element(
      documentRef,
      "h3",
      { class: "hai-widget-title" },
      widget.args.title || widget.datum_id,
    ),
  );

  const current = widget.fill && typeof widget.fill === "object"
    ? text(widget.fill.text)
    : "";
  const input = element(documentRef, "textarea", {
    "data-hai-note-editor": "1",
    "data-datum-id": widget.datum_id,
    placeholder: widget.args.placeholder || "Write a note",
  });
  input.value = current;
  input.disabled = !widget.access.write;

  const save = element(
    documentRef,
    "button",
    {
      type: "button",
      "data-hai-note-save": "1",
      "data-datum-id": widget.datum_id,
    },
    "Save note",
  );
  save.disabled = !widget.access.write;
  save.addEventListener("click", async () => {
    const A = {
      action: "STEP",
      userFill: {
        [widget.datum_id]: {
          text: input.value,
        },
      },
      userSignal: null,
    };
    const checked = api.validateDispatch(A);
    if (!checked.ok) {
      api.presentLocalReceipt(checked);
      return;
    }
    api.presentLocalReceipt(checked);
    api.presentDispatchResult(await api.dispatch(A));
  });

  card.append(input, save);

  if (widget.runtime_state.last_text) {
    card.append(
      element(
        documentRef,
        "p",
        { "data-hai-note-last-text": "1" },
        `Backend state: ${widget.runtime_state.last_text}`,
      ),
    );
  }

  return card;
};

const renderNotesBrand = ({ documentRef, container, ctx }) => {
  container.replaceChildren(
    element(
      documentRef,
      "strong",
      { "data-hai-example-notes-brand": "1" },
      `Example Notes / ${ctx.session.role ?? "roleless"}`,
    ),
  );
};

export const appPack = Object.freeze({
  kind: "app_pack_mould_app_pack_v1",
  id: "example_notes",
  styleUrls: Object.freeze([
    new URL("./style.css", import.meta.url).href,
  ]),
  callables: Object.freeze({}),
  widgetRenderers: Object.freeze({
    "example_notes.note.v1": renderNoteWidget,
  }),
  epsRoutes: Object.freeze({
    "example_notes.saved": "widget",
  }),
  defaultEpsRoute: null,
  outers: Object.freeze({
    brand: Object.freeze({
      render: renderNotesBrand,
      powder: Object.freeze({
        new_page: true,
        widget_refresh: false,
        epsilon: false,
      }),
    }),
  }),
});

export default appPack;
