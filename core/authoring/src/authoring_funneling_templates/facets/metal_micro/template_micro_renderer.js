export function renderBoundedScore({ documentRef, micro }) {
  const input = documentRef.createElement('input');
  input.type = 'number';
  input.min = String(micro.minimum ?? 0);
  input.max = String(micro.maximum ?? 100);
  input.value = micro.value == null ? '' : String(micro.value);
  return input;
}
