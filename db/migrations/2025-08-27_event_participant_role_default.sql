-- Ensure event_participant.role has a sensible default to avoid NOT NULL violations
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='event_participant' AND column_name='role' AND column_default IS NOT NULL
  ) THEN
    EXECUTE 'ALTER TABLE event_participant ALTER COLUMN role SET DEFAULT ''participant''';
  END IF;
END$$;

