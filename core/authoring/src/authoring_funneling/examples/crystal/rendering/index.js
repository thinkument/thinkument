// Crystal independent app pack presentation bed (zero dependencies on Metal)
import { defineAppPackV1 } from '../../hai/app_packs.js';

function element(documentRef, tag, attrs = {}, text = null) {
  const node = documentRef.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, String(value));
  }
  if (text !== null) {
    node.textContent = String(text);
  }
  return node;
}

function updateFillComposer(documentRef, datumId, microName, value) {
  // HAI owns the public dispatch path. Keep its checked fill composer in sync
  // with this presentation control; the normal STEP button then validates and
  // dispatches the resulting userFill action.
  const includes = documentRef.querySelectorAll?.('[data-hai-micro-include]') ?? [];
  const values = documentRef.querySelectorAll?.('[data-hai-micro-value]') ?? [];
  for (const input of values) {
    if (input.getAttribute('data-datum-id') !== datumId
      || input.getAttribute('data-micro-name') !== microName) continue;
    input.value = JSON.stringify(value);
  }
  for (const include of includes) {
    if (include.getAttribute('data-datum-id') === datumId
      && include.getAttribute('data-micro-name') === microName) {
      include.checked = true;
    }
  }
}

function renderMicro({ documentRef, micro, value, widget }) {
  const container = element(documentRef, 'div', {
    'data-hai-micro': `${widget.datum_id}.${micro.name}`,
    class: 'crystal-micro',
  });
  const label = element(documentRef, 'label', {}, micro.label ?? micro.name);
  const isNumber = micro.type === 'integer';
  const control = element(documentRef, 'input', {
    type: isNumber ? 'number' : 'text',
    'data-micro-name': micro.name,
    'data-datum-id': widget.datum_id,
    'aria-label': micro.label ?? micro.name,
  });
  control.value = value != null ? String(value) : '';
  control.addEventListener('input', () => {
    let next = control.value;
    if (isNumber) {
      next = control.value === '' ? null : Number(control.value);
    }
    updateFillComposer(documentRef, widget.datum_id, micro.name, next);
  });
  container.append(label, control);
  return container;
}

function renderWidget(args) {
  const { documentRef, widget } = args;
  const card = element(documentRef, 'article', {
    'data-hai-widget-card': '1',
    'data-hai-widget-id': widget.datum_id,
    class: 'crystal-card',
  });
  const title = element(documentRef, 'h3', { class: 'crystal-title' }, widget.shell?.title ?? widget.datum_id);
  card.append(title);
  const microsContainer = element(documentRef, 'div', { class: 'crystal-micros' });
  for (const micro of widget.micros ?? []) {
    microsContainer.append(
      renderMicro({
        documentRef,
        micro,
        value: widget.fill?.[micro.name],
        widget,
      })
    );
  }
  card.append(microsContainer);
  return card;
}

export default defineAppPackV1({
  id: 'crystal',
  styleUrls: [new URL('./styles.css', import.meta.url).href],
  callables: { widget: renderWidget },
  widgetRenderers: {
    'crystal.seed': renderWidget,
    'crystal.consumer': renderWidget,
    'crystal.json_ideator': renderWidget,
  },
});
