-- ============================================================
-- Database Migration Script: Normalize Breaker Categories
-- Purpose: Convert English breaker category names to Greek
-- Date: 2026-01-31
-- ============================================================

-- IMPORTANT: Run this script only once after taking a backup!
-- This will update existing circuit breaker records to use Greek category names

-- Step 1: Display current breaker category values (for verification)
SELECT DISTINCT breaker_category, COUNT(*) as count
FROM elements
WHERE element_type IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ')
GROUP BY breaker_category;

-- Step 2: Update English category names to Greek equivalents
-- Convert "Vacuum" to "Κενού"
UPDATE elements
SET breaker_category = 'Κενού'
WHERE breaker_category = 'Vacuum'
  AND element_type IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ');

-- Convert "Oil" to "Πτωχού Ελαίου"
UPDATE elements
SET breaker_category = 'Πτωχού Ελαίου'
WHERE breaker_category = 'Oil'
  AND element_type IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ');

-- "SF6" remains the same (already correct)

-- Step 3: Update element_models table (same logic)
SELECT DISTINCT breaker_category, COUNT(*) as count
FROM element_models
WHERE element_category IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ')
GROUP BY breaker_category;

UPDATE element_models
SET breaker_category = 'Κενού'
WHERE breaker_category = 'Vacuum'
  AND element_category IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ');

UPDATE element_models
SET breaker_category = 'Πτωχού Ελαίου'
WHERE breaker_category = 'Oil'
  AND element_category IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ');

-- Step 4: Verify results after migration
SELECT 'Elements Table - After Migration' as table_name;
SELECT DISTINCT breaker_category, COUNT(*) as count
FROM elements
WHERE element_type IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ')
GROUP BY breaker_category;

SELECT 'Models Table - After Migration' as table_name;
SELECT DISTINCT breaker_category, COUNT(*) as count
FROM element_models
WHERE element_category IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ')
GROUP BY breaker_category;

-- Step 5: Find breakers with NULL or invalid categories (needs manual review)
SELECT id, name, element_type, breaker_category, substation_id
FROM elements
WHERE element_type IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ')
  AND (breaker_category IS NULL 
       OR breaker_category NOT IN ('SF6', 'Κενού', 'Πτωχού Ελαίου'));

-- ============================================================
-- ROLLBACK SCRIPT (if needed - SAVE THIS!)
-- ============================================================
-- If you need to revert, uncomment and run these:
/*
UPDATE elements
SET breaker_category = 'Vacuum'
WHERE breaker_category = 'Κενού'
  AND element_type IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ');

UPDATE elements
SET breaker_category = 'Oil'
WHERE breaker_category = 'Πτωχού Ελαίου'
  AND element_type IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ');

UPDATE element_models
SET breaker_category = 'Vacuum'
WHERE breaker_category = 'Κενού'
  AND element_category IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ');

UPDATE element_models
SET breaker_category = 'Oil'
WHERE breaker_category = 'Πτωχού Ελαίου'
  AND element_category IN ('Διακόπτης ΜΤ', 'Διακόπτης ΥΤ');
*/
