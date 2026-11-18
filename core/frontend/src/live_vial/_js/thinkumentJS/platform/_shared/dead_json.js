const objectTag = Object.prototype.toString;

export function assertDeadJson(value, path = "value") {
  if (value === null) return;
  const type = typeof value;
  if (type === "string" || type === "boolean") return;
  if (type === "number") {
    if (!Number.isFinite(value)) throw new TypeError(`${path} must contain only finite numbers`);
    return;
  }
  if (type !== "object") throw new TypeError(`${path} is not dead JSON`);
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertDeadJson(item, `${path}[${index}]`));
    return;
  }
  if (objectTag.call(value) !== "[object Object]") {
    throw new TypeError(`${path} must contain only plain objects and arrays`);
  }
  for (const [key, item] of Object.entries(value)) {
    assertDeadJson(item, `${path}.${key}`);
  }
}

export function cloneDeadJson(value, path = "value") {
  assertDeadJson(value, path);
  return structuredClone(value);
}

export function plainObject(value, name) {
  if (value === null || typeof value !== "object" || Array.isArray(value) || objectTag.call(value) !== "[object Object]") {
    throw new TypeError(`${name} must be a plain object`);
  }
  return value;
}
