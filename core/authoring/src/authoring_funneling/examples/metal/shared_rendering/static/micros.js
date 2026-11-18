import { annotate } from './aesthetics.js';
// Micro mechanics. A descriptor reaches this function intact, never merged with widget args.
export function element(documentRef, tag, attrs = {}, text = null) {
  const node = documentRef.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (text !== null) node.textContent = String(text);
  return node;
}

function editor({ documentRef, micro, value, widget, ctx, aesthetics }, kind) {
  const attrs = { 'data-datum-id': widget.datum_id, 'data-micro-name': micro.name };
  const include = element(documentRef, 'input', { ...attrs, type: 'checkbox',
    'data-hai-micro-include': '1', 'aria-label': `include ${micro.name}` });
  const serialized = element(documentRef, 'textarea', { ...attrs, hidden: '', 'data-hai-micro-value': '1' });
  serialized.value = JSON.stringify(value ?? null);
  const control = element(documentRef, kind === 'select' ? 'select' : 'input', {
    ...attrs, 'data-library-editor': kind, 'aria-label': micro.label ?? micro.name,
    ...(kind === 'select' ? {} : { type: kind === 'integer' ? 'number' : 'text' }),
  });
  if (kind === 'select') {
    control.append(element(documentRef, 'option', { value: '' }, 'Choose…'));
    for (const option of micro.options ?? []) {
      // Options remain typed JSON values, including strings with dollar signs.
      control.append(element(documentRef, 'option', { value: JSON.stringify(option) }, String(option)));
    }
    control.value = value == null ? '' : JSON.stringify(value);
  } else {
    control.value = value == null ? '' : String(value);
  }
  if (kind === 'integer') {
    control.setAttribute('step', '1');
    if (micro.minimum !== undefined) control.setAttribute('min', micro.minimum);
    if (micro.maximum !== undefined) control.setAttribute('max', micro.maximum);
  }
  control.addEventListener('input', () => {
    let next;
    if (kind === 'select') next = control.value === '' ? null : JSON.parse(control.value);
    else if (kind === 'integer') {
      next = control.value === '' ? null : Number(control.value);
      if (next !== null && !Number.isInteger(next)) {
        control.setCustomValidity('Enter an integer.');
        include.checked = false;
        return;
      }
      control.setCustomValidity('');
    } else next = control.value;
    serialized.value = JSON.stringify(next);
    include.checked = true;
  });
  aesthetics.control({ documentRef, control, micro, widget, ctx, annotate });
  annotate(control, { ctx, widget, micro, part: 'control', section: 'widgets' });
  const row = annotate(aesthetics.microFrame({ documentRef, micro, widget, ctx, annotate }), { ctx, widget, micro, part: 'micro', section: 'widgets' });
  row.append(annotate(aesthetics.label({ documentRef, micro, widget, ctx, annotate }), { ctx, widget, micro, part: 'label', section: 'widgets' }), include, control, serialized);
  // The unmodified descriptor is inspectable without serializing the whole runtime blanket.
  row.microDescriptor = micro;
  return row;
}

export function text(args) { return editor(args, 'text'); }
export function integer(args) { return editor(args, 'integer'); }
export function select(args) { return editor(args, 'select'); }
