"""
This type stub file was generated by pyright.
"""

from typing import Any
from ..hdl.ast import *
from ..hdl.rec import *
from ..lib.io import *
from .dsl import *
from collections.abc import Iterable, Iterator

__all__ = ["ResourceError", "ResourceManager"]
class ResourceError(Exception):
    ...


class ResourceManager:
    def __init__(self, resources: Iterable[Resource], connectors: Iterable[Connector]) -> None:
        ...
    
    def add_resources(self, resources: Iterable[Resource]) -> None:
        ...
    
    def add_connectors(self, connectors: Iterable[Connector]) -> None:
        ...
    
    def lookup(self, name: str, number: int=...) -> Resource:
        ...
    
    def request(self, name: str, number: int=..., *, dir=..., xdr=...) -> Record | Pin:
        ...
    
    def iter_single_ended_pins(self): # -> Generator[tuple[Unknown, Unknown, Unknown, Unknown], Any, None]:
        ...
    
    def iter_differential_pins(self): # -> Generator[tuple[Unknown, Unknown, Unknown, Unknown], Any, None]:
        ...
    
    def should_skip_port_component(self, port, attrs, component) -> bool:
        ...
    
    def iter_ports(self): # -> Generator[Unknown, Any, None]:
        ...
    
    def iter_port_constraints(self): # -> Generator[tuple[Unknown, Unknown, Unknown], Any, None]:
        ...
    
    def iter_port_constraints_bits(self): # -> Generator[tuple[Unknown, Unknown, Unknown] | tuple[str, Unknown, Unknown], Any, None]:
        ...
    
    def add_clock_constraint(self, clock: Signal, frequency: int | float) -> None:
        ...
    
    def iter_clock_constraints(self) -> Iterator[tuple[Signal, Any, int | float]]:
        ...
    


