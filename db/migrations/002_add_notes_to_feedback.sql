-- Migration: Add notes column to feedback table
-- This adds support for storing user notes with feedback

ALTER TABLE feedback 
  ADD COLUMN IF NOT EXISTS notes TEXT;

COMMENT ON COLUMN feedback.notes IS 'Optional notes from user providing feedback';

