# Warrant

No agent action without a warrant. A gateway between an AI agent and its tools that makes MongoDB Atlas the identity, policy and audit layer: every tool call is tied to an identity, checked against policy stored in Atlas before it runs, and recorded in an append-only ledger so a reviewer can reconstruct, stop and roll back a run.

Built at Agents in Context Toronto (MongoDB x Cerebral Valley), Nov 14 2026. Problem statement 1: "Agents You Can Audit".

Status: planning docs committed first, code follows. See `docs/00-SCOPE.md`.

## Setup

    cp .env.example .env      # fill in the Atlas sandbox connection string
    uv sync
    uv run --env-file .env python scripts/check_sandbox.py
