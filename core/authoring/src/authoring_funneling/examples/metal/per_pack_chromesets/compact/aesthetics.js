import standard from '../metal_standard/aesthetics.js';

export function widgetFrame(args) {
  const card = standard.widgetFrame(args);
  card.classList.add('chromed-widget-compact');
  return card;
}
export function page({ shell, renderDefaultPage }) {
  shell.setAttribute('data-chrome', 'compact');
  return renderDefaultPage();
}

// Reuse is explicit; every collection still supplies every required slot.
export default Object.freeze({ ...standard, widgetFrame, page });
