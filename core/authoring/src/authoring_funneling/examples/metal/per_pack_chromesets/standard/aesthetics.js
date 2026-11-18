import { element } from '../../../_funneled_apps/examples/metal/shared_rendering/micros.js';

export function widgetFrame({ documentRef, widget }) {
  const card = element(documentRef, 'article', { class: 'chromed-widget',
    'data-hai-widget-card': '1', 'data-hai-widget-id': widget.datum_id });
  card.append(element(documentRef, 'h3', {}, widget.shell?.title ?? widget.datum_id));
  return card;
}
export function microFrame({ documentRef, micro, widget }) {
  return element(documentRef, 'div', { class: 'chromed-micro', 'data-hai-micro': `${widget.datum_id}.${micro.name}` });
}
export function label({ documentRef, micro }) {
  return element(documentRef, 'span', { class: 'chromed-label' }, micro.label ?? micro.name);
}
export function control({ control }) { control.classList.add('chromed-control'); }
export function notification({ documentRef, container, event, messageType }) {
  container.append(element(documentRef, 'p', { class: 'chromed-notification', 'data-hai-notification': messageType },
    event?.payload?.message?.text ?? event?.payload?.text ?? JSON.stringify(event)));
}
export function widgetNotification(args) { notification(args); }
export function widgetsContainer({ container, widgets, renderWidgetCard }) {
  for (const widget of widgets) container.append(renderWidgetCard(widget));
}
export function page({ shell, renderDefaultPage }) {
  shell.setAttribute('data-chrome', 'standard');
  return renderDefaultPage();
}
export function outers({ renderDefaultOuters }) { return renderDefaultOuters(); }
export function noReadWidget({ documentRef, widget }) {
  return element(documentRef, 'article', { class: 'chromed-widget', 'data-hai-widget-card': '1',
    'data-hai-widget-id': widget.datum_id, 'data-hai-no-read': '1' }, 'Hidden by role projection');
}
export function noWriteWidget(args) {
  const card = widgetFrame(args);
  card.setAttribute('data-hai-no-write', '1');
  card.append(element(args.documentRef, 'pre', { 'data-hai-readonly-fill': '1' }, JSON.stringify(args.widget.fill)));
  return card;
}
export function brand({ documentRef, container, appPack }) {
  container.replaceChildren(element(documentRef, 'strong', { 'data-hai-brand': '1' }, appPack.id));
}

export default Object.freeze({ widgetFrame, microFrame, label, control, notification, widgetNotification,
  widgetsContainer, page, outers, noReadWidget, noWriteWidget, brand });
