import { widgetsContainer, annotate, applyAesthetics } from './aesthetics.js';
import * as micros from './micros.js';
import * as widgets from './widgets.js';
import { MICRO_RENDERERS, WIDGET_RENDERERS } from './catalogue.js';
import { defineAppPackV1 } from '../../../../bootstrap_higher_app/hai/app_packs.js';

export const AESTHETIC_SLOTS = Object.freeze(['widgetFrame','microFrame','label','control','notification',
  'widgetNotification','widgetsContainer','page','outers','noReadWidget','noWriteWidget','brand']);

export function validateAesthetics(aesthetics) {
  if (!aesthetics || typeof aesthetics !== 'object') throw new TypeError('Expected an aesthetic collection.');
  for (const slot of AESTHETIC_SLOTS) {
    if (typeof aesthetics[slot] !== 'function' || aesthetics[slot].constructor?.name === 'AsyncFunction') {
      throw new TypeError(`Aesthetic slot ${slot} must be a synchronous function.`);
    }
  }
  return Object.freeze({ ...aesthetics });
}

export function composePack(id, aestheticCollection, styleUrl) {
  const aesthetics = validateAesthetics(aestheticCollection);
  const microRenderers = Object.freeze(Object.fromEntries(Object.entries(MICRO_RENDERERS).map(([type, fn]) => {
    if (typeof micros[fn] !== 'function') throw new TypeError(`Missing micro renderer ${fn}`);
    return [type, micros[fn]];
  })));
  function renderMicro(args) {
    const render = microRenderers[args.micro.type];
    if (!render) throw new TypeError(`Micro type ${args.micro.type} is not admitted by the library.`);
    return annotate(render({ ...args, aesthetics, annotate }), { ...args, part:'micro', section:'widgets' });
  }
  const widgetRenderers = Object.freeze(Object.fromEntries(Object.entries(WIDGET_RENDERERS).map(([key, fn]) => {
    if (typeof widgets[fn] !== 'function') throw new TypeError(`Missing widget renderer ${fn}`);
    return [key, args => annotate(widgets[fn]({ ...args, aesthetics, renderMicro, annotate }), { ...args, part:'widget', section:'widgets' })];
  })));
  // HAI's renderer_key is optional. Standard mechanics also handle shells with no custom key.
  const widget = args => widgets.standardWidget({ ...args, aesthetics, renderMicro, annotate });
  return defineAppPackV1({ id,
    styleUrls: [new URL('./aesthetics.css', import.meta.url).href, String(styleUrl)],
    callables: { widget, widgetsContainer:args => widgetsContainer(args,aesthetics), ...Object.fromEntries(['notification','widgetNotification',
      'outers','noReadWidget','noWriteWidget'].map(slot => [slot, args => {
        const result = aesthetics[slot]({ ...args, annotate });
        return slot.endsWith('Widget') ? annotate(result, { ...args, part:'widget', section:'widgets' }) : result;
      }])),
      page:args => {
        annotate(args.shell, { part:'page' });
        const result = aesthetics.page({ ...args, annotate });
        for (const node of args.shell.querySelectorAll?.('[data-hai-outer]') ?? []) {
          annotate(node, { part:'section', section:node.getAttribute('data-hai-outer') });
        }
        for (const [selector, section] of [['[data-hai-stage]', 'stage'],
          ['[data-hai-composer]', 'composer'], ['[data-hai-global-notifications]', 'notifications']]) {
          for (const node of args.shell.querySelectorAll?.(selector) ?? []) annotate(node, { part:'section', section });
        }
        applyAesthetics(args);
        return result;
      } },
    widgetRenderers, epsRoutes: {},
    outers: { brand: { render:args => aesthetics.brand({ ...args, annotate }),
      powder: { new_page: true, widget_refresh: false, epsilon: false } } },
  });
}
