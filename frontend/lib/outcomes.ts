/**
 * Labels and colours for the call-outcome / disposition taxonomy.
 *
 * The backend classifies each call into one granular `call_outcome`, then maps
 * it to a `disposition_status` + `sub_status`. Disposition status is the
 * business rollup (six values) and is what operator views lead with; the
 * granular outcome is the detail underneath it.
 */

/** Canonical display order — most actionable first. */
export const DISPOSITION_ORDER = [
  "Converted",
  "Follow Up",
  "Escalation",
  "Not Interested",
  "No Output",
  "Couldn't Reach",
] as const;

const DISPOSITION_COLORS: Record<string, string> = {
  Converted: "var(--green)",
  "Follow Up": "var(--accent)",
  Escalation: "var(--amber)",
  "Not Interested": "var(--red)",
  "No Output": "var(--muted)",
  "Couldn't Reach": "var(--muted)",
};

const OUTCOME_LABELS: Record<string, string> = {
  escalation: "Escalation",
  completed_visited: "Already visited",
  scheduled_booking: "Booking scheduled",
  done_elsewhere: "Done elsewhere",
  declined: "Declined",
  wants_cost_estimate: "Wants cost estimate",
  wants_discount: "Wants discount",
  wants_second_opinion: "Second opinion",
  waiting_doctor_confirmation: "Awaiting doctor",
  insurance_concern: "Insurance / TPA",
  loan_required: "Loan / EMI",
  on_medications: "On medications",
  waiting_reports: "Awaiting reports",
  medical_clearance_pending: "Clearance pending",
  waiting_referral_letter: "Referral pending",
  follow_up: "Follow-up",
  call_dropped: "Call dropped",
  no_output: "No output",
  not_connected: "Not connected",
};

/** Each granular outcome takes its disposition family's colour. */
const OUTCOME_COLORS: Record<string, string> = {
  escalation: "var(--amber)",

  completed_visited: "var(--green)",
  scheduled_booking: "var(--green)",

  done_elsewhere: "var(--red)",
  declined: "var(--red)",

  wants_cost_estimate: "var(--accent)",
  wants_discount: "var(--accent)",
  wants_second_opinion: "var(--accent)",
  waiting_doctor_confirmation: "var(--accent)",
  insurance_concern: "var(--accent)",
  loan_required: "var(--accent)",
  on_medications: "var(--accent)",
  waiting_reports: "var(--accent)",
  medical_clearance_pending: "var(--accent)",
  waiting_referral_letter: "var(--accent)",
  follow_up: "var(--accent)",
  call_dropped: "var(--accent)",

  no_output: "var(--muted)",
  not_connected: "var(--muted)",
};

/** Falls back to a de-snake-cased key so a new backend outcome still renders. */
export function outcomeLabel(key: string): string {
  return OUTCOME_LABELS[key] ?? key.replace(/_/g, " ");
}

export function outcomeColor(key: string): string {
  return OUTCOME_COLORS[key] ?? "var(--muted)";
}

export function dispositionColor(status: string): string {
  return DISPOSITION_COLORS[status] ?? "var(--muted)";
}

/**
 * Entries in canonical order, with any unrecognised key appended rather than
 * dropped — the backend taxonomy can grow without silently losing counts here.
 */
export function orderedDispositions<T>(
  counts: Record<string, T>,
): [string, T][] {
  const known = DISPOSITION_ORDER.filter((status) => status in counts).map(
    (status) => [status, counts[status]] as [string, T],
  );
  const unknown = Object.keys(counts)
    .filter((status) => !DISPOSITION_ORDER.includes(status as never))
    .sort()
    .map((status) => [status, counts[status]] as [string, T]);
  return [...known, ...unknown];
}

/** Granular outcomes, highest count first. */
export function rankedOutcomes(
  counts: Record<string, { count: number }>,
): [string, { count: number }][] {
  return Object.entries(counts).sort((a, b) => b[1].count - a[1].count);
}
