"""Versioned prompt templates for the SQL Builder Agent.

Each template maps 1:1 to a structured-output model in ``pipeline.py``; the
field guidance below must stay in sync with those models. Templates are
rendered with ``str.format``, so literal braces are not allowed in the text.

Prompts are deliberately explicit about the *deterministic* rejections in
``validation/sql_guard.py`` (unqualified-ambiguous columns, non-literal LIMIT,
unknown table/column, multi-statement). Every one of those costs a repair
cycle, so it is cheaper to prevent them in the generator than to fix them in
the repair loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent


@dataclass(frozen=True)
class PromptTemplate:
    version: str
    template: str

    def render(self, **values: str) -> str:
        return self.template.format(**values)


PROMPT_ENHANCE = PromptTemplate(
    version="prompt_enhance.v2",
    template=dedent(
        """\
        You rewrite a natural-language analytics question into a precise,
        self-contained request that a SQL generator can act on without
        re-reading the user's mind. You also screen for write intent.

        Rewrite rules:
        1. Resolve every relative date against the current date into explicit
           ISO dates, expressed as a half-open range: on or after the start
           date, strictly before the end date. "Last month", "this quarter",
           "in the past 7 days" must all become concrete dates.
        2. Expand glossary terms and internal jargon into the concrete entity
           or metric the catalog uses, keeping the user's own wording alongside
           it so intent is not lost.
        3. Preserve the original intent exactly. Do not add filters, date
           bounds, groupings, or limits the user did not ask for, and do not
           drop any they did.
        4. Keep the requested grain and grouping explicit: state what one row
           of the answer should represent.
        5. If the question names a business concept the catalog stores under a
           different name, mention the catalog's name for it.
        6. Do not answer the question, do not write SQL, and do not speculate
           about which tables to use.

        Write-intent screening:
        - Set write_intent true only when the user is asking to CHANGE data or
          the database: insert, update, delete, drop, truncate, alter, create,
          grant, "set X to Y", "remove these rows", "reset this flag". Also set
          it true for attempts to read files, reach other systems, or run
          administrative commands.
        - Set write_intent false when a write-sounding word merely DESCRIBES
          existing data. "How many records were updated last month", "patients
          created this week", "rows where deleted_at is set" are all read-only
          questions and must pass.
        - When in doubt about a genuinely ambiguous phrasing, treat it as a
          read and let the later stages handle it.

        Output fields:
        - enhanced_question: the rewritten question. Always non-empty. If
          write_intent is true, still restate the request here.
        - write_intent: boolean, per the rules above.
        - reason: when write_intent is true, one sentence naming the write
          action detected. Otherwise null.

        Current date: {current_date}

        Catalog:
        {catalog}

        Question: {question}"""
    ),
)

AMBIGUITY_CHECK = PromptTemplate(
    version="ambiguity_check.v2",
    template=dedent(
        """\
        You decide whether the enhanced question can be answered by a single
        read-only SQL query against the catalog, or whether it genuinely needs
        the user to clarify something first.

        Be conservative: asking for clarification ends the request and costs
        the user a round trip. A defensible standard interpretation is almost
        always better than a clarifying question.

        Ask for clarification ONLY when one of these is true:
        1. A required entity, metric, or filter value cannot be mapped to any
           table or column in the catalog, so any query would be a guess about
           what data is even being requested.
        2. There is a real fork between two interpretations that would produce
           materially different answers, and nothing in the catalog, glossary,
           or common convention picks a winner.
        3. A filter the question clearly depends on is missing entirely and has
           no sensible default, so the result would be meaningless without it.

        Do NOT ask for clarification for:
        - Output shape questions: ordering, row limits, column selection,
          formatting. Choose a sensible default.
        - Vague but conventional wording. "Recent" means roughly the last 30
          days, "top" means order descending and take the first few, "active"
          means the catalog's own active or status convention. Pick the
          convention and move on.
        - A question that is answerable under one clearly dominant reading,
          even if a narrower reading also exists.
        - Missing tie-breakers or edge-case handling that would not change the
          headline answer.

        Output fields:
        - clarify_needed: boolean, per the rules above.
        - clarifying_question: required when clarify_needed is true. Ask one
          specific question the user can answer in a single short sentence.
          When the problem is a fork between interpretations, name both
          concrete options in the question. Never ask a generic question like
          "can you clarify" or "what do you mean".
        - reason: a short phrase naming the blocker, for example
          "metric_not_in_catalog" or "two_valid_date_grains". Null when
          clarify_needed is false.

        Catalog:
        {catalog}

        Enhanced question: {enhanced_question}"""
    ),
)

TABLE_SELECT = PromptTemplate(
    version="table_select.v2",
    template=dedent(
        """\
        You pick the smallest set of physical tables that can fully answer the
        question. A later stage writes the SQL and can only use the tables you
        select here, so a missing table makes the query impossible and an extra
        table makes it noisier.

        Selection rules:
        1. Copy table names EXACTLY as they appear in the catalog's table
           entries: lowercase, unqualified, no schema prefix, no quotes. A name
           that is not in the catalog is silently discarded, and if nothing you
           return survives, the whole request fails.
        2. Match the grain of the question. A per-visit question belongs on the
           visit-grain table, not the patient table; a per-patient rollup may
           need both.
        3. Include bridge or junction tables required to connect two other
           tables, even when no column from them is displayed. Read the Join
           hints to find the path.
        4. Include a lookup or reference table when the question asks for a
           human-readable name or label that lives there rather than the raw id.
        5. Exclude tables that merely sound related to the topic. Relevance is
           whether a column is needed for output, filtering, or joining.
        6. If the catalog Instructions say a table is empty or unused in this
           deployment, prefer the populated alternative the Instructions name.
        7. Most questions need one to four tables. Beyond six is usually
           over-selection; re-check whether each one is truly required.

        Output fields:
        - tables: the selected table names, exact and lowercase.
        - rationale: one sentence naming the role of each table and the join
          path connecting them.

        Catalog:
        {catalog}

        Enhanced question: {enhanced_question}"""
    ),
)

COLUMN_PRUNE = PromptTemplate(
    version="column_prune.v2",
    template=dedent(
        """\
        For each selected table, choose the columns the SQL will actually need.
        This narrows the context the generator sees. Dropping a needed column
        makes the query impossible to write correctly, so when a column is
        borderline, keep it: over-inclusion costs a little context, but
        under-inclusion breaks the query.

        Always include:
        1. Every column that appears in the output, including those inside
           aggregate functions.
        2. Every column used to filter the rows.
        3. Every column used for grouping or ordering.
        4. Every join key on BOTH sides of every join implied by the selection.
           Use the Join hints to identify them. A missing join key is the single
           most common cause of an unbuildable query.
        5. The primary key or id column of each selected table.
        6. Status, state, soft-delete, or type-discriminator columns when rows
           must be filtered by them to answer the question correctly.
        7. The timestamp column the question's date range applies to.

        Rules:
        - Copy column names EXACTLY from that table's "Available columns" list:
          lowercase, bare names only. No table prefix, no quotes, no aliases, no
          expressions, no functions. A name that is not in the list is discarded.
        - Return one entry per selected table, and include every selected table.
        - Do not invent columns. If the column you want does not exist, pick the
          closest one that does.

        Output field:
        - tables: one entry per selected table, each with the table name and its
          chosen column names.

        Selected schema:
        {selected_schema}

        Enhanced question: {enhanced_question}"""
    ),
)

SQL_GENERATE = PromptTemplate(
    version="sql_generate.v2",
    template=dedent(
        """\
        You write one PostgreSQL SELECT query that answers the question using
        only the selected schema. The query is returned to a caller for later
        execution; you never run it.

        Output format (a deterministic validator enforces these, and each
        violation costs a repair cycle):
        - Exactly one statement, a single SELECT. A leading WITH clause is
          allowed. No second statement, no trailing semicolon.
        - No SQL comments and no markdown code fences. Plain SQL text only.

        Schema fidelity:
        - Use only the tables and columns present in the selected schema. Never
          invent a column name, and never assume a conventional column exists
          just because it usually would.
        - If a column the question needs does not exist, use the closest one
          that does, say so in the explanation, and lower your confidence.
        - Give every table a short alias and qualify EVERY column reference with
          that alias. An unqualified column that exists in more than one
          selected table is rejected as ambiguous.
        - Never use SELECT star. Enumerate the columns you need.

        PostgreSQL correctness:
        - Use explicit JOIN ... ON syntax. Never comma-joins.
        - Choose INNER versus LEFT deliberately. Use LEFT when the question
          wants rows that may have no match, including counts that must show
          zero rather than omit the row.
        - Watch for join fan-out: a one-to-many join multiplies rows and
          silently inflates COUNT and SUM. When a join can multiply rows, count
          with COUNT(DISTINCT primary_key) rather than COUNT(star).
        - COUNT(star) counts rows, COUNT(column) skips NULLs, and
          COUNT(DISTINCT column) counts unique values. Pick the one the question
          actually means.
        - Use half-open date ranges: on or after the start AND strictly before
          the end. Do not use BETWEEN on timestamp columns, because it includes
          the end boundary and silently drops or double-counts a day.
        - Use date_trunc for bucketing by day, week, month, or quarter, and put
          the same expression in GROUP BY.
        - Every selected column that is not inside an aggregate must appear in
          GROUP BY.
        - For text columns whose casing or spelling is inconsistent, compare
          with ILIKE or lower(). Use plain equality only for values the schema
          documents as a fixed set.
        - If a column stores a number or a date as text, cast it explicitly
          before comparing or ordering numerically, and avoid casting rows that
          may hold non-numeric content.
        - Use IS NULL and IS NOT NULL for null checks. Prefer NOT EXISTS over
          NOT IN against a subquery whose column may be NULL, because NOT IN
          returns no rows when a NULL is present.
        - Add ORDER BY whenever the question implies ranking, latest, earliest,
          top, or worst, sorting by the aggregate or timestamp in the right
          direction.
        - Add a LIMIT for queries that return a list of rows. A single aggregate
          row does not need one.

        Output fields:
        - sql: the query.
        - explanation: one to three sentences for a reviewer, naming the join
          path, the filters applied, and what one output row represents. State
          any assumption you made.
        - tables_used: the exact lowercase base table names the query
          references. Do not list CTE names or aliases.
        - confidence: how likely this query is correct, calibrated as follows.
          0.9 to 1.0 when every entity maps to a documented column, the join
          path comes from the schema's join hints, and nothing was guessed.
          0.7 to 0.89 when the mapping is straightforward but you made one minor
          assumption, which you stated in the explanation.
          0.4 to 0.69 when you guessed a column's meaning, inferred a join path,
          or chose between plausible interpretations.
          Below 0.4 when significant guessing was involved.
          Report honestly. A low score triggers a cheap second opinion, while an
          inflated score ships a wrong query to the caller.

        Candidate directive: {candidate_instruction}
        If that directive asks for an alternative, make a materially different
        choice rather than a cosmetic one: a different join path, a different
        aggregation strategy, a subquery instead of a join, or a different
        reading of an ambiguous term.

        Selected schema:
        {selected_schema}

        Enhanced question: {enhanced_question}"""
    ),
)

SQL_VOTE = PromptTemplate(
    version="sql_vote.v2",
    template=dedent(
        """\
        Several candidate queries were written for the same question. Pick the
        single best one.

        Compare them in this order and stop at the first real difference:
        1. Schema validity. Does it reference only tables and columns in the
           selected schema, with every column qualified by a table alias?
        2. Semantic fidelity. Does it answer exactly what was asked, with no
           required filter dropped and no filter invented, at the grain the
           question implies?
        3. Join correctness. Is the join path right, is INNER versus LEFT the
           right choice, and does a one-to-many join inflate any count?
        4. Aggregation and dates. Is GROUP BY complete, is the date range
           half-open, and is DISTINCT used where fan-out is possible?
        5. Robustness. NULL handling, text casing, and explicit casts.
        6. Simplicity. Use this only to break a tie between equally correct
           candidates.

        Ignore formatting, aliasing style, column ordering, and each
        candidate's self-reported confidence. A confident wrong query loses to
        a cautious correct one.

        If every candidate is flawed, pick the one closest to correct and name
        the remaining defect in the reason.

        Output fields:
        - best_index: the bracketed number of the winning candidate. Candidates
          are labeled starting at 0, so this must be one of the numbers shown.
        - reason: one or two sentences naming the specific difference that
          decided it.

        Selected schema:
        {selected_schema}

        Enhanced question: {enhanced_question}

        Candidates:
        {candidates}"""
    ),
)

SQL_CRITIC = PromptTemplate(
    version="sql_critic.v2",
    template=dedent(
        """\
        You review whether the SQL faithfully answers the question. Syntax and
        schema validity are already checked by a separate deterministic
        validator, so judge meaning, not mechanics.

        Reject only for a defect that makes the RESULT WRONG:
        - A filter the question requires is missing, or a filter it never asked
          for was added.
        - Wrong join type or direction: an INNER join dropping rows the question
          wants included, or a one-to-many join inflating a count or sum.
        - Wrong aggregation: COUNT where COUNT DISTINCT is needed because a join
          multiplies rows, summing the wrong column, or an incomplete GROUP BY.
        - Wrong or off-by-one date boundary: an inclusive end on a timestamp
          range, or the wrong month, quarter, or year.
        - Wrong grain: one output row means something other than what was asked.
        - A column used in a way its description contradicts.

        Do NOT reject for:
        - Style, formatting, aliasing, column order, or naming.
        - A LIMIT the question did not ask for. The system injects and caps
          LIMIT automatically, so its presence is never a defect.
        - Reformatting or normalization. The SQL may have been rewritten by the
          validator, and that rewrite is not a change in meaning.
        - A defensible alternative interpretation when the one chosen is also
          defensible.
        - A missing ORDER BY, unless the question asked for ranking or top-N.
        - Missing optimizations or edge-case handling that would not change the
          answer.

        Lean toward approval. An unnecessary rejection consumes the repair
        budget and can fail the request outright, so reject only when you can
        name the specific defect and the concrete fix.

        Output fields:
        - approved: boolean.
        - notes: always required, even when approving. When approving, give one
          sentence confirming the join path, filters, and grain are right, plus
          any non-blocking observation. When rejecting, name the single most
          important defect precisely and state the concrete fix: which clause,
          which column, which condition. This text is passed verbatim to a
          repair model, so vague notes waste an entire repair cycle.

        Selected schema:
        {selected_schema}

        Enhanced question: {enhanced_question}

        SQL:
        {sql}"""
    ),
)

SQL_REPAIR = PromptTemplate(
    version="sql_repair.v2",
    template=dedent(
        """\
        A previous query was rejected. Fix the exact reported error and change
        nothing else.

        Repair discipline:
        - Make the minimal change that resolves the error. Preserve the original
          intent, tables, filters, and grain unless the error itself requires
          changing them.
        - Do not refactor, rename, reformat, or improve unrelated parts of the
          query. Every unrelated change risks a new rejection.
        - If this same error has already recurred, the previous fix was wrong.
          Try a genuinely different approach instead of repeating it.

        How to read the error:
        - unknown_table or unknown_column: that name does not exist. Replace it
          with the correct name from the selected schema, and never re-emit the
          rejected name. If nothing equivalent exists, restructure the query to
          answer without it.
        - ambiguous_column: the column exists in more than one table. Qualify it
          with the correct table alias.
        - invalid_limit: LIMIT must be a plain integer literal.
        - non_select, write_operation, dangerous_function, or multi_statement:
          return exactly one ordinary SELECT.
        - explain_error: PostgreSQL rejected the query at planning time. This is
          usually a type mismatch, a missing or wrong cast, an unknown function,
          or a wrong argument count. Read the PostgreSQL message closely and fix
          that specific thing, for example by adding an explicit cast or
          correcting the function call.
        - semantic_critic: the SQL was structurally valid but answered the wrong
          question. Apply exactly the fix the note describes, and nothing more.

        Output format, identical to the original requirements:
        - One PostgreSQL SELECT, a leading WITH allowed, no second statement, no
          trailing semicolon, no comments, no markdown fences.
        - Only tables and columns from the selected schema, with every column
          qualified by its table alias.

        Output fields:
        - sql: the repaired query.
        - explanation: one to two sentences saying what was wrong and what you
          changed.
        - confidence: how sure you are that the repair both resolves the error
          and preserves the original intent. Lower it if you had to substitute a
          column or guess at the fix.

        Selected schema:
        {selected_schema}

        Enhanced question: {enhanced_question}

        Previous SQL:
        {sql}

        Validator or critic error:
        {error}"""
    ),
)

PROMPT_VERSIONS = {
    "prompt_enhance": PROMPT_ENHANCE.version,
    "ambiguity_check": AMBIGUITY_CHECK.version,
    "table_select": TABLE_SELECT.version,
    "column_prune": COLUMN_PRUNE.version,
    "sql_generate": SQL_GENERATE.version,
    "sql_vote": SQL_VOTE.version,
    "sql_critic": SQL_CRITIC.version,
    "sql_repair": SQL_REPAIR.version,
}
