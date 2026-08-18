"""Agent Orchestrator — intent classification, plan schema/validation, and the
runner that executes a plan's steps against existing providers/connectors.

Scope (see plan doc for the full rationale): this package currently executes
one real plan type end-to-end — a visual-design request that also asks for
the result to be saved to Google Drive in the same message. Every other
intent in `intents.IntentType` is classified for taxonomy/telemetry purposes
only and is left to the existing chat.py branches, unmodified.
"""
