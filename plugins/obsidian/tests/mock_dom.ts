/**
 * Minimal DOM element stub used to exercise Obsidian view renderers in Node.
 */

export interface MockEl {
  children: MockEl[];
  textContent: string;
  style: Record<string, string>;
  className: string;
  tag?: string;
  attrs: Record<string, string>;
  onclick?: (evt?: any) => void;
  addEventListener?: (event: string, handler: (e: any) => void) => void;
  dispatchEvent?: (event: string, e: any) => void;
  createDiv: (opts?: MockElOptions) => MockEl;
  createSpan: (opts?: MockElOptions) => MockEl;
  createEl: (tag: string, opts?: MockElOptions) => MockEl;
  setText: (text: string) => void;
  setAttribute: (key: string, value: string) => void;
  removeAttribute: (key: string) => void;
  addClass: (cls: string) => void;
  removeClass: (cls: string) => void;
  hasClass: (cls: string) => boolean;
  toggleClass: (cls: string, force: boolean) => void;
  empty: () => void;
}

export interface MockElOptions {
  cls?: string;
  text?: string;
  attr?: Record<string, string>;
}

export function createMockEl(): MockEl {
  const listeners: Record<string, Array<(e: any) => void>> = {};
  const el: MockEl = {
    children: [],
    textContent: "",
    style: {},
    className: "",
    attrs: {},
    addEventListener: (event: string, handler: (e: any) => void) => {
      listeners[event] = listeners[event] || [];
      listeners[event].push(handler);
    },
    dispatchEvent: (event: string, e: any) => {
      (listeners[event] || []).forEach((fn) => fn(e));
    },
    createDiv: (opts?: MockElOptions) => appendChild(el, "div", opts),
    createSpan: (opts?: MockElOptions) => appendChild(el, "span", opts),
    createEl: (tag: string, opts?: MockElOptions) => appendChild(el, tag, opts),
    setText: (text: string) => {
      el.textContent = text;
    },
    setAttribute: (key: string, value: string) => {
      el.attrs[key] = value;
    },
    removeAttribute: (key: string) => {
      delete el.attrs[key];
    },
    addClass: (cls: string) => {
      el.className = (el.className + " " + cls).trim();
    },
    removeClass: (cls: string) => {
      el.className = el.className.replace(cls, "").trim();
    },
    hasClass: (cls: string) => el.className.split(/\s+/).includes(cls),
    toggleClass: (cls: string, force: boolean) => {
      const has = el.hasClass(cls);
      if (force && !has) el.addClass(cls);
      if (!force && has) el.removeClass(cls);
    },
    empty: () => {
      el.children.length = 0;
      el.textContent = "";
    },
  };
  return el;
}

function appendChild(parent: MockEl, tag: string, opts?: MockElOptions): MockEl {
  const child = createMockEl();
  child.tag = tag;
  if (opts?.cls) child.className = opts.cls;
  if (opts?.text) child.textContent = opts.text;
  if (opts?.attr) Object.assign(child.attrs, opts.attr);
  parent.children.push(child);
  return child;
}

/** Collect every text node rendered inside an element tree. */
export function collectText(node: MockEl): string {
  const parts: string[] = [node.textContent];
  for (const child of node.children) {
    parts.push(collectText(child));
  }
  return parts.filter(Boolean).join(" | ");
}

/** Find the first element whose text matches, depth first. */
export function findByText(node: MockEl, text: string): MockEl | null {
  if (node.textContent === text) return node;
  for (const child of node.children) {
    const found = findByText(child, text);
    if (found) return found;
  }
  return null;
}
