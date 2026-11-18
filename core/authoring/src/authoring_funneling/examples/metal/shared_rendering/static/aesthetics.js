// Central declarations are projected from aesthetics.py into catalogue.js.
import { PLACEMENT_AXES, PLACEMENT_DEFAULTS, SEMANTIC_TARGETS, MICRO_TABLES, RENDERABLE_PARTS } from './catalogue.js';

export function publicStep(step) {
  return step?.public_step_name ?? null;
}

// Receives only role-projected models; never recovers identities from authored sources.
export function annotate(node, { ctx, widget, micro, part, section, step } = {}) {
  if (!node?.setAttribute) return node;
  if (part && !RENDERABLE_PARTS.includes(part)) throw new TypeError(`Unknown paquete part ${part}`);
  const values = { part, section, step: publicStep(step ?? ctx?.view?.step),
    widget: widget?.datum_id, widget_type: widget?.widget_type,
    micro: micro?.name, micro_type: micro?.type, micro_table: MICRO_TABLES[micro?.type] };
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null) node.setAttribute(SEMANTIC_TARGETS[key], value);
  }
  return node;
}

export function vertical({ container }) { container.setAttribute('data-paquete-layout', 'vertical'); }
export function horizontal({ container }) { container.setAttribute('data-paquete-layout', 'horizontal'); }
const layouts = { vertical, horizontal };

export function place(axis, member, container) {
  const selected = member ?? PLACEMENT_DEFAULTS[axis];
  const fn = layouts[PLACEMENT_AXES[axis]?.[selected]];
  if (typeof fn !== 'function') throw new TypeError(`Unknown paquete placement ${axis}.${selected}`);
  container.setAttribute('data-paquete-placement-axis', axis);
  container.setAttribute('data-paquete-placement', selected);
  fn({ container });
}

export function stepPlacement(ctx, step = ctx.view.step) {
  const pocket = ctx.womb?.session_metadata?.paquete_aesthetics?.widget_placements ?? {};
  const rows = pocket.steps ?? [];
  const seen = new Set();
  for (const row of rows) {
    if (!row.step || seen.has(row.step)) throw new TypeError('Duplicate or empty paquete placement step');
    seen.add(row.step);
  }
  const override = rows.find(row => row.step === publicStep(step)) ?? {};
  return { placement: PLACEMENT_DEFAULTS.widgets, visibility: PLACEMENT_DEFAULTS.visibility,
    ...pocket.defaults, ...override };
}

export function widgetsContainer(args, aesthetics) {
  const { documentRef, container, widgets, ctx, renderWidgetCard } = args;
  const current = stepPlacement(ctx);
  const appearances = current.visibility === 'all_appearances'
    ? ctx.view.widget_appearances
    : [{ step:ctx.view.step, widgets, current:true }];
  annotate(container, { part:'section', section:'widgets' });
  container.setAttribute('data-paquete-visibility', current.visibility);
  if (current.visibility === 'all_appearances') container.setAttribute('data-paquete-history-retained', '1');
  for (const appearance of appearances) {
    const group = annotate(documentRef.createElement('section'), { step:appearance.step, part:'step', section:'widgets' });
    place('widgets', stepPlacement(ctx, appearance.step).placement, group);
    aesthetics.widgetsContainer({ ...args, annotate, container:group, widgets:appearance.widgets,
      renderWidgetCard(widget) {
        const card = annotate(renderWidgetCard(widget), { widget, step:appearance.step, part:'widget', section:'widgets' });
        // Renderers use the active context for patches; historical cards use their own step.
        for (const node of card.querySelectorAll?.('[data-paquete-part]') ?? []) {
          const id = publicStep(appearance.step);
          if (id) node.setAttribute(SEMANTIC_TARGETS.step, id);
          else node.removeAttribute(SEMANTIC_TARGETS.step);
        }
        if (!appearance.current) {
          card.setAttribute('data-hai-widget-id', `${appearance.id}::${widget.datum_id}`);
          card.setAttribute('data-paquete-historical-widget', widget.datum_id);
        }
        return card;
      },
    });
    container.append(group);
  }
}

// Static roots and installed-pack modules can reach this file through more
// than one public URL. ES modules are cached by URL, so a second URL would
// otherwise get a separate WeakMap and append a second sheet to the same
// mounted shell. Keep the shell state shared by all copies in this window.
const runtimeKey = Symbol.for('thinkument.creativity.metal.aesthetics.runtime.v1');
const runtime = globalThis[runtimeKey] ??= { nextScope: 0, sheets: new WeakMap() };

export function compileCss(documentRef, scope, rules) {
  const { CSSStyleSheet, CSS } = documentRef.defaultView;
  const sheet = new CSSStyleSheet();
  for (const [index, rule] of rules.entries()) {
    try {
      let selector = '';
      for (const [key, value] of Object.entries(rule.target)) {
        if (!SEMANTIC_TARGETS[key] || typeof value !== 'string') throw new TypeError(`Invalid target ${key}`);
        selector += `[${SEMANTIC_TARGETS[key]}="${CSS.escape(value)}"]`;
      }
      if (!selector) selector = '[data-paquete-part="page"]';
      for (const pseudo of rule.pseudo_classes ?? []) {
        if (typeof pseudo !== 'string' || !/^[a-zA-Z_][a-zA-Z_0-9-]*$/.test(pseudo)
            || !CSS.supports(`selector(:${pseudo})`)) throw new TypeError(`Invalid pseudo-class ${pseudo}`);
        selector += `:${CSS.escape(pseudo)}`;
      }
      const root = `[data-paquete-scope="${scope}"]`;
      // Nested mounted sessions are boundaries too. :where keeps scoping out of specificity.
      const boundary = `:not(:where(${root} [data-paquete-scope], ${root} [data-paquete-scope] *))`;
      const scoped = `:where(${root})${selector}, :where(${root}) ${selector}${boundary}`;
      const position = sheet.cssRules.length;
      if (rule.media !== undefined) {
        if (typeof rule.media !== 'string' || !rule.media.trim()) throw new TypeError('Empty media condition');
        // insertRule parses natively. Count and type checks prevent extra-rule injection.
        sheet.insertRule(`@media ${rule.media} {}`, position);
        const media = sheet.cssRules[position];
        if (!media.media || media.cssRules.length || (media.conditionText === 'not all' && rule.media.trim() !== 'not all')) {
          throw new TypeError('Malformed media condition');
        }
        media.insertRule(`${scoped} {}`, 0);
      } else sheet.insertRule(`${scoped} {}`, position);
      const parsed = sheet.cssRules[position];
      const declaration = (parsed.media ? parsed.cssRules[0] : parsed).style;
      for (const [property, value] of Object.entries(rule.declarations)) {
        if (typeof value !== 'string') throw new TypeError(`Declaration ${property} must be a string`);
        const important = /\s*!important\s*$/i;
        declaration.setProperty(property, value.replace(important, ''), important.test(value) ? 'important' : '');
      }
    } catch (error) {
      throw new TypeError(`paquete_aesthetics.css_injection[${index}]: ${error.message}`);
    }
  }
  return [...sheet.cssRules].map(rule => rule.cssText).join('\n');
}

export function applyAesthetics({ shell, documentRef = shell.ownerDocument, ctx }) {
  if (!documentRef?.defaultView?.CSSStyleSheet) return;
  let state = runtime.sheets.get(shell);
  if (!state) {
    // The same source may be loaded through multiple public static URLs, which
    // creates distinct ES module instances and distinct WeakMaps. The mounted
    // root is the durable owner, so recover its sheet before adding another.
    const scope = shell.getAttribute('data-paquete-scope');
    const style = scope && [...shell.querySelectorAll('[data-paquete-styles]')].find(node =>
      node.getAttribute('data-paquete-styles') === scope
      && node.closest('[data-paquete-scope]') === shell);
    if (style) {
      const sequence = /^paquete-(\d+)$/.exec(scope);
      if (sequence) runtime.nextScope = Math.max(runtime.nextScope, Number(sequence[1]));
      state = { scope, style, signature:null };
    } else {
      const newScope = `paquete-${++runtime.nextScope}`;
      shell.setAttribute('data-paquete-scope', newScope);
      const newStyle = documentRef.createElement('style');
      newStyle.setAttribute('data-paquete-styles', newScope);
      // Root ownership provides cleanup when the mounted page is removed.
      shell.append(newStyle);
      state = { scope:newScope, style:newStyle, signature:null };
    }
    runtime.sheets.set(shell, state);
  }
  const rules = ctx?.womb?.session_metadata?.paquete_aesthetics?.css_injection ?? [];
  const signature = JSON.stringify(rules);
  if (signature === state.signature) return;
  try {
    const css = compileCss(documentRef, state.scope, rules);
    state.style.textContent = css;
    state.signature = signature;
    shell.removeAttribute('data-paquete-styling-error');
  } catch (error) {
    shell.setAttribute('data-paquete-styling-error', error.message);
    documentRef.defaultView.console?.error(error.message);
  }
}
