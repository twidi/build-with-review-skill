#!/usr/bin/env python3
"""Canonical ordered workflow context carried by durable journal entries."""

CONTEXT_FIELDS = (
    "mode", "lot", "correction", "task", "attempt", "round", "mandate", "job",
)
