export function widgetFrame({ documentRef, widget }) {
  const card = documentRef.createElement('article');
  card.dataset.widgetId = widget.datum_id;
  card.textContent = widget.shell?.title ?? widget.datum_id;
  return card;
}

export function control({ control }) { control.classList.add('metal-control'); }

export default Object.freeze({ widgetFrame, control });
