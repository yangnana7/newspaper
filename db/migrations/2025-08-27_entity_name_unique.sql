-- Create a unique index on entity name stored in attrs->>'name'
-- Note: unique constraint on expression isn't supported; use a unique index.
CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_name ON entity ((attrs->>'name')) WHERE (attrs ? 'name');

