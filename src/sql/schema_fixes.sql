-- =========================================================================
-- Fix: missing UNIQUE constraints that orquestacion_modelo.sql assumes exist.
--
-- orquestacion_modelo.sql uses bare `ON CONFLICT DO NOTHING` (no target
-- columns) for type_employee, position, employee, and payroll. In Postgres
-- that clause only suppresses an error if a UNIQUE/PK constraint actually
-- exists to trigger a conflict — without one, it's a silent no-op and every
-- pipeline rerun inserts duplicate rows. `division` already had its
-- constraint; these four didn't, and the live database had accumulated
-- massive duplication as a result (verified 2026-09-07, tables truncated
-- and rebuilt after this fix).
--
-- Safe to run more than once: each block only adds the constraint if it
-- isn't already there.
-- =========================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'type_employee_description_key'
    ) THEN
        ALTER TABLE public.type_employee ADD CONSTRAINT type_employee_description_key UNIQUE (description);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'position_name_key'
    ) THEN
        ALTER TABLE public.position ADD CONSTRAINT position_name_key UNIQUE (name);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'employee_name_key'
    ) THEN
        ALTER TABLE public.employee ADD CONSTRAINT employee_name_key UNIQUE (name);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'payroll_payroll_date_key'
    ) THEN
        ALTER TABLE public.payroll ADD CONSTRAINT payroll_payroll_date_key UNIQUE (payroll_date);
    END IF;
END $$;
