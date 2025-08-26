-- Set a safe default for mention.span so inserts without explicit span
-- still satisfy NOT NULL via PRIMARY KEY (chunk_id, ent_id, span).
-- An empty range int4range(0,0) is non-null and deterministic.
ALTER TABLE mention
  ALTER COLUMN span SET DEFAULT int4range(0,0);

