-- =========================================================================
-- PASO 1: Poblar la dimensión de tiempo (dim_time)
-- =========================================================================
WITH meses_numeros AS (
    SELECT DISTINCT 
        CAST(ano AS INT) as anio, 
        TRIM(mes) as mes_txt,
        CASE LOWER(TRIM(mes))
            WHEN 'enero'      THEN 1 WHEN 'febrero'    THEN 2 WHEN 'marzo'      THEN 3
            WHEN 'abril'      THEN 4 WHEN 'mayo'       THEN 5 WHEN 'junio'      THEN 6
            WHEN 'julio'      THEN 7 WHEN 'agosto'     THEN 8 WHEN 'septiembre' THEN 9
            WHEN 'octubre'    THEN 10 WHEN 'noviembre'  THEN 11 WHEN 'diciembre'  THEN 12
        END as mes_num
    FROM (
        SELECT ano, mes FROM staging_desembolsos UNION
        SELECT ano, mes FROM staging_cartera UNION
        SELECT ano, mes FROM staging_areas UNION
        SELECT ano, mes FROM staging_destinos
    ) sub 
    WHERE ano IS NOT NULL
),
fechas_calculadas AS (
    SELECT 
        make_date(anio, mes_num, 1) as date_key, 
        anio as year_num,
        mes_num as month_num,
        mes_txt as month_name,
        CASE 
            WHEN mes_num BETWEEN 1 AND 3 THEN 1
            WHEN mes_num BETWEEN 4 AND 6 THEN 2
            WHEN mes_num BETWEEN 7 AND 9 THEN 3
            ELSE 4
        END as quarter
    FROM meses_numeros
    WHERE mes_num IS NOT NULL
)
INSERT INTO public.dim_time (date_key, year_num, month_num, month_name, quarter)
SELECT date_key, year_num, month_num, month_name, quarter 
FROM fechas_calculadas
ON CONFLICT (date_key) DO NOTHING;


-- =========================================================================
-- PASO 2: Cargar fact_transactions
-- =========================================================================
TRUNCATE TABLE public.fact_transactions RESTART IDENTITY CASCADE;

INSERT INTO public.fact_transactions (branch_id, time_id, disbursed_amount, collected_amount)
SELECT 
    b.id as branch_id,
    t.id as time_id,
    COALESCE(CAST(NULLIF(s.desembolsos, '') AS NUMERIC(15,2)), 0.00),
    COALESCE(CAST(NULLIF(s.cobros, '') AS NUMERIC(15,2)), 0.00)
FROM public.staging_desembolsos s
JOIN public.branch b ON 
    TRIM(LOWER(b.name)) = TRIM(LOWER(s.sucursal)) OR 
    POSITION(TRIM(LOWER(s.sucursal)) IN TRIM(LOWER(b.name))) > 0 OR
    POSITION(TRIM(LOWER(b.name)) IN TRIM(LOWER(s.sucursal))) > 0
JOIN public.dim_time t ON t.year_num = CAST(s.ano AS INT) AND TRIM(LOWER(t.month_name)) = TRIM(LOWER(s.mes));


-- =========================================================================
-- PASO 3: Cargar fact_loan_portfolio
-- =========================================================================
TRUNCATE TABLE public.fact_loan_portfolio RESTART IDENTITY CASCADE;

INSERT INTO public.fact_loan_portfolio (branch_id, time_id, active_loans_count, outstanding_balance, past_due_balance)
SELECT 
    b.id as branch_id,
    t.id as time_id,
	COALESCE(s.prestamos_activos, 0) AS prestamos_activos,
	COALESCE(CAST(NULLIF(s.balance_pendiente, '') AS NUMERIC(15,2)), 0.00),
    COALESCE(CAST(NULLIF(s.balance_vencido, '') AS NUMERIC(15,2)), 0.00)
FROM public.staging_cartera s
JOIN public.branch b ON 
    TRIM(LOWER(b.name)) = TRIM(LOWER(s.sucursal)) OR 
    POSITION(TRIM(LOWER(s.sucursal)) IN TRIM(LOWER(b.name))) > 0 OR
    POSITION(TRIM(LOWER(b.name)) IN TRIM(LOWER(s.sucursal))) > 0
JOIN public.dim_time t ON t.year_num = CAST(s.ano AS INT) AND TRIM(LOWER(t.month_name)) = TRIM(LOWER(s.mes));


-- =========================================================================
-- PASO 4: Cargar fact_financed_areas
-- =========================================================================
TRUNCATE TABLE public.fact_financed_areas RESTART IDENTITY CASCADE;

INSERT INTO public.fact_financed_areas (branch_id, time_id, financed_area_tasks, borrowers_count)
SELECT 
    b.id as branch_id,
    t.id as time_id,
    -- Con este doble NULLIF, si encuentra '-' lo vuelve NULL y COALESCE lo convierte a 0.00 o 0
    COALESCE(CAST(NULLIF(NULLIF(TRIM(s.tareas_financiadas), ''), '-') AS NUMERIC(12,2)), 0.00),
    COALESCE(CAST(NULLIF(NULLIF(TRIM(s.beneficiarios), ''), '-') AS INT), 0)
FROM public.staging_areas s
JOIN public.branch b ON 
    TRIM(LOWER(b.name)) = TRIM(LOWER(s.sucursal)) OR 
    POSITION(TRIM(LOWER(s.sucursal)) IN TRIM(LOWER(b.name))) > 0 OR
    POSITION(TRIM(LOWER(b.name)) IN TRIM(LOWER(s.sucursal))) > 0
JOIN public.dim_time t ON t.year_num = CAST(s.ano AS INT) AND TRIM(LOWER(t.month_name)) = TRIM(LOWER(s.mes));


-- =========================================================================
-- PASO 5: Cargar fact_disbursements_by_destination
-- =========================================================================
TRUNCATE TABLE public.fact_disbursements_by_destination RESTART IDENTITY CASCADE;

INSERT INTO public.fact_disbursements_by_destination (branch_id, time_id, destination_name, disbursed_amount)
SELECT 
    b.id as branch_id,
    t.id as time_id,
    s.destino,
    COALESCE(CAST(NULLIF(s.monto_disbursado, '') AS NUMERIC(15,2)), 0.00)
FROM public.staging_destinos s
JOIN public.branch b ON 
    TRIM(LOWER(b.name)) = TRIM(LOWER(s.sucursal)) OR 
    POSITION(TRIM(LOWER(s.sucursal)) IN TRIM(LOWER(b.name))) > 0 OR
    POSITION(TRIM(LOWER(b.name)) IN TRIM(LOWER(s.sucursal))) > 0
JOIN public.dim_time t ON t.year_num = CAST(s.ano AS INT) AND TRIM(LOWER(t.month_name)) = TRIM(LOWER(s.mes));