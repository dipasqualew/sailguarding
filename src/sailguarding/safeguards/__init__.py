"""Safeguards — the governance keystone, the SPEC's *separation of powers* as types.

A :class:`Safeguard` is the metadata the safeguarding team owns: the control's class, its metric,
and the two declarations that govern how far a signal may move the float — structural vs.
human-dependent (:class:`SafeguardKind`) and health vs. efficacy (:class:`Measurement`). A
:class:`SafeguardBinding` binds one to the ``(activity, context)`` region it governs, through the
same :class:`~sailguarding.classification.Selector` language classification uses. A
:class:`BindingRegistry` resolves which safeguards govern a given ``(activity, context)`` — the
input list task 09 assembles a feature vector from — returning the union of distinct safeguards and
deduping any single safeguard bound twice to the most specific binding.

Live measurement (task 08) and the activity tree + budgets (task 07) build on top; this package
supplies the governed inputs, not the composition (task 05's scoring function) or the evidence.
"""

from sailguarding.safeguards.binding import SafeguardBinding
from sailguarding.safeguards.registry import BindingRegistry, InMemoryBindingRegistry
from sailguarding.safeguards.safeguard import (
    SAFEGUARD_SCHEMA_VERSION,
    Measurement,
    Safeguard,
    SafeguardKind,
)

__all__ = [
    "SAFEGUARD_SCHEMA_VERSION",
    "BindingRegistry",
    "InMemoryBindingRegistry",
    "Measurement",
    "Safeguard",
    "SafeguardBinding",
    "SafeguardKind",
]
