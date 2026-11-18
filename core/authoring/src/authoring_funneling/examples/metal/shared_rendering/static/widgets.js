import { place, annotate } from './aesthetics.js';
// Widget display mechanics shared by every chrome and every standard library widget.
export function standardWidget({ documentRef, widget, ctx, api, aesthetics, renderMicro }) {
  const card = annotate(aesthetics.widgetFrame({ documentRef, widget, ctx, annotate }), { ctx, widget, part: 'widget', section: 'widgets' });
  const micros = documentRef.createElement('div');
  annotate(micros, { ctx, widget, part: 'micros', section: 'widgets' });
  place('micros', widget.shell?.paquete_micro_placement, micros);
  for (const micro of widget.micros ?? []) {
    micros.append(renderMicro({ documentRef, micro, value: widget.fill?.[micro.name], widget, ctx, api, aesthetics }));
  }
  card.append(micros);
  return card;
}
