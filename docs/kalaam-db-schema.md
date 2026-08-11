# Kalaam DB — Full Schema Reference

Auto-introspected from `kalam-postgres` (localhost:5435), database `continental-pilot-local`, schema `public`.
This is the complete structure fed to the SQL Builder Agent's control plane (metadata + embeddings).
Access is via the `sql_agent_readonly` role — SELECT only, 10s statement timeout, read-only transactions.

**68 base tables + 1 view (`assignment_plan_preview`) · 1,112 columns · 155 foreign-key relationships.**

> Row counts are planner estimates (`pg_class.reltuples`) at introspection time, not exact.

## Table inventory

| Table | ~Rows | Columns | PK |
|---|---:|---:|---|
| [visits_actions](#visits-actions) | 198,738 | 34 | id |
| [prescriptions](#prescriptions) | 53,155 | 25 | id |
| [prescription_files](#prescription-files) | 53,140 | 23 | id |
| [patient_visits](#patient-visits) | 52,792 | 19 | id |
| [patients](#patients) | 28,366 | 50 | id |
| [doc_map_assignment_audit](#doc-map-assignment-audit) | 21,309 | 6 | id |
| [call_history](#call-history) | 12,506 | 14 | id |
| [patient_suppression_list](#patient-suppression-list) | 5,858 | 9 | id |
| [patient_call_record_assets](#patient-call-record-assets) | 3,266 | 17 | id |
| [patient_call_records](#patient-call-records) | 2,913 | 40 | id |
| [escalations](#escalations) | 1,465 | 53 | id |
| [escalation_history](#escalation-history) | 1,463 | 9 | id |
| [notifications](#notifications) | 1,201 | 17 | id |
| [disposition_escalation_events](#disposition-escalation-events) | 444 | 8 | id |
| [appointments](#appointments) | 183 | 23 | id |
| [reminders](#reminders) | 149 | 12 | id |
| [disposition_escalations](#disposition-escalations) | 119 | 24 | id |
| [bulk_import_batches](#bulk-import-batches) | 117 | 14 | id |
| [user_sessions](#user-sessions) | 102 | 9 | id |
| [task_transfer_logs](#task-transfer-logs) | 100 | 9 | id |
| [users](#users) | 85 | 20 | id |
| [workflow_statuses](#workflow-statuses) | 84 | 13 | id |
| [department_coordinator_mappings](#department-coordinator-mappings) | 59 | 7 | id |
| [agent_presence](#agent-presence) | 55 | 11 | id |
| [doctor_coordinator_mappings](#doctor-coordinator-mappings) | 52 | 7 | id |
| [workflow_buckets](#workflow-buckets) | 49 | 11 | id |
| [task_types](#task-types) | 29 | 12 | id |
| [ni_caller_department_mappings](#ni-caller-department-mappings) | 14 | 7 | id |
| [floor_counsellor_mappings](#floor-counsellor-mappings) | 12 | 9 | id |
| [escalation_rules](#escalation-rules) | 8 | 29 | id |
| [roles](#roles) | 8 | 10 | id |
| [workflows](#workflows) | 7 | 13 | id |
| [system_config](#system-config) | 6 | 13 | id |
| [disposition_escalation_nudges](#disposition-escalation-nudges) | 5 | 12 | id |
| [disposition_escalation_attachments](#disposition-escalation-attachments) | 3 | 10 | id |
| [disposition_escalation_configs](#disposition-escalation-configs) | 3 | 9 | id |
| [centers](#centers) | 2 | 13 | id |
| [escalation_configs](#escalation-configs) | 2 | 9 | id |
| [feature_flags](#feature-flags) | 2 | 13 | id |
| [alembic_version](#alembic-version) | 1 | 1 | version_num |
| [departments](#departments) | 1 | 6 | id |
| [escalation_email_replies](#escalation-email-replies) | 1 | 13 | id |
| [hospitals](#hospitals) | 1 | 12 | id |
| [whatsapp_messages](#whatsapp-messages) | 1 | 30 | id |
| [whatsapp_settings](#whatsapp-settings) | 1 | 13 | id |
| [analytics_daily_summary](#analytics-daily-summary) | 0 | 18 | id |
| [analytics_events](#analytics-events) | 0 | 14 | id |
| [assignment_plan_preview](#assignment-plan-preview) (view) | — | 4 | — |
| [audit_logs](#audit-logs) | 0 | 19 | id |
| [call_derived_analytics](#call-derived-analytics) | 0 | 22 | id |
| [doctors](#doctors) | 0 | 5 | id |
| [escalation_matrices](#escalation-matrices) | 0 | 10 | id |
| [escalation_rule_versions](#escalation-rule-versions) | 0 | 20 | id |
| [escalation_run_states](#escalation-run-states) | 0 | 12 | id |
| [legacy_escalation_rules](#legacy-escalation-rules) | 0 | 17 | id |
| [nursing_visit_log](#nursing-visit-log) | 0 | 15 | anc_number |
| [patient_schedules](#patient-schedules) | 0 | 26 | id |
| [patient_whatsapp_state](#patient-whatsapp-state) | 0 | 14 | id |
| [schedule_adjustments](#schedule-adjustments) | 0 | 13 | id |
| [schedule_occurrences](#schedule-occurrences) | 0 | 16 | id |
| [scheduler_logs](#scheduler-logs) | 0 | 33 | id |
| [status_transitions](#status-transitions) | 0 | 12 | id |
| [system_config_versions](#system-config-versions) | 0 | 15 | id |
| [task_snapshots](#task-snapshots) | 0 | 8 | id |
| [whatsapp_escalation_events](#whatsapp-escalation-events) | 0 | 11 | id |
| [whatsapp_escalations](#whatsapp-escalations) | 0 | 54 | id |
| [whatsapp_media](#whatsapp-media) | 0 | 16 | id |
| [whatsapp_messaging_permissions](#whatsapp-messaging-permissions) | 0 | 8 | id |
| [workflow_rules](#workflow-rules) | 0 | 12 | id |

## Tables

### agent_presence

~55 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `user_id` → users.id | character varying(128) | no |  |
| `is_logged_in` | boolean | no | false |
| `assignment_enabled` | boolean | no | true |
| `last_login_at` | timestamp with time zone | yes |  |
| `last_logout_at` | timestamp with time zone | yes |  |
| `last_heartbeat_at` | timestamp with time zone | yes |  |
| `external_assigned_today` | integer | no | 0 |
| `external_counter_date` | date | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### alembic_version

~1 rows · PK: `version_num`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `version_num` 🔑 | character varying(32) | no |  |

### analytics_daily_summary

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `center_id` → centers.id | uuid | yes |  |
| `user_id` → users.id | character varying(128) | yes |  |
| `date` | date | no |  |
| `metric_type` | character varying(100) | no |  |
| `total_count` | integer | no |  |
| `completed_count` | integer | no |  |
| `pending_count` | integer | no |  |
| `failed_count` | integer | no |  |
| `average_completion_time` | integer | yes |  |
| `median_completion_time` | integer | yes |  |
| `min_completion_time` | integer | yes |  |
| `max_completion_time` | integer | yes |  |
| `average_quality_score` | double precision | yes |  |
| `success_rate` | double precision | yes |  |
| `metrics` | jsonb | no |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### analytics_events

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `center_id` → centers.id | uuid | yes |  |
| `event_type` | character varying(100) | no |  |
| `entity_type` | character varying(50) | no |  |
| `entity_id` | uuid | no |  |
| `user_id` → users.id | character varying(128) | yes |  |
| `event_data` | jsonb | no |  |
| `session_id` | character varying(100) | yes |  |
| `ip_address` | inet | yes |  |
| `user_agent` | text | yes |  |
| `occurred_at` | timestamp without time zone | no |  |
| `date_partition` | date | no |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### appointments

~183 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `patient_id` → patients.id | uuid | no |  |
| `visit_id` → patient_visits.id | uuid | yes |  |
| `doctor_id` → doctors.id | uuid | yes |  |
| `appointment_date` | timestamp with time zone | yes |  |
| `created_by_id` → users.id | character varying(128) | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `appointment_code` | character varying(50) | yes |  |
| `notes` | text | yes |  |
| `urgency` | character varying(50) | yes |  |
| `revenue_potential` | integer | yes |  |
| `workflow_id` → workflows.id | uuid | yes |  |
| `status` | USER-DEFINED | yes |  |
| `rescheduled_from_id` → appointments.id | uuid | yes |  |
| `reschedule_count` | integer | no |  |
| `completed_at` | timestamp with time zone | yes |  |
| `completed_by_id` → users.id | character varying(128) | yes |  |
| `cancelled_at` | timestamp with time zone | yes |  |
| `cancelled_by_id` → users.id | character varying(128) | yes |  |
| `cancellation_reason` | text | yes |  |
| `no_show_at` | timestamp with time zone | yes |  |
| `marked_by_id` → users.id | character varying(128) | yes |  |

Referenced by: `appointments.rescheduled_from_id`, `schedule_occurrences.appointment_id`

### assignment_plan_preview

**VIEW** (not a base table) · PK: `—`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `patient_id` | uuid | yes |  |
| `old_agent` | character varying(128) | yes |  |
| `user_id` | text | yes |  |
| `case_used` | text | yes |  |

### audit_logs

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `center_id` → centers.id | uuid | yes |  |
| `action` | character varying(100) | no |  |
| `entity_type` | character varying(50) | no |  |
| `entity_id` | uuid | yes |  |
| `user_id` → users.id | character varying(128) | yes |  |
| `user_email` | character varying(255) | yes |  |
| `old_values` | jsonb | no |  |
| `new_values` | jsonb | no |  |
| `changes` | jsonb | no |  |
| `ip_address` | character varying(45) | yes |  |
| `user_agent` | text | yes |  |
| `request_id` | character varying(100) | yes |  |
| `description` | text | yes |  |
| `data` | jsonb | no |  |
| `status` | character varying(20) | no |  |
| `error_message` | text | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### bulk_import_batches

~117 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `center_id` → centers.id | uuid | no |  |
| `created_by_id` → users.id | character varying | no |  |
| `workflow_code` | character varying(50) | no | 'opd'::character varying |
| `total_visits` | integer | no | 0 |
| `processed_count` | integer | no | 0 |
| `failed_count` | integer | no | 0 |
| `status` | character varying(10) | no | 'pending'::character varying |
| `errors` | jsonb | yes |  |
| `import_metadata` | jsonb | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `skipped_count` | integer | no | 0 |
| `skipped` | jsonb | yes |  |

### call_derived_analytics

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `call_history_id` → call_history.id | uuid | no |  |
| `patient_id` → patients.id | uuid | no |  |
| `journey_stage` | text | no |  |
| `package_interest` | text | no |  |
| `payment_mode` | text | no |  |
| `revenue_segment` | text | no |  |
| `blocker_code` | text | no |  |
| `next_action_type` | text | no |  |
| `next_action_date` | date | yes |  |
| `next_action_window` | text | no |  |
| `commitment_level` | text | no |  |
| `churn_risk` | text | no |  |
| `conversion_flag` | boolean | no |  |
| `follow_up_required` | boolean | no |  |
| `priority_score` | integer | no |  |
| `is_pregnant` | boolean | yes |  |
| `has_scans_booked` | boolean | yes |  |
| `has_delivery_booked` | boolean | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `derived_payload` | jsonb | no | '{}'::jsonb |

### call_history

~12,506 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `patient_id` → patients.id | uuid | no |  |
| `created_by_id` → users.id | character varying(128) | yes |  |
| `call_status` | character varying | yes |  |
| `call_reason` | character varying(200) | yes |  |
| `call_sub_reason` | character varying(200) | yes |  |
| `remarks` | text | yes |  |
| `follow_up_date` | timestamp with time zone | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `workflow_id` → workflows.id | uuid | yes |  |
| `meta_data` | jsonb | yes |  |
| `entity_type` | character varying(50) | yes |  |
| `escalation_id` → disposition_escalations.id | uuid | yes |  |

Referenced by: `call_derived_analytics.call_history_id`

### centers

~2 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `hospital_id` → hospitals.id | uuid | no |  |
| `name` | character varying(200) | no |  |
| `description` | text | yes |  |
| `email` | character varying(255) | yes |  |
| `phone` | character varying(20) | yes |  |
| `operating_hours` | jsonb | no |  |
| `specialties` | jsonb | no |  |
| `settings` | jsonb | no |  |
| `is_active` | boolean | no |  |
| `version` | integer | no |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

Referenced by: `analytics_daily_summary.center_id`, `analytics_events.center_id`, `audit_logs.center_id`, `bulk_import_batches.center_id`, `department_coordinator_mappings.center_id`, `disposition_escalation_configs.center_id`, `disposition_escalations.center_id`, `escalation_rules.center_id`, `escalations.center_id`, `floor_counsellor_mappings.center_id`, `legacy_escalation_rules.center_id`, `ni_caller_department_mappings.center_id`, `patients.center_id`, `prescriptions.center_id`, `users.center_id`, `whatsapp_escalations.center_id`

### department_coordinator_mappings

~59 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `department_name` | character varying(255) | no |  |
| `coordinator_user_id` → users.id | character varying(128) | no |  |
| `center_id` → centers.id | uuid | yes |  |
| `is_active` | boolean | no | true |
| `created_at` | timestamp with time zone | yes | now() |
| `updated_at` | timestamp with time zone | yes | now() |

### departments

~1 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `name` | character varying(100) | no |  |
| `description` | text | yes |  |
| `is_active` | boolean | no |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

Referenced by: `doctors.department_id`, `users.department_id`

### disposition_escalation_attachments

~3 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `escalation_id` → disposition_escalations.id | uuid | no |  |
| `uploaded_by` → users.id | character varying(128) | no |  |
| `original_filename` | character varying(255) | no |  |
| `storage_path` | character varying(512) | no |  |
| `bucket_name` | character varying(128) | no |  |
| `mime_type` | character varying(128) | no |  |
| `file_size` | integer | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### disposition_escalation_configs

~3 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `center_id` → centers.id | uuid | no |  |
| `escalation_type` | USER-DEFINED | no |  |
| `handler_user_id` → users.id | character varying(128) | no |  |
| `tat_minutes` | integer | no | 120 |
| `is_active` | boolean | no | true |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `breach_notification_user_ids` | jsonb | yes | '[]'::jsonb |

Referenced by: `disposition_escalations.config_id`

### disposition_escalation_events

~444 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `escalation_id` → disposition_escalations.id | uuid | no |  |
| `event_type` | USER-DEFINED | no |  |
| `actor_id` → users.id | character varying(128) | yes |  |
| `actor_role` | USER-DEFINED | no |  |
| `payload` | jsonb | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### disposition_escalation_nudges

~5 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `escalation_id` → disposition_escalations.id | uuid | no |  |
| `sent_by` → users.id | character varying(128) | yes |  |
| `sent_by_role` | USER-DEFINED | no |  |
| `sent_to` → users.id | character varying(128) | no |  |
| `message` | text | yes |  |
| `channel` | USER-DEFINED | no | 'push'::disposition_nudge_channel |
| `delivery_status` | USER-DEFINED | no | 'pending'::disposition_nudge_delivery_st… |
| `response_text` | text | yes |  |
| `responded_at` | timestamp with time zone | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### disposition_escalations

~119 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `center_id` → centers.id | uuid | no |  |
| `patient_id` → patients.id | uuid | no |  |
| `encounter_id` → patient_visits.id | uuid | yes |  |
| `escalation_type` | USER-DEFINED | no |  |
| `doctor_id` → doctors.id | uuid | yes |  |
| `created_by` → users.id | character varying(128) | no |  |
| `assigned_to` → users.id | character varying(128) | no |  |
| `config_id` → disposition_escalation_configs.id | uuid | no |  |
| `status` | USER-DEFINED | no | 'open'::disposition_escalation_status |
| `tat_deadline` | timestamp with time zone | no |  |
| `breached_at` | timestamp with time zone | yes |  |
| `resolved_at` | timestamp with time zone | yes |  |
| `resolution_note` | text | yes |  |
| `cxo_escalated` | boolean | no | false |
| `cxo_escalated_at` | timestamp with time zone | yes |  |
| `nudge_count` | integer | no | 0 |
| `warning_sent` | boolean | no | false |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `remarks` | text | yes |  |
| `follow_up_at` | timestamp with time zone | yes |  |
| `not_connected_at` | timestamp with time zone | yes |  |
| `original_agent_id` → users.id | character varying(128) | yes |  |

Referenced by: `call_history.escalation_id`, `disposition_escalation_attachments.escalation_id`, `disposition_escalation_events.escalation_id`, `disposition_escalation_nudges.escalation_id`

### doc_map_assignment_audit

~21,309 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | bigint | no | nextval('doc_map_assignment_audit_id_seq… |
| `patient_id` | uuid | no |  |
| `new_agent` | character varying | no |  |
| `case_used` | character varying(32) | no |  |
| `changed_at` | timestamp with time zone | no | now() |
| `old_agent` | character varying | yes |  |

### doctor_coordinator_mappings

~52 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `doctor_name` | character varying(255) | no |  |
| `coordinator_user_id` → users.id | character varying(128) | yes |  |
| `center_id` | uuid | yes |  |
| `is_active` | boolean | yes | true |
| `created_at` | timestamp with time zone | yes | now() |
| `updated_at` | timestamp with time zone | yes | now() |

### doctors

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `name` | character varying(255) | no |  |
| `department_id` → departments.id | uuid | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

Referenced by: `appointments.doctor_id`, `disposition_escalations.doctor_id`, `nursing_visit_log.doctor_id`, `patient_visits.doctor_id`

### escalation_configs

~2 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp without time zone | no | now() |
| `updated_at` | timestamp without time zone | no | now() |
| `config_key` | character varying(100) | no |  |
| `config_value` | jsonb | no |  |
| `description` | text | yes |  |
| `is_active` | boolean | no | true |
| `version` | character varying(20) | no | '1.0'::character varying |
| `updated_by` → users.id | character varying(128) | yes |  |

### escalation_email_replies

~1 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `escalation_id` → escalations.escalation_id | character varying(255) | no |  |
| `from_email` | character varying(255) | no |  |
| `to_emails` | ARRAY | yes |  |
| `subject` | text | yes |  |
| `body` | text | no |  |
| `message_id` | character varying(500) | yes |  |
| `in_reply_to` | character varying(500) | yes |  |
| `references` | text | yes |  |
| `nlp_analysis` | jsonb | yes |  |
| `received_at` | timestamp without time zone | no |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### escalation_history

~1,463 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp without time zone | no | now() |
| `updated_at` | timestamp without time zone | no | now() |
| `escalation_db_id` → escalations.id | uuid | no |  |
| `action` | character varying(100) | no |  |
| `old_value` | jsonb | yes |  |
| `new_value` | jsonb | yes |  |
| `remarks` | text | yes |  |
| `changed_by` → users.id | character varying(128) | yes |  |

### escalation_matrices

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `matrix_key` | character varying(100) | no |  |
| `version` | character varying(50) | no |  |
| `matrix` | jsonb | no |  |
| `department_mapping` | jsonb | no |  |
| `global_settings` | jsonb | no |  |
| `is_active` | boolean | no |  |
| `hospital_id` → hospitals.id | uuid | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### escalation_rule_versions

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `rule_id` → escalation_rules.id | uuid | no |  |
| `center_id` | uuid | yes |  |
| `rule_name` | character varying(100) | no |  |
| `task_type` | character varying(50) | no |  |
| `conditions` | jsonb | no |  |
| `escalate_to_role` | character varying(50) | yes |  |
| `escalate_to_user` | character varying(128) | yes |  |
| `notification_template` | character varying(100) | yes |  |
| `is_active` | boolean | no |  |
| `priority` | integer | no |  |
| `max_escalation_level` | integer | no |  |
| `trigger_delay_minutes` | integer | no |  |
| `cooldown_minutes` | integer | no |  |
| `actions` | jsonb | no |  |
| `version` | integer | no |  |
| `change_reason` | text | yes |  |
| `changed_by` → users.id | character varying(128) | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### escalation_rules

~8 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `center_id` → centers.id | uuid | yes |  |
| `rule_name` | character varying(100) | no |  |
| `task_type` | character varying(50) | yes |  |
| `conditions` | jsonb | no |  |
| `escalate_to_role` | character varying(50) | yes |  |
| `escalate_to_user` → users.id | character varying(128) | yes |  |
| `notification_template` | character varying(100) | yes |  |
| `is_active` | boolean | no |  |
| `priority` | integer | no |  |
| `max_escalation_level` | integer | yes |  |
| `trigger_delay_minutes` | integer | yes |  |
| `cooldown_minutes` | integer | yes |  |
| `actions` | jsonb | yes |  |
| `version` | integer | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `rule_code` | character varying(100) | yes |  |
| `description` | text | yes |  |
| `escalation_type` | character varying(50) | yes |  |
| `workflow_id` → workflows.id | uuid | yes |  |
| `department_ids` | ARRAY | yes |  |
| `escalation_matrix` | jsonb | no | '{}'::jsonb |
| `email_config` | jsonb | no | '{}'::jsonb |
| `sla_hours` | integer | yes |  |
| `auto_resolve_on_status_change` | boolean | no | false |
| `auto_resolve_statuses` | ARRAY | yes |  |
| `created_by` → users.id | character varying(128) | yes |  |
| `updated_by` → users.id | character varying(128) | yes |  |

Referenced by: `escalation_rule_versions.rule_id`, `escalations.rule_id`

### escalation_run_states

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `workflow_code` | character varying(100) | no |  |
| `bucket_code` | character varying(100) | no |  |
| `run_date` | timestamp without time zone | no |  |
| `run_time` | character varying(20) | no |  |
| `total_tasks` | integer | no |  |
| `breakdown` | jsonb | no |  |
| `email_sent` | boolean | no | false |
| `skipped` | boolean | no | false |
| `skip_reason` | text | yes |  |
| `created_at` | timestamp without time zone | no | now() |
| `updated_at` | timestamp without time zone | no | now() |

### escalations

~1,465 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `escalation_id` | character varying(255) | no |  |
| `uhid` | character varying(255) | no |  |
| `patient_name` | character varying(255) | no |  |
| `patient_age` | character varying(50) | yes |  |
| `patient_gender` | character varying(10) | yes |  |
| `patient_number` | character varying(20) | yes |  |
| `consultant_name` | character varying(255) | yes |  |
| `consultant_department` | character varying(255) | yes |  |
| `payor_type` | character varying(100) | yes |  |
| `call_reason` | character varying(255) | yes |  |
| `call_sub_reason` | character varying(255) | yes |  |
| `remarks` | text | yes |  |
| `prescription_images` | ARRAY | yes |  |
| `to_emails` | ARRAY | no |  |
| `cc_emails` | ARRAY | yes |  |
| `bcc_emails` | ARRAY | yes |  |
| `from_email` | character varying(255) | no |  |
| `escalation_header` | character varying(500) | no |  |
| `agent_email` | character varying(255) | yes |  |
| `coordinator_name` | character varying(255) | yes |  |
| `status` | character varying(50) | no |  |
| `resolved_at` | timestamp without time zone | yes |  |
| `resolved_by` | character varying(255) | yes |  |
| `resolution_remarks` | text | yes |  |
| `resolution_attachment_url` | text | yes |  |
| `auto_resolved` | boolean | no |  |
| `nlp_confidence` | double precision | yes |  |
| `nlp_keywords` | ARRAY | yes |  |
| `turnaround_time_seconds` | integer | yes |  |
| `turnaround_time_human` | character varying(100) | yes |  |
| `payload` | jsonb | no |  |
| `email_sent` | boolean | no |  |
| `email_sent_at` | timestamp without time zone | yes |  |
| `email_error` | text | yes |  |
| `hospital_id` → hospitals.id | uuid | yes |  |
| `created_by` → users.id | character varying(128) | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `rule_id` → escalation_rules.id | uuid | yes |  |
| `escalation_type` | character varying(50) | yes |  |
| `trigger_type` | character varying(50) | yes |  |
| `trigger_reason` | text | yes |  |
| `entity_id` | uuid | yes |  |
| `entity_type` | character varying(100) | yes |  |
| `priority` | character varying(20) | yes |  |
| `escalation_level` | character varying(10) | no | 'L1'::character varying |
| `assigned_to` → users.id | character varying(128) | yes |  |
| `assigned_at` | timestamp without time zone | yes |  |
| `due_date` | timestamp without time zone | yes |  |
| `is_overdue` | boolean | no | false |
| `center_id` → centers.id | uuid | yes |  |
| `workflow_id` → workflows.id | uuid | yes |  |

Referenced by: `escalation_email_replies.escalation_id`, `escalation_history.escalation_db_id`

### feature_flags

~2 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `flag_key` | character varying(100) | no |  |
| `flag_name` | character varying(200) | no |  |
| `description` | text | yes |  |
| `is_enabled` | boolean | no |  |
| `is_global` | boolean | no |  |
| `target_users` | jsonb | no |  |
| `target_roles` | jsonb | no |  |
| `config` | jsonb | no |  |
| `rollout_percentage` | integer | no |  |
| `environment` | character varying(20) | no |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### floor_counsellor_mappings

~12 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `department` | character varying(500) | no |  |
| `opd_code` | character varying(20) | no |  |
| `floor` | character varying(50) | no |  |
| `counsellor_user_id` → users.id | character varying | yes |  |
| `center_id` → centers.id | uuid | yes |  |
| `is_active` | boolean | no | true |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### hospitals

~1 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `name` | character varying(200) | no |  |
| `email` | character varying(255) | yes |  |
| `phone` | character varying(20) | yes |  |
| `website` | character varying(255) | yes |  |
| `address` | jsonb | no |  |
| `settings` | jsonb | no |  |
| `is_active` | boolean | no |  |
| `version` | integer | no |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `saheli_tenant_id` | uuid | yes |  |

Referenced by: `centers.hospital_id`, `escalation_matrices.hospital_id`, `escalations.hospital_id`, `system_config.hospital_id`, `whatsapp_escalations.hospital_id`, `whatsapp_settings.hospital_id`

### legacy_escalation_rules

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `center_id` → centers.id | uuid | yes |  |
| `rule_name` | character varying(100) | no |  |
| `task_type` | character varying(50) | no |  |
| `conditions` | jsonb | no |  |
| `escalate_to_role` | character varying(50) | yes |  |
| `escalate_to_user` → users.id | character varying(128) | yes |  |
| `notification_template` | character varying(100) | yes |  |
| `is_active` | boolean | no |  |
| `priority` | integer | no |  |
| `max_escalation_level` | integer | no |  |
| `trigger_delay_minutes` | integer | no |  |
| `cooldown_minutes` | integer | no |  |
| `actions` | jsonb | no |  |
| `version` | integer | no |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### ni_caller_department_mappings

~14 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `center_id` → centers.id | uuid | no |  |
| `department_pattern` | character varying(200) | no |  |
| `user_id` → users.id | character varying(128) | no |  |
| `is_fallback` | boolean | no | false |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### notifications

~1,201 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `user_id` → users.id | character varying(128) | no |  |
| `visit_id` → patient_visits.id | uuid | yes |  |
| `action_id` → visits_actions.id | uuid | yes |  |
| `type` | character varying(50) | no |  |
| `title` | character varying(255) | no |  |
| `message` | text | no |  |
| `channels` | jsonb | no | '["in_app"]'::jsonb |
| `delivery_status` | jsonb | no | '{}'::jsonb |
| `is_read` | boolean | no | false |
| `read_at` | timestamp with time zone | yes |  |
| `scheduled_for` | timestamp with time zone | no | now() |
| `sent_at` | timestamp with time zone | yes |  |
| `priority` | character varying(20) | no | 'medium'::character varying |
| `data` | jsonb | no | '{}'::jsonb |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### nursing_visit_log

~0 rows · PK: `anc_number`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `anc_number` 🔑 | bigint | no | nextval('nursing_visit_log_anc_number_se… |
| `visit_date` | date | no |  |
| `uhid` | text | no |  |
| `patient_name` | text | no |  |
| `guardian_name` | text | no |  |
| `age` | smallint | yes |  |
| `address` | text | no |  |
| `phone_number` | bigint | yes |  |
| `occupation` | text | yes |  |
| `lmp` | date | yes |  |
| `edd` | date | yes |  |
| `doctor_name` | text | no |  |
| `created_at` | timestamp with time zone | yes | now() |
| `updated_at` | timestamp with time zone | yes | now() |
| `doctor_id` → doctors.id | uuid | no |  |

### patient_call_record_assets

~3,266 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `call_record_id` → patient_call_records.id | uuid | no |  |
| `asset_type` | character varying(50) | no |  |
| `bucket_name` | character varying(200) | yes |  |
| `storage_provider` | character varying(100) | yes |  |
| `storage_path` | character varying(500) | yes |  |
| `storage_url` | character varying(1024) | yes |  |
| `mime_type` | character varying(100) | yes |  |
| `file_size` | integer | yes |  |
| `checksum` | character varying(64) | yes |  |
| `processing_status` | character varying(50) | no | 'pending'::character varying |
| `processing_started_at` | timestamp with time zone | yes |  |
| `processing_completed_at` | timestamp with time zone | yes |  |
| `processing_error` | text | yes |  |
| `meta_data` | jsonb | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### patient_call_records

~2,913 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `patient_id` → patients.id | uuid | yes |  |
| `provider` | character varying(50) | no |  |
| `provider_record_id` | character varying(128) | yes |  |
| `provider_call_id` | character varying(128) | no |  |
| `provider_recording_id` | character varying(128) | yes |  |
| `provider_uuid` | character varying(128) | yes |  |
| `direction` | character varying(20) | yes |  |
| `status` | character varying(50) | yes |  |
| `description` | text | yes |  |
| `detailed_description` | text | yes |  |
| `service` | character varying(100) | yes |  |
| `provider_recording_url` | character varying(1024) | yes |  |
| `call_date` | date | yes |  |
| `call_time` | character varying(20) | yes |  |
| `provider_end_stamp` | timestamp without time zone | yes |  |
| `linked_at` | timestamp with time zone | yes |  |
| `link_source` | character varying(50) | yes |  |
| `link_status` | character varying(50) | yes |  |
| `call_duration` | integer | yes |  |
| `answered_seconds` | integer | yes |  |
| `minutes_consumed` | integer | yes |  |
| `charges` | numeric | yes |  |
| `department_name` | character varying(255) | yes |  |
| `agent_number` | character varying(32) | yes |  |
| `agent_number_with_prefix` | character varying(32) | yes |  |
| `agent_name` | character varying(255) | yes |  |
| `client_number` | character varying(32) | yes |  |
| `did_number` | character varying(32) | yes |  |
| `caller_id_num` | character varying(32) | yes |  |
| `reason` | character varying(255) | yes |  |
| `hangup_cause` | character varying(255) | yes |  |
| `call_hint` | character varying(100) | yes |  |
| `lead_id` | character varying(128) | yes |  |
| `matched_phone` | character varying(32) | yes |  |
| `summary_text` | text | yes |  |
| `raw_payload` | jsonb | no | '{}'::jsonb |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `transcript_text` | text | yes |  |

Referenced by: `patient_call_record_assets.call_record_id`

### patient_schedules

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `schedule_code` | character varying(50) | no |  |
| `schedule_name` | character varying(200) | no |  |
| `patient_id` → patients.id | uuid | no |  |
| `workflow_id` → workflows.id | uuid | yes |  |
| `task_type_id` → task_types.id | uuid | no |  |
| `start_date` | date | no |  |
| `expected_end_date` | date | yes |  |
| `actual_end_date` | date | yes |  |
| `status` | character varying(9) | no |  |
| `notes` | text | yes |  |
| `created_by_id` → users.id | character varying(128) | yes |  |
| `created_at` | timestamp with time zone | no | CURRENT_TIMESTAMP |
| `updated_at` | timestamp with time zone | no | CURRENT_TIMESTAMP |
| `start_time` | time without time zone | no |  |
| `scheduling_type` | character varying(14) | no |  |
| `total_sessions` | integer | no |  |
| `gap_days` | integer | no |  |
| `skip_days` | ARRAY | yes |  |
| `completed_sessions` | integer | no |  |
| `cancelled_sessions` | integer | no |  |
| `skipped_sessions` | integer | no |  |
| `duration_minutes` | integer | yes |  |
| `location` | character varying(255) | yes |  |
| `visit_action_id` → visits_actions.id | uuid | yes |  |
| `weekly_pattern` | ARRAY | yes |  |

Referenced by: `schedule_adjustments.schedule_id`, `schedule_occurrences.schedule_id`

### patient_suppression_list

~5,858 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `uhid` | character varying(50) | no |  |
| `patient_name` | character varying(100) | yes |  |
| `phone` | character varying(20) | yes |  |
| `source_file` | character varying(255) | yes |  |
| `remarks` | text | yes |  |
| `is_active` | boolean | no | true |

### patient_visits

~52,792 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `patient_id` → patients.id | uuid | no |  |
| `doctor_id` → doctors.id | uuid | yes |  |
| `doctor_name` | character varying(200) | yes |  |
| `visit_date` | timestamp with time zone | yes |  |
| `status` | character varying(100) | yes |  |
| `is_escalated` | boolean | yes |  |
| `escalation_level` | character varying(100) | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `prescription_id` → prescriptions.id | uuid | yes |  |
| `clinical_summary` | jsonb | yes |  |
| `clinical_timeline` | jsonb | yes |  |
| `workflow_id` → workflows.id | uuid | yes |  |
| `department` | character varying | yes |  |
| `ip_progression_summary` | jsonb | yes |  |
| `ip_potential_metrics` | jsonb | yes |  |
| `ip_conversion_probability` | character varying(10) | yes |  |
| `radiology_tags` | jsonb | yes | '[]'::jsonb |

Referenced by: `appointments.visit_id`, `disposition_escalations.encounter_id`, `notifications.visit_id`, `visits_actions.visit_id`

### patient_whatsapp_state

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 → patients.id | uuid | no |  |
| `phone` | character varying(20) | no |  |
| `tenant_id` | uuid | no |  |
| `has_active_escalation` | boolean | no | false |
| `active_escalation_count` | integer | no | 0 |
| `highest_priority` | smallint | yes |  |
| `has_emergency` | boolean | no | false |
| `latest_escalation_id` → whatsapp_escalations.id | uuid | yes |  |
| `latest_escalation_ref` | character varying(20) | yes |  |
| `total_unread_messages` | integer | no | 0 |
| `last_inbound_at` | timestamp with time zone | yes |  |
| `last_event_at` | timestamp with time zone | no | '2026-05-28 12:22:23.339698+00'::timesta… |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### patients

~28,366 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `center_id` → centers.id | uuid | yes |  |
| `agent_id` → users.id | character varying(128) | yes |  |
| `uhid` | character varying(50) | no |  |
| `name` | character varying(100) | no |  |
| `phone` | character varying(20) | yes |  |
| `phone_captured` | character varying(20) | yes |  |
| `secondary_phone` | character varying(20) | yes |  |
| `email` | character varying(255) | yes |  |
| `age` | character varying(10) | yes |  |
| `gender` | character varying | yes |  |
| `is_active` | boolean | no |  |
| `bookmarked` | boolean | yes |  |
| `agent_worked_status` | character varying(50) | yes |  |
| `clinical_summary` | jsonb | yes |  |
| `follow_up_date` | date | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `created_by_id` → users.id | character varying(128) | yes |  |
| `client_uhid` | character varying(50) | yes |  |
| `workflow_status` | character varying(100) | yes |  |
| `workflow_sub_status` | character varying(100) | yes |  |
| `clinical_timeline` | jsonb | yes |  |
| `clinical_timeline_by_visits` | jsonb | yes |  |
| `workflow_secondary_status` | character varying(100) | yes |  |
| `workflow_id` → workflows.id | uuid | yes |  |
| `stage` | character varying(100) | yes |  |
| `status_action_date` | timestamp with time zone | yes |  |
| `workflow_type` | character varying | yes |  |
| `workflow_secondary_sub_status` | character varying | yes |  |
| `agent_worked_at` | timestamp with time zone | yes |  |
| `risk_category` | character varying(100) | yes |  |
| `last_visit_date` | date | yes |  |
| `last_visit` | jsonb | yes |  |
| `is_verified` | boolean | no | true |
| `verified_by` | character varying(200) | yes |  |
| `last_verified_date` | timestamp with time zone | yes |  |
| `ip_progression_summary` | jsonb | yes |  |
| `care_plan_filters` | jsonb | yes |  |
| `search_vector` | tsvector | yes |  |
| `counselling_done` | boolean | yes | false |
| `package_taken` | boolean | yes | false |
| `first_visit` | boolean | yes | false |
| `previously_not_interested` | boolean | no | false |
| `payor_type` | character varying(20) | yes |  |
| `payor_name` | character varying(255) | yes |  |
| `ip_admission_metrics` | jsonb | yes |  |
| `radiology_metrics` | jsonb | yes |  |
| `ip_potential_metrics` | jsonb | yes |  |
| `ip_conversion_probability` | character varying(10) | yes |  |

Referenced by: `appointments.patient_id`, `call_derived_analytics.patient_id`, `call_history.patient_id`, `disposition_escalations.patient_id`, `patient_call_records.patient_id`, `patient_schedules.patient_id`, `patient_visits.patient_id`, `patient_whatsapp_state.id`, `prescriptions.patient_id`, `reminders.patient_id`, `schedule_occurrences.patient_id`, `task_transfer_logs.patient_id`, `visits_actions.patient_id`, `whatsapp_escalations.patient_id`, `whatsapp_messages.patient_id`

### prescription_files

~53,140 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `prescription_id` → prescriptions.id | uuid | yes |  |
| `uploaded_by` → users.id | character varying(128) | yes |  |
| `filename` | character varying(255) | no |  |
| `original_filename` | character varying(255) | yes |  |
| `file_type` | character varying(100) | yes |  |
| `file_size` | bigint | yes |  |
| `mime_type` | character varying(100) | yes |  |
| `storage_url` | character varying(1024) | yes |  |
| `bucket_name` | character varying(200) | yes |  |
| `storage_path` | character varying(500) | yes |  |
| `storage_provider` | character varying(100) | yes |  |
| `processing_status` | USER-DEFINED | no |  |
| `processing_started_at` | timestamp without time zone | yes |  |
| `processing_completed_at` | timestamp without time zone | yes |  |
| `processing_error` | text | yes |  |
| `extracted_data` | jsonb | yes |  |
| `confidence_score` | numeric | yes |  |
| `extraction_method` | character varying(50) | yes |  |
| `checksum` | character varying(64) | yes |  |
| `is_valid` | boolean | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### prescriptions

~53,155 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `center_id` → centers.id | uuid | yes |  |
| `patient_id` → patients.id | uuid | yes |  |
| `uploaded_by` → users.id | character varying(128) | yes |  |
| `processed_by` → users.id | character varying(128) | yes |  |
| `prescription_number` | character varying(100) | yes |  |
| `status` | USER-DEFINED | no |  |
| `ip_admission_advised` | boolean | yes |  |
| `escalation_status` | character varying(50) | yes |  |
| `escalation_level` | character varying(100) | yes |  |
| `escalation_notes` | text | yes |  |
| `form_data` | jsonb | no |  |
| `extracted_data` | jsonb | no |  |
| `confidence_score` | numeric | yes |  |
| `extraction_method` | character varying(50) | yes |  |
| `quality_score` | numeric | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `patient_form_data` | jsonb | yes |  |
| `is_verified` | boolean | no |  |
| `verified_by` → users.id | character varying(128) | yes |  |
| `verified_at` | timestamp without time zone | yes |  |
| `prescription_type` | character varying(20) | yes |  |
| `content_hash` | character varying(64) | yes |  |
| `clinical_fingerprint` | character varying(64) | yes |  |

Referenced by: `patient_visits.prescription_id`, `prescription_files.prescription_id`

### reminders

~149 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `patient_id` → patients.id | uuid | no |  |
| `patient_type` | character varying(50) | no | 'ip_recommendation_patient'::character v… |
| `title` | character varying(255) | no |  |
| `reminder_date` | timestamp with time zone | no |  |
| `notes` | text | yes |  |
| `user_id` → users.id | character varying(128) | no |  |
| `status` | character varying(20) | no | 'pending'::character varying |
| `completed_at` | timestamp with time zone | yes |  |
| `dismissed_at` | timestamp with time zone | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### roles

~8 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `name` | character varying(100) | no |  |
| `display_name` | character varying(100) | no |  |
| `description` | text | yes |  |
| `role_type` | character varying(50) | no |  |
| `permissions` | jsonb | no |  |
| `config` | jsonb | no |  |
| `is_active` | boolean | no |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

Referenced by: `users.role_id`

### schedule_adjustments

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `schedule_id` → patient_schedules.id | uuid | no |  |
| `occurrence_id` → schedule_occurrences.id | uuid | yes |  |
| `adjustment_type` | character varying(50) | no |  |
| `reason` | text | yes |  |
| `adjusted_by_id` → users.id | character varying(128) | yes |  |
| `created_at` | timestamp with time zone | no | CURRENT_TIMESTAMP |
| `updated_at` | timestamp with time zone | no | CURRENT_TIMESTAMP |
| `old_date` | date | yes |  |
| `new_date` | date | yes |  |
| `old_time` | time without time zone | yes |  |
| `new_time` | time without time zone | yes |  |
| `adjusted_at` | timestamp with time zone | no |  |

### schedule_occurrences

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `schedule_id` → patient_schedules.id | uuid | no |  |
| `scheduled_date` | date | no |  |
| `original_date` | date | no |  |
| `status` | character varying(9) | no |  |
| `appointment_id` → appointments.id | uuid | yes |  |
| `notes` | text | yes |  |
| `completed_at` | timestamp with time zone | yes |  |
| `completed_by_id` → users.id | character varying(128) | yes |  |
| `created_at` | timestamp with time zone | no | CURRENT_TIMESTAMP |
| `updated_at` | timestamp with time zone | no | CURRENT_TIMESTAMP |
| `patient_id` → patients.id | uuid | no |  |
| `task_type_id` → task_types.id | uuid | no |  |
| `session_number` | integer | no |  |
| `scheduled_time` | time without time zone | no |  |
| `original_time` | time without time zone | no |  |

Referenced by: `schedule_adjustments.occurrence_id`

### scheduler_logs

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `log_type` | character varying(50) | no |  |
| `operation` | character varying(100) | no |  |
| `patient_id` | uuid | yes |  |
| `visit_id` | uuid | yes |  |
| `task_id` | uuid | yes |  |
| `reminder_id` | uuid | yes |  |
| `created_by_id` | character varying(100) | yes |  |
| `previous_agent_id` | character varying(100) | yes |  |
| `new_agent_id` | character varying(100) | yes |  |
| `assignment_reason` | text | yes |  |
| `previous_workflow_id` | uuid | yes |  |
| `new_workflow_id` | uuid | yes |  |
| `workflow_change_reason` | text | yes |  |
| `previous_task_type_id` | uuid | yes |  |
| `new_task_type_id` | uuid | yes |  |
| `trigger_type` | character varying(50) | yes |  |
| `trigger_task_title` | text | yes |  |
| `action_type` | character varying(50) | yes |  |
| `reminder_action` | character varying(20) | yes |  |
| `reminder_notes` | text | yes |  |
| `previous_workflow_status` | character varying(50) | yes |  |
| `new_workflow_status` | character varying(50) | yes |  |
| `previous_workflow_secondary_status` | character varying(50) | yes |  |
| `new_workflow_secondary_status` | character varying(50) | yes |  |
| `error_message` | text | yes |  |
| `error_stack` | text | yes |  |
| `error_context` | jsonb | yes |  |
| `batch_id` | uuid | yes |  |
| `execution_time_ms` | integer | yes |  |
| `records_affected` | integer | yes |  |
| `additional_data` | jsonb | yes |  |
| `created_at` | timestamp without time zone | yes | now() |

### status_transitions

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `workflow_id` → workflows.id | uuid | no |  |
| `from_status_id` → workflow_statuses.id | uuid | yes |  |
| `to_status_id` → workflow_statuses.id | uuid | yes |  |
| `transition_name` | character varying(100) | yes |  |
| `conditions` | jsonb | yes |  |
| `required_fields` | jsonb | yes |  |
| `auto_actions` | jsonb | yes |  |
| `is_allowed` | boolean | no |  |
| `display_order` | integer | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### system_config

~6 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `hospital_id` → hospitals.id | uuid | yes |  |
| `config_key` | character varying(100) | no |  |
| `config_value` | jsonb | no |  |
| `description` | text | yes |  |
| `is_active` | boolean | no |  |
| `is_encrypted` | boolean | no |  |
| `config_type` | character varying(50) | no |  |
| `environment` | character varying(20) | no |  |
| `version` | integer | no |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `workflow_id` → workflows.id | uuid | yes |  |

Referenced by: `system_config_versions.config_id`

### system_config_versions

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `config_id` → system_config.id | uuid | no |  |
| `hospital_id` | uuid | yes |  |
| `config_key` | character varying(100) | no |  |
| `config_value` | jsonb | no |  |
| `description` | text | yes |  |
| `is_active` | boolean | no |  |
| `is_encrypted` | boolean | no |  |
| `config_type` | character varying(50) | no |  |
| `environment` | character varying(20) | no |  |
| `version` | integer | no |  |
| `change_reason` | text | yes |  |
| `changed_by` → users.id | character varying(128) | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### task_snapshots

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `snapshot_date` | timestamp without time zone | no |  |
| `workflow_code` | character varying | no |  |
| `bucket_code` | character varying | no |  |
| `total_tasks` | integer | no | 0 |
| `task_breakdown` | jsonb | no | '{}'::jsonb |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### task_transfer_logs

~100 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `visit_action_id` → visits_actions.id | uuid | no |  |
| `patient_id` → patients.id | uuid | no |  |
| `from_agent_id` → users.id | character varying(128) | yes |  |
| `to_agent_id` → users.id | character varying(128) | yes |  |
| `doctor_name` | character varying(255) | yes |  |
| `matched_coordinator` | boolean | yes | false |
| `transferred_by_id` → users.id | character varying(128) | yes |  |
| `created_at` | timestamp with time zone | yes | now() |

### task_types

~29 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `is_active` | boolean | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `workflow_id` → workflows.id | uuid | no |  |
| `task_type_code` | character varying(50) | no |  |
| `task_type_name` | character varying(100) | no |  |
| `description` | text | yes |  |
| `default_status_id` → workflow_statuses.id | uuid | yes |  |
| `default_bucket_id` → workflow_buckets.id | uuid | yes |  |
| `workflow_config` | jsonb | yes |  |
| `auto_create_reminder` | boolean | yes | false |

Referenced by: `patient_schedules.task_type_id`, `schedule_occurrences.task_type_id`, `visits_actions.task_type_id`

### user_sessions

~102 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `shadow_user_id` → users.id | character varying(128) | no |  |
| `actual_user_id` → users.id | character varying(128) | no |  |
| `session_token` | character varying(255) | yes |  |
| `started_at` | timestamp with time zone | no |  |
| `ended_at` | timestamp with time zone | yes |  |
| `is_active` | boolean | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### users

~85 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | character varying(128) | no |  |
| `email` | character varying(255) | no |  |
| `hashed_password` | character varying(255) | yes |  |
| `first_name` | character varying(100) | no |  |
| `last_name` | character varying(100) | no |  |
| `phone` | character varying(20) | yes |  |
| `is_active` | boolean | no |  |
| `role_id` → roles.id | uuid | yes |  |
| `department_id` → departments.id | uuid | yes |  |
| `center_id` → centers.id | uuid | no |  |
| `fcm_token` | character varying(255) | yes |  |
| `user_config` | jsonb | no |  |
| `data` | jsonb | no |  |
| `login_count` | integer | no |  |
| `last_login` | timestamp without time zone | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `is_shadow` | boolean | no | false |
| `allowed_shadow_users` | jsonb | yes |  |
| `last_task_assignment_at` | timestamp with time zone | yes |  |

Referenced by: `agent_presence.user_id`, `analytics_daily_summary.user_id`, `analytics_events.user_id`, `appointments.cancelled_by_id`, `appointments.completed_by_id`, `appointments.created_by_id`, `appointments.marked_by_id`, `audit_logs.user_id`, `bulk_import_batches.created_by_id`, `call_history.created_by_id`, `department_coordinator_mappings.coordinator_user_id`, `disposition_escalation_attachments.uploaded_by`, `disposition_escalation_configs.handler_user_id`, `disposition_escalation_events.actor_id`, `disposition_escalation_nudges.sent_by`, `disposition_escalation_nudges.sent_to`, `disposition_escalations.assigned_to`, `disposition_escalations.created_by`, `disposition_escalations.original_agent_id`, `doctor_coordinator_mappings.coordinator_user_id`, `escalation_configs.updated_by`, `escalation_history.changed_by`, `escalation_rule_versions.changed_by`, `escalation_rules.created_by`, `escalation_rules.escalate_to_user`, `escalation_rules.updated_by`, `escalations.assigned_to`, `escalations.created_by`, `floor_counsellor_mappings.counsellor_user_id`, `legacy_escalation_rules.escalate_to_user`, `ni_caller_department_mappings.user_id`, `notifications.user_id`, `patient_schedules.created_by_id`, `patients.agent_id`, `patients.created_by_id`, `prescription_files.uploaded_by`, `prescriptions.processed_by`, `prescriptions.uploaded_by`, `prescriptions.verified_by`, `reminders.user_id`, `schedule_adjustments.adjusted_by_id`, `schedule_occurrences.completed_by_id`, `system_config_versions.changed_by`, `task_transfer_logs.from_agent_id`, `task_transfer_logs.to_agent_id`, `task_transfer_logs.transferred_by_id`, `user_sessions.actual_user_id`, `user_sessions.shadow_user_id`, `visits_actions.acted_by_id`, `visits_actions.created_by_id`, `visits_actions.transferred_by_id`, `whatsapp_escalation_events.actor_user_id`, `whatsapp_escalations.assigned_to_user_id`, `whatsapp_escalations.resolved_by_user_id`, `whatsapp_messages.sender_user_id`, `whatsapp_messaging_permissions.granted_by`, `whatsapp_messaging_permissions.user_id`, `whatsapp_settings.updated_by_user_id`

### visits_actions

~198,738 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `patient_id` → patients.id | uuid | no |  |
| `visit_id` → patient_visits.id | uuid | yes |  |
| `created_by_id` → users.id | character varying(128) | yes |  |
| `acted_by_id` → users.id | character varying(128) | yes |  |
| `task_type_id` → task_types.id | uuid | yes |  |
| `action_type` | character varying(100) | yes |  |
| `status` | character varying(50) | no |  |
| `title` | character varying(255) | no |  |
| `description` | text | yes |  |
| `urgency` | character varying(50) | yes |  |
| `revenue_potential` | integer | yes |  |
| `source` | character varying(100) | yes |  |
| `evidence` | text | yes |  |
| `due_date` | timestamp with time zone | yes |  |
| `associated_appointment_id` | uuid | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `workflow_id` → workflows.id | uuid | yes |  |
| `workflow_type` | character varying(50) | yes |  |
| `workflow_status` | character varying(100) | yes |  |
| `workflow_sub_status` | character varying(100) | yes |  |
| `workflow_secondary_status` | character varying(100) | yes |  |
| `workflow_secondary_sub_status` | character varying(100) | yes |  |
| `follow_up_date` | date | yes |  |
| `status_action_date` | timestamp with time zone | yes |  |
| `agent_worked_status` | character varying | yes |  |
| `agent_worked_at` | timestamp with time zone | yes |  |
| `agent_id` | character varying | yes |  |
| `first_level_assigned_at` | timestamp without time zone | yes |  |
| `is_fitness_case` | boolean | yes | false |
| `transfer_doctor_name` | character varying(255) | yes |  |
| `transferred_at` | timestamp with time zone | yes |  |
| `transferred_by_id` → users.id | character varying(128) | yes |  |

Referenced by: `notifications.action_id`, `patient_schedules.visit_action_id`, `task_transfer_logs.visit_action_id`

### whatsapp_escalation_events

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `escalation_id` → whatsapp_escalations.id | uuid | no |  |
| `event_type` | character varying(40) | no |  |
| `from_status` | character varying(20) | yes |  |
| `to_status` | character varying(20) | yes |  |
| `actor_user_id` → users.id | character varying(128) | yes |  |
| `actor_role` | character varying(30) | yes |  |
| `payload` | jsonb | no | '{}'::jsonb |
| `note` | text | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### whatsapp_escalations

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `saheli_escalation_id` | bigint | no |  |
| `escalation_ref` | character varying(20) | no |  |
| `patient_id` → patients.id | uuid | yes |  |
| `patient_uhid` | character varying(50) | yes |  |
| `patient_name` | character varying(200) | yes |  |
| `phone` | character varying(20) | no |  |
| `tenant_id` | uuid | no |  |
| `hospital_id` → hospitals.id | uuid | yes |  |
| `center_id` → centers.id | uuid | yes |  |
| `department_id` | uuid | yes |  |
| `department_name` | character varying(200) | yes |  |
| `doctor_id` | uuid | yes |  |
| `escalation_type` | character varying(50) | yes |  |
| `follow_up_category` | character varying(50) | yes |  |
| `procedure_category` | character varying(50) | yes |  |
| `procedure_subcategory` | character varying(100) | yes |  |
| `category` | character varying(20) | yes |  |
| `emergency` | boolean | no | false |
| `severity` | character varying(20) | yes |  |
| `priority` | smallint | no | '3'::smallint |
| `status` | character varying(20) | no | 'open'::character varying |
| `assigned_to_user_id` → users.id | character varying(128) | yes |  |
| `assigned_to_email` | character varying(255) | yes |  |
| `confidence_score` | smallint | no | '0'::smallint |
| `needs_manual_review` | boolean | no | false |
| `trigger_source` | character varying(20) | no | 'chatbot'::character varying |
| `trigger_message` | text | yes |  |
| `reason` | text | yes |  |
| `notes` | text | yes |  |
| `ai_summary` | text | yes |  |
| `assignment_reason` | text | yes |  |
| `wa_assignment_sync_pending` | boolean | no | false |
| `wa_assignment_last_sync_attempt_at` | timestamp with time zone | yes |  |
| `wa_assignment_sync_error` | text | yes |  |
| `wa_resolution_sync_pending` | boolean | no | false |
| `wa_resolution_last_sync_attempt_at` | timestamp with time zone | yes |  |
| `wa_resolution_sync_error` | text | yes |  |
| `conversation_id` | character varying(50) | yes |  |
| `source_inbound_id` | bigint | yes |  |
| `signals` | jsonb | no | '{}'::jsonb |
| `unread_count` | integer | no | 0 |
| `last_inbound_at` | timestamp with time zone | yes |  |
| `last_outbound_at` | timestamp with time zone | yes |  |
| `last_event_at` | timestamp with time zone | no | '2026-05-28 12:22:23.339698+00'::timesta… |
| `sla_due_at` | timestamp with time zone | yes |  |
| `resolved_at` | timestamp with time zone | yes |  |
| `resolved_by_user_id` → users.id | character varying(128) | yes |  |
| `closed_at` | timestamp with time zone | yes |  |
| `archived` | boolean | no | false |
| `synced_from_saheli_at` | timestamp with time zone | no | '2026-05-28 12:22:23.339698+00'::timesta… |
| `sync_version` | integer | no | 1 |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

Referenced by: `patient_whatsapp_state.latest_escalation_id`, `whatsapp_escalation_events.escalation_id`, `whatsapp_messages.escalation_id`

### whatsapp_media

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `saheli_media_id` | bigint | no |  |
| `tenant_id` | uuid | no |  |
| `mime_type` | character varying(100) | yes |  |
| `meta_media_id` | character varying(200) | yes |  |
| `sha256` | character varying(64) | yes |  |
| `bytes` | integer | yes |  |
| `local_path` | text | yes |  |
| `kalaam_blob_url` | text | yes |  |
| `transcription` | text | yes |  |
| `transcription_lang` | character varying(10) | yes |  |
| `processing_status` | character varying(20) | no | 'pending'::character varying |
| `scanned_status` | character varying(20) | no | 'pending'::character varying |
| `original_filename` | character varying(255) | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

Referenced by: `whatsapp_messages.media_id`

### whatsapp_messages

~1 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `saheli_message_id` | bigint | no |  |
| `saheli_source_table` | character varying(30) | no |  |
| `escalation_id` → whatsapp_escalations.id | uuid | yes |  |
| `patient_id` → patients.id | uuid | yes |  |
| `phone` | character varying(20) | no |  |
| `tenant_id` | uuid | no |  |
| `direction` | character varying(10) | no |  |
| `sender_role` | character varying(30) | yes |  |
| `sender_user_id` → users.id | character varying(128) | yes |  |
| `message_type` | character varying(30) | no | 'text'::character varying |
| `body` | text | yes |  |
| `template_id` | character varying(100) | yes |  |
| `template_variables` | jsonb | yes |  |
| `media_id` → whatsapp_media.id | uuid | yes |  |
| `wamid` | character varying(100) | yes |  |
| `idempotency_key` | character varying(100) | yes |  |
| `status` | character varying(20) | yes |  |
| `error_code` | character varying(50) | yes |  |
| `error_message` | text | yes |  |
| `intent` | character varying(50) | yes |  |
| `is_internal_note` | boolean | no | false |
| `received_at` | timestamp with time zone | yes |  |
| `sent_at` | timestamp with time zone | yes |  |
| `delivered_at` | timestamp with time zone | yes |  |
| `read_at` | timestamp with time zone | yes |  |
| `failed_at` | timestamp with time zone | yes |  |
| `raw_payload` | jsonb | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### whatsapp_messaging_permissions

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `user_id` → users.id | character varying(128) | no |  |
| `granted_by` → users.id | character varying(128) | yes |  |
| `notes` | text | yes |  |
| `granted_at` | timestamp with time zone | no | now() |
| `revoked_at` | timestamp with time zone | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### whatsapp_settings

~1 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `hospital_id` → hospitals.id | uuid | yes |  |
| `backend_url` | text | no |  |
| `integration_api_key_encrypted` | text | yes |  |
| `admin_api_key_encrypted` | text | yes |  |
| `tenant_slug` | text | yes |  |
| `is_active` | boolean | no | true |
| `last_health_check_at` | timestamp with time zone | yes |  |
| `last_health_status` | text | yes |  |
| `last_health_message` | text | yes |  |
| `updated_by_user_id` → users.id | character varying(128) | yes |  |
| `id` 🔑 | uuid | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### workflow_buckets

~49 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no | gen_random_uuid() |
| `display_order` | integer | no |  |
| `config` | jsonb | yes |  |
| `is_visible` | boolean | no |  |
| `is_active` | boolean | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `workflow_id` → workflows.id | uuid | no |  |
| `bucket_code` | character varying(50) | no |  |
| `bucket_name` | character varying(100) | no |  |
| `bucket_type` | character varying(12) | no |  |

Referenced by: `task_types.default_bucket_id`, `workflow_statuses.bucket_id`

### workflow_rules

~0 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `workflow_id` → workflows.id | uuid | no |  |
| `rule_code` | character varying(50) | no |  |
| `rule_name` | character varying(100) | no |  |
| `description` | text | yes |  |
| `rule_type` | character varying(50) | no |  |
| `trigger_conditions` | jsonb | yes |  |
| `actions` | jsonb | yes |  |
| `priority` | integer | no |  |
| `is_active` | boolean | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |

### workflow_statuses

~84 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `is_active` | boolean | no |  |
| `config` | jsonb | yes |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `is_initial_state` | boolean | no |  |
| `workflow_id` → workflows.id | uuid | no |  |
| `bucket_id` → workflow_buckets.id | uuid | yes |  |
| `parent_status_id` → workflow_statuses.id | uuid | yes |  |
| `status_code` | character varying(50) | no |  |
| `status_name` | character varying(300) | no |  |
| `status_type` | character varying(20) | no |  |
| `is_terminal` | boolean | no |  |

Referenced by: `status_transitions.from_status_id`, `status_transitions.to_status_id`, `task_types.default_status_id`, `workflow_statuses.parent_status_id`

### workflows

~7 rows · PK: `id`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `id` 🔑 | uuid | no |  |
| `workflow_code` | character varying(50) | no |  |
| `workflow_name` | character varying(100) | no |  |
| `description` | text | yes |  |
| `has_patient_view` | boolean | no |  |
| `has_task_view` | boolean | no |  |
| `default_view` | character varying(20) | no |  |
| `agent_config` | jsonb | yes |  |
| `is_active` | boolean | no |  |
| `created_at` | timestamp with time zone | no | now() |
| `updated_at` | timestamp with time zone | no | now() |
| `workflow_entity_type` | character varying(100) | no |  |
| `priority` | integer | no | 0 |

Referenced by: `appointments.workflow_id`, `call_history.workflow_id`, `escalation_rules.workflow_id`, `escalations.workflow_id`, `patient_schedules.workflow_id`, `patient_visits.workflow_id`, `patients.workflow_id`, `status_transitions.workflow_id`, `system_config.workflow_id`, `task_types.workflow_id`, `visits_actions.workflow_id`, `workflow_buckets.workflow_id`, `workflow_rules.workflow_id`, `workflow_statuses.workflow_id`

## Relationship map (all foreign keys)

| From | To |
|---|---|
| `agent_presence.user_id` | `users.id` |
| `analytics_daily_summary.center_id` | `centers.id` |
| `analytics_daily_summary.user_id` | `users.id` |
| `analytics_events.center_id` | `centers.id` |
| `analytics_events.user_id` | `users.id` |
| `appointments.cancelled_by_id` | `users.id` |
| `appointments.completed_by_id` | `users.id` |
| `appointments.created_by_id` | `users.id` |
| `appointments.doctor_id` | `doctors.id` |
| `appointments.marked_by_id` | `users.id` |
| `appointments.patient_id` | `patients.id` |
| `appointments.rescheduled_from_id` | `appointments.id` |
| `appointments.visit_id` | `patient_visits.id` |
| `appointments.workflow_id` | `workflows.id` |
| `audit_logs.center_id` | `centers.id` |
| `audit_logs.user_id` | `users.id` |
| `bulk_import_batches.center_id` | `centers.id` |
| `bulk_import_batches.created_by_id` | `users.id` |
| `call_derived_analytics.call_history_id` | `call_history.id` |
| `call_derived_analytics.patient_id` | `patients.id` |
| `call_history.created_by_id` | `users.id` |
| `call_history.escalation_id` | `disposition_escalations.id` |
| `call_history.patient_id` | `patients.id` |
| `call_history.workflow_id` | `workflows.id` |
| `centers.hospital_id` | `hospitals.id` |
| `department_coordinator_mappings.center_id` | `centers.id` |
| `department_coordinator_mappings.coordinator_user_id` | `users.id` |
| `disposition_escalation_attachments.escalation_id` | `disposition_escalations.id` |
| `disposition_escalation_attachments.uploaded_by` | `users.id` |
| `disposition_escalation_configs.center_id` | `centers.id` |
| `disposition_escalation_configs.handler_user_id` | `users.id` |
| `disposition_escalation_events.actor_id` | `users.id` |
| `disposition_escalation_events.escalation_id` | `disposition_escalations.id` |
| `disposition_escalation_nudges.escalation_id` | `disposition_escalations.id` |
| `disposition_escalation_nudges.sent_by` | `users.id` |
| `disposition_escalation_nudges.sent_to` | `users.id` |
| `disposition_escalations.assigned_to` | `users.id` |
| `disposition_escalations.center_id` | `centers.id` |
| `disposition_escalations.config_id` | `disposition_escalation_configs.id` |
| `disposition_escalations.created_by` | `users.id` |
| `disposition_escalations.doctor_id` | `doctors.id` |
| `disposition_escalations.encounter_id` | `patient_visits.id` |
| `disposition_escalations.original_agent_id` | `users.id` |
| `disposition_escalations.patient_id` | `patients.id` |
| `doctor_coordinator_mappings.coordinator_user_id` | `users.id` |
| `doctors.department_id` | `departments.id` |
| `escalation_configs.updated_by` | `users.id` |
| `escalation_email_replies.escalation_id` | `escalations.escalation_id` |
| `escalation_history.changed_by` | `users.id` |
| `escalation_history.escalation_db_id` | `escalations.id` |
| `escalation_matrices.hospital_id` | `hospitals.id` |
| `escalation_rule_versions.changed_by` | `users.id` |
| `escalation_rule_versions.rule_id` | `escalation_rules.id` |
| `escalation_rules.center_id` | `centers.id` |
| `escalation_rules.created_by` | `users.id` |
| `escalation_rules.escalate_to_user` | `users.id` |
| `escalation_rules.updated_by` | `users.id` |
| `escalation_rules.workflow_id` | `workflows.id` |
| `escalations.assigned_to` | `users.id` |
| `escalations.center_id` | `centers.id` |
| `escalations.created_by` | `users.id` |
| `escalations.hospital_id` | `hospitals.id` |
| `escalations.rule_id` | `escalation_rules.id` |
| `escalations.workflow_id` | `workflows.id` |
| `floor_counsellor_mappings.center_id` | `centers.id` |
| `floor_counsellor_mappings.counsellor_user_id` | `users.id` |
| `legacy_escalation_rules.center_id` | `centers.id` |
| `legacy_escalation_rules.escalate_to_user` | `users.id` |
| `ni_caller_department_mappings.center_id` | `centers.id` |
| `ni_caller_department_mappings.user_id` | `users.id` |
| `notifications.action_id` | `visits_actions.id` |
| `notifications.user_id` | `users.id` |
| `notifications.visit_id` | `patient_visits.id` |
| `nursing_visit_log.doctor_id` | `doctors.id` |
| `patient_call_record_assets.call_record_id` | `patient_call_records.id` |
| `patient_call_records.patient_id` | `patients.id` |
| `patient_schedules.created_by_id` | `users.id` |
| `patient_schedules.patient_id` | `patients.id` |
| `patient_schedules.task_type_id` | `task_types.id` |
| `patient_schedules.visit_action_id` | `visits_actions.id` |
| `patient_schedules.workflow_id` | `workflows.id` |
| `patient_visits.doctor_id` | `doctors.id` |
| `patient_visits.patient_id` | `patients.id` |
| `patient_visits.prescription_id` | `prescriptions.id` |
| `patient_visits.workflow_id` | `workflows.id` |
| `patient_whatsapp_state.id` | `patients.id` |
| `patient_whatsapp_state.latest_escalation_id` | `whatsapp_escalations.id` |
| `patients.agent_id` | `users.id` |
| `patients.center_id` | `centers.id` |
| `patients.created_by_id` | `users.id` |
| `patients.workflow_id` | `workflows.id` |
| `prescription_files.prescription_id` | `prescriptions.id` |
| `prescription_files.uploaded_by` | `users.id` |
| `prescriptions.center_id` | `centers.id` |
| `prescriptions.patient_id` | `patients.id` |
| `prescriptions.processed_by` | `users.id` |
| `prescriptions.uploaded_by` | `users.id` |
| `prescriptions.verified_by` | `users.id` |
| `reminders.patient_id` | `patients.id` |
| `reminders.user_id` | `users.id` |
| `schedule_adjustments.adjusted_by_id` | `users.id` |
| `schedule_adjustments.occurrence_id` | `schedule_occurrences.id` |
| `schedule_adjustments.schedule_id` | `patient_schedules.id` |
| `schedule_occurrences.appointment_id` | `appointments.id` |
| `schedule_occurrences.completed_by_id` | `users.id` |
| `schedule_occurrences.patient_id` | `patients.id` |
| `schedule_occurrences.schedule_id` | `patient_schedules.id` |
| `schedule_occurrences.task_type_id` | `task_types.id` |
| `status_transitions.from_status_id` | `workflow_statuses.id` |
| `status_transitions.to_status_id` | `workflow_statuses.id` |
| `status_transitions.workflow_id` | `workflows.id` |
| `system_config.hospital_id` | `hospitals.id` |
| `system_config.workflow_id` | `workflows.id` |
| `system_config_versions.changed_by` | `users.id` |
| `system_config_versions.config_id` | `system_config.id` |
| `task_transfer_logs.from_agent_id` | `users.id` |
| `task_transfer_logs.patient_id` | `patients.id` |
| `task_transfer_logs.to_agent_id` | `users.id` |
| `task_transfer_logs.transferred_by_id` | `users.id` |
| `task_transfer_logs.visit_action_id` | `visits_actions.id` |
| `task_types.default_bucket_id` | `workflow_buckets.id` |
| `task_types.default_status_id` | `workflow_statuses.id` |
| `task_types.workflow_id` | `workflows.id` |
| `user_sessions.actual_user_id` | `users.id` |
| `user_sessions.shadow_user_id` | `users.id` |
| `users.center_id` | `centers.id` |
| `users.department_id` | `departments.id` |
| `users.role_id` | `roles.id` |
| `visits_actions.acted_by_id` | `users.id` |
| `visits_actions.created_by_id` | `users.id` |
| `visits_actions.patient_id` | `patients.id` |
| `visits_actions.task_type_id` | `task_types.id` |
| `visits_actions.transferred_by_id` | `users.id` |
| `visits_actions.visit_id` | `patient_visits.id` |
| `visits_actions.workflow_id` | `workflows.id` |
| `whatsapp_escalation_events.actor_user_id` | `users.id` |
| `whatsapp_escalation_events.escalation_id` | `whatsapp_escalations.id` |
| `whatsapp_escalations.assigned_to_user_id` | `users.id` |
| `whatsapp_escalations.center_id` | `centers.id` |
| `whatsapp_escalations.hospital_id` | `hospitals.id` |
| `whatsapp_escalations.patient_id` | `patients.id` |
| `whatsapp_escalations.resolved_by_user_id` | `users.id` |
| `whatsapp_messages.escalation_id` | `whatsapp_escalations.id` |
| `whatsapp_messages.media_id` | `whatsapp_media.id` |
| `whatsapp_messages.patient_id` | `patients.id` |
| `whatsapp_messages.sender_user_id` | `users.id` |
| `whatsapp_messaging_permissions.granted_by` | `users.id` |
| `whatsapp_messaging_permissions.user_id` | `users.id` |
| `whatsapp_settings.hospital_id` | `hospitals.id` |
| `whatsapp_settings.updated_by_user_id` | `users.id` |
| `workflow_buckets.workflow_id` | `workflows.id` |
| `workflow_rules.workflow_id` | `workflows.id` |
| `workflow_statuses.bucket_id` | `workflow_buckets.id` |
| `workflow_statuses.parent_status_id` | `workflow_statuses.id` |
| `workflow_statuses.workflow_id` | `workflows.id` |
