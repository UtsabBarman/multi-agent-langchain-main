-- Add columns for agent->user validation (pause/resume).
-- Run after 001_initial_sqlite.sql.

ALTER TABLE app_requests ADD COLUMN paused_at_step INTEGER;
ALTER TABLE app_requests ADD COLUMN validation_payload TEXT;
