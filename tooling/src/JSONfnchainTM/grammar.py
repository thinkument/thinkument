"""Immutable compiled-node records and strict identifiers; no expression interpreter."""
from dataclasses import dataclass
import json
import re
from typing import Any
from .errors import FlowCompilationError

IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
RESERVED = frozenset(('item', 'outer', 'current', 'index', 'state', 'iteration'))
MAX_CONSTRUCT_DEPTH = 64
MAX_FLOW_NODES = 10_000

def ident(value, path=(), *, reserved=True):
    if type(value) is not str or not IDENT.fullmatch(value) or (reserved and value in RESERVED):
        raise FlowCompilationError('invalid_identifier', path, f'Invalid or reserved identifier: {value!r}', actual=str(value))
    return value

@dataclass(frozen=True)
class Expression:
    plan: Any
    schema: Any
    canonical_json: str
    @property
    def canonical(self):
        # Return a detached parse; the verified node stores only immutable text.
        return json.loads(self.canonical_json)

@dataclass(frozen=True)
class Block:
    nodes: tuple
    returns: Expression | None = None

@dataclass(frozen=True)
class CallNode:
    id: str
    fn: str
    args: Expression

@dataclass(frozen=True)
class BranchNode:
    id: str
    predicate: Expression
    then: Block
    otherwise: Block
    valued: bool

@dataclass(frozen=True)
class MapNode:
    id: str
    over: Expression
    alias: str
    parallel: bool
    max_concurrency: int
    body: Block

@dataclass(frozen=True)
class LoopNode:
    id: str
    init: Expression
    state_type: Any
    maximum: int
    on_max: str
    predicate: Expression
    body: Block
    update: Expression
    returns: Expression | None

@dataclass(frozen=True)
class ParallelNode:
    id: str
    calls: tuple[CallNode, ...]
