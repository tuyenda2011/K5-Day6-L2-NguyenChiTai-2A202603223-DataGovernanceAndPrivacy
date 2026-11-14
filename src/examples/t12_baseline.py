"""Simple random sampling under exactly the same policy and audit budget as T12 PoC."""
from dataclasses import replace

from ..common.io import deep_merge
from ..tracks.t12 import run as run_t12


def run(ctx):
    run_t12(replace(ctx, config=deep_merge(ctx.config, {"params": {"sampling_strategy": "random", "audit_stages": None}})))
