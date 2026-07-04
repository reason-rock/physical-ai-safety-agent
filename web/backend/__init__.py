"""FastAPI backend for the Physical AI Safety Agent dashboard.

Exposes ``/api/*`` REST endpoints and ``/sse/lab`` Server-Sent Events that
the Next.js frontend consumes. All agent / lab / safety / report logic is
delegated to the existing ``gaitlab.*`` package.
"""
