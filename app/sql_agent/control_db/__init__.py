"""Control-plane persistence for the SQL Builder Agent.

Own SQLAlchemy Base, engine, and session factory against the dedicated
``sql_agent_db`` database — nothing here is shared with ``app.db``.
"""
