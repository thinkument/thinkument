"""Approved callable registry with versioned, exact, closed-record contracts."""
from dataclasses import dataclass
from difflib import get_close_matches
from threading import RLock
import re
from typing import Callable
from bindings2bindingsTM import Schema, normalize
from .errors import FlowCompilationError, FlowRuntimeError

_FN = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z')

@dataclass(frozen=True)
class FunctionEntry:
    name: str
    fn: Callable
    inputs: Schema
    output: Schema
    version: str
    def contract(self):
        return {'version': self.version, 'inputs': self.inputs.to_json(), 'output': self.output.to_json()}

class FunctionVocab:
    def __init__(self):
        self._entries = {}
        self._lock = RLock()

    def register(self, *, name, fn, inputs, output, version, replace=False):
        if type(name) is not str or not _FN.fullmatch(name):
            raise FlowCompilationError('invalid_function_name', message=f'Invalid function name: {name!r}')
        if not callable(fn):
            raise FlowCompilationError('invalid_function', message=f'Function {name!r} is not callable')
        if type(version) is not str or not version:
            raise FlowCompilationError('invalid_function_version', message='Version must be a nonempty string')
        try:
            incoming, outgoing = normalize(inputs), normalize(output)
        except Exception as exc:
            raise FlowCompilationError('invalid_function_contract', message=f'Invalid contract for {name}', cause=exc) from exc
        if incoming.kind != 'dict' or outgoing.kind != 'dict':
            raise FlowCompilationError('invalid_function_contract',
                                       message=f'Function {name!r} inputs and output must be closed Dict schemas')
        with self._lock:
            if name in self._entries and not replace:
                raise FlowCompilationError('duplicate_function', message=f'Function {name!r} is already registered')
            self._entries[name] = FunctionEntry(name, fn, incoming, outgoing, version)

    def names(self):
        with self._lock: return tuple(sorted(self._entries))

    def resolve(self, name, path=()):
        with self._lock:
            entry = self._entries.get(name)
            names = tuple(self._entries)
        if entry is None:
            matches = get_close_matches(str(name), names, n=1)
            suggestion = f" Did you mean '{matches[0]}'?" if matches else ''
            raise FlowCompilationError('unknown_function', path, message=f"Step {path!r} references unknown function {name!r}.{suggestion}", actual=name)
        return entry

    def snapshot(self, expected):
        """Atomically collect all checked callables or reject before any execution."""
        with self._lock:
            entries = {}
            for name, contract in expected.items():
                entry = self._entries.get(name)
                if entry is None or entry.contract() != contract:
                    raise FlowRuntimeError('contract_drift', ('functions', name),
                                           f'Function contract drift or missing registration: {name}',
                                           expected=contract, actual=entry.contract() if entry else None)
                entries[name] = entry
        return entries
