"""SQL Builder Agent — natural-language-to-SQL over a read-only target DB.

Operationally and data-wise independent of turing_service proper: its
control-plane data lives in the dedicated ``sql_agent_db`` database (see
``control_db/``), never in turing's own DB. Spec: docs/SQL Builder Agent -
Implementation.md.
"""
