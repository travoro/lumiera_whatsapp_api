-- ============================================================================
-- Language Code Normalization Migration
-- ============================================================================
-- This migration normalizes all language values in the subcontractors table
-- from full language names (e.g., "french", "English") to ISO 639-1 codes
-- (e.g., "fr", "en") and adds a constraint to prevent future inconsistencies.
--
-- IMPORTANT: Review and test on staging before running on production!
-- ============================================================================

-- Step 1: Backup current language values (for verification)
DO $$
BEGIN
    RAISE NOTICE 'Current language distribution BEFORE migration:';
END $$;

SELECT language, COUNT(*) as count
FROM subcontractors
GROUP BY language
ORDER BY count DESC;

-- Step 2: Normalize existing data to ISO 639-1 codes
UPDATE subcontractors
SET language = CASE
    -- French variants
    WHEN LOWER(TRIM(language)) IN ('french', 'français', 'francais', 'fr') THEN 'fr'

    -- English variants
    WHEN LOWER(TRIM(language)) IN ('english', 'anglais', 'en') THEN 'en'

    -- Spanish variants
    WHEN LOWER(TRIM(language)) IN ('spanish', 'español', 'espanol', 'espagnol', 'es') THEN 'es'

    -- Portuguese variants
    WHEN LOWER(TRIM(language)) IN ('portuguese', 'português', 'portugues', 'portugais', 'pt') THEN 'pt'

    -- Romanian variants
    WHEN LOWER(TRIM(language)) IN ('romanian', 'română', 'romana', 'roumain', 'ro') THEN 'ro'

    -- Arabic variants
    WHEN LOWER(TRIM(language)) IN ('arabic', 'العربية', 'arabe', 'ar') THEN 'ar'

    -- German variants
    WHEN LOWER(TRIM(language)) IN ('german', 'deutsch', 'allemand', 'de') THEN 'de'

    -- Italian variants
    WHEN LOWER(TRIM(language)) IN ('italian', 'italiano', 'italien', 'it') THEN 'it'

    -- Czech variants
    WHEN LOWER(TRIM(language)) IN ('czech', 'čeština', 'cestina', 'tchèque', 'cs') THEN 'cs'

    -- Slovak variants
    WHEN LOWER(TRIM(language)) IN ('slovak', 'slovenčina', 'slovencina', 'slovaque', 'sk') THEN 'sk'

    -- Hungarian variants
    WHEN LOWER(TRIM(language)) IN ('hungarian', 'magyar', 'hongrois', 'hu') THEN 'hu'

    -- Bulgarian variants
    WHEN LOWER(TRIM(language)) IN ('bulgarian', 'български', 'bulgare', 'bg') THEN 'bg'

    -- Serbian variants
    WHEN LOWER(TRIM(language)) IN ('serbian', 'српски', 'serbe', 'sr') THEN 'sr'

    -- Croatian variants
    WHEN LOWER(TRIM(language)) IN ('croatian', 'hrvatski', 'croate', 'hr') THEN 'hr'

    -- Slovenian variants
    WHEN LOWER(TRIM(language)) IN ('slovenian', 'slovenščina', 'slovenian', 'slovène', 'sl') THEN 'sl'

    -- Ukrainian variants
    WHEN LOWER(TRIM(language)) IN ('ukrainian', 'українська', 'ukrainien', 'uk') THEN 'uk'

    -- Russian variants
    WHEN LOWER(TRIM(language)) IN ('russian', 'русский', 'russe', 'ru') THEN 'ru'

    -- Lithuanian variants
    WHEN LOWER(TRIM(language)) IN ('lithuanian', 'lietuvių', 'lituanien', 'lt') THEN 'lt'

    -- Latvian variants
    WHEN LOWER(TRIM(language)) IN ('latvian', 'latviešu', 'letton', 'lv') THEN 'lv'

    -- Estonian variants
    WHEN LOWER(TRIM(language)) IN ('estonian', 'eesti', 'estonien', 'et') THEN 'et'

    -- Albanian variants
    WHEN LOWER(TRIM(language)) IN ('albanian', 'shqip', 'albanais', 'sq') THEN 'sq'

    -- Macedonian variants
    WHEN LOWER(TRIM(language)) IN ('macedonian', 'македонски', 'macédonien', 'mk') THEN 'mk'

    -- Bosnian variants
    WHEN LOWER(TRIM(language)) IN ('bosnian', 'bosanski', 'bosnien', 'bs') THEN 'bs'

    -- Polish variants
    WHEN LOWER(TRIM(language)) IN ('polish', 'polski', 'polonais', 'pl') THEN 'pl'

    -- Default to French for NULL or unknown values
    ELSE 'fr'
END
WHERE language IS NOT NULL;

-- Handle NULL values
UPDATE subcontractors
SET language = 'fr'
WHERE language IS NULL;

-- Step 3: Verify normalization results
DO $$
BEGIN
    RAISE NOTICE 'Language distribution AFTER normalization:';
END $$;

SELECT language, COUNT(*) as count
FROM subcontractors
GROUP BY language
ORDER BY count DESC;

-- Step 4: Check for any unexpected values (should be empty)
DO $$
DECLARE
    unexpected_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO unexpected_count
    FROM subcontractors
    WHERE language NOT IN ('fr', 'en', 'es', 'pt', 'ro', 'ar', 'de', 'it',
                           'cs', 'sk', 'hu', 'bg', 'sr', 'hr', 'sl', 'uk',
                           'ru', 'lt', 'lv', 'et', 'sq', 'mk', 'bs', 'pl');

    IF unexpected_count > 0 THEN
        RAISE WARNING 'Found % rows with unexpected language codes!', unexpected_count;
        RAISE NOTICE 'Unexpected language values:';

        -- Show unexpected values
        PERFORM language, COUNT(*)
        FROM subcontractors
        WHERE language NOT IN ('fr', 'en', 'es', 'pt', 'ro', 'ar', 'de', 'it',
                               'cs', 'sk', 'hu', 'bg', 'sr', 'hr', 'sl', 'uk',
                               'ru', 'lt', 'lv', 'et', 'sq', 'mk', 'bs', 'pl')
        GROUP BY language;
    ELSE
        RAISE NOTICE '✓ All language codes are valid ISO 639-1 codes';
    END IF;
END $$;

-- Step 5: Add CHECK constraint to enforce ISO 639-1 codes going forward
-- First, check if constraint already exists
DO $$
BEGIN
    -- Try to add constraint
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_name = 'language_iso_code_check'
        AND table_name = 'subcontractors'
    ) THEN
        ALTER TABLE subcontractors
        ADD CONSTRAINT language_iso_code_check
        CHECK (language IN (
            'fr',  -- French
            'en',  -- English
            'es',  -- Spanish
            'pt',  -- Portuguese
            'ro',  -- Romanian
            'ar',  -- Arabic
            'de',  -- German
            'it',  -- Italian
            'cs',  -- Czech
            'sk',  -- Slovak
            'hu',  -- Hungarian
            'bg',  -- Bulgarian
            'sr',  -- Serbian
            'hr',  -- Croatian
            'sl',  -- Slovenian
            'uk',  -- Ukrainian
            'ru',  -- Russian
            'lt',  -- Lithuanian
            'lv',  -- Latvian
            'et',  -- Estonian
            'sq',  -- Albanian
            'mk',  -- Macedonian
            'bs',  -- Bosnian
            'pl'   -- Polish
        ));

        RAISE NOTICE '✓ CHECK constraint added successfully';
    ELSE
        RAISE NOTICE 'ℹ CHECK constraint already exists';
    END IF;
END $$;

-- Step 6: Final verification
DO $$
DECLARE
    total_rows INTEGER;
    valid_codes INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_rows FROM subcontractors;
    SELECT COUNT(*) INTO valid_codes FROM subcontractors
    WHERE language IN ('fr', 'en', 'es', 'pt', 'ro', 'ar', 'de', 'it',
                       'cs', 'sk', 'hu', 'bg', 'sr', 'hr', 'sl', 'uk',
                       'ru', 'lt', 'lv', 'et', 'sq', 'mk', 'bs', 'pl');

    RAISE NOTICE '============================================';
    RAISE NOTICE 'Migration Summary:';
    RAISE NOTICE 'Total subcontractors: %', total_rows;
    RAISE NOTICE 'Valid ISO language codes: %', valid_codes;

    IF total_rows = valid_codes THEN
        RAISE NOTICE '✓ SUCCESS: All language codes normalized';
    ELSE
        RAISE WARNING '⚠ WARNING: % rows have invalid codes', (total_rows - valid_codes);
    END IF;
    RAISE NOTICE '============================================';
END $$;

-- ============================================================================
-- Rollback Instructions (if needed)
-- ============================================================================
-- To remove the constraint:
-- ALTER TABLE subcontractors DROP CONSTRAINT IF EXISTS language_iso_code_check;
--
-- To restore a specific value (example):
-- UPDATE subcontractors SET language = 'french' WHERE id = '<uuid>';
-- ============================================================================
