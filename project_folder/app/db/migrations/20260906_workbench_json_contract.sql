-- MANUAL migration for existing databases. Not read by bootstrap, not executed here.
-- No data rewrite: old result_info objects without workbench remain valid.
BEGIN;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'result_info_object'
                   AND conrelid = 'core.result'::regclass) THEN
        ALTER TABLE core.result ADD CONSTRAINT result_info_object
            CHECK (jsonb_typeof(result_info) = 'object') NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'result_workbench_object'
                   AND conrelid = 'core.result'::regclass) THEN
        ALTER TABLE core.result ADD CONSTRAINT result_workbench_object
            CHECK (NOT (result_info ? 'workbench') OR jsonb_typeof(result_info->'workbench') = 'object') NOT VALID;
    END IF;
END $$;
-- Stops if historical rows violate the contract; review them before retrying.
ALTER TABLE core.result VALIDATE CONSTRAINT result_info_object;
ALTER TABLE core.result VALIDATE CONSTRAINT result_workbench_object;
COMMIT;
