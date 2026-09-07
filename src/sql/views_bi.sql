-- =========================================================================
-- BI VIEWS — Power BI / Tableau
--
-- Run this file once against the target database to create the views below.
-- Then, in Power BI or Tableau, connect to Postgres and either:
--   (a) pick these views directly from the table/view list (simplest), or
--   (b) paste the view name into a Custom SQL source (e.g. "SELECT * FROM
--       public.vw_payroll_cost_by_branch_month") if you need Direct Query
--       with extra filters.
--
-- Views are grouped by domain: payroll (Nomina) and financial (Cartera).
-- =========================================================================


-- =========================================================================
-- PAYROLL DOMAIN
-- =========================================================================

-- 1. Total payroll cost and headcount per branch/division, per pay run.
--    Use for: cost trend lines, branch comparison bar charts.
CREATE OR REPLACE VIEW public.vw_payroll_cost_by_branch_month AS
SELECT
    p.payroll_date AS fecha,
    b.name AS sucursal,
    d.name AS division,
    SUM(pd.salary::numeric) AS total_gasto_salarial,
    COUNT(DISTINCT pd.employee_id) AS total_empleados,
    ROUND(AVG(pd.salary::numeric), 2) AS salario_promedio
FROM public.payroll_detail pd
JOIN public.payroll p ON p.id = pd.payroll_id
JOIN public.employee_position_history h ON h.id = pd.employee_position_history_id
JOIN public.department_position dp ON dp.id = h.department_position_id
JOIN public.department dpt ON dpt.id = dp.department_id
JOIN public.branch b ON b.id = dpt.branch_id
JOIN public.division d ON d.id = dpt.division_id
GROUP BY p.payroll_date, b.name, d.name;


-- 2. Headcount by department, per pay run.
--    Use for: org-size drill-down (branch -> division -> department).
CREATE OR REPLACE VIEW public.vw_headcount_by_department AS
SELECT
    p.payroll_date AS fecha,
    b.name AS sucursal,
    d.name AS division,
    dpt.name AS departamento,
    COUNT(DISTINCT pd.employee_id) AS cantidad_empleados
FROM public.payroll_detail pd
JOIN public.payroll p ON p.id = pd.payroll_id
JOIN public.employee_position_history h ON h.id = pd.employee_position_history_id
JOIN public.department_position dp ON dp.id = h.department_position_id
JOIN public.department dpt ON dpt.id = dp.department_id
JOIN public.branch b ON b.id = dpt.branch_id
JOIN public.division d ON d.id = dpt.division_id
GROUP BY p.payroll_date, b.name, d.name, dpt.name;


-- 3. Gender diversity and pay gap, by position/department, per pay run.
--    Use for: diversity dashboards, salary-gap analysis.
CREATE OR REPLACE VIEW public.vw_gender_diversity AS
SELECT
    p.payroll_date AS fecha,
    d.name AS division,
    dpt.name AS departamento,
    pos.name AS posicion,
    COALESCE(e.gender, 'N') AS genero,
    COUNT(DISTINCT e.id) AS cantidad_empleados,
    ROUND(AVG(pd.salary::numeric), 2) AS salario_promedio
FROM public.payroll_detail pd
JOIN public.payroll p ON p.id = pd.payroll_id
JOIN public.employee e ON e.id = pd.employee_id
JOIN public.employee_position_history h ON h.id = pd.employee_position_history_id
JOIN public.department_position dp ON dp.id = h.department_position_id
JOIN public.position pos ON pos.id = dp.position_id
JOIN public.department dpt ON dpt.id = dp.department_id
JOIN public.division d ON d.id = dpt.division_id
GROUP BY p.payroll_date, d.name, dpt.name, pos.name, e.gender;


-- 4. Current snapshot of active employees (one row per active employee).
--    Use for: headcount cards, tenure histograms, current org chart tables.
CREATE OR REPLACE VIEW public.vw_employee_current_snapshot AS
SELECT
    e.id AS employee_id,
    e.name,
    e.gender,
    e.status,
    e.hire_date,
    ROUND(
        EXTRACT(YEAR FROM AGE(CURRENT_DATE, e.hire_date))::numeric
        + EXTRACT(MONTH FROM AGE(CURRENT_DATE, e.hire_date))::numeric / 12,
        1
    ) AS antiguedad_anios,
    te.description AS tipo_empleado,
    b.name AS sucursal,
    d.name AS division,
    dpt.name AS departamento,
    pos.name AS posicion,
    h.salary AS salario_actual
FROM public.employee e
JOIN public.type_employee te ON te.id = e.type_employee_id
JOIN public.department_position dp ON dp.id = e.department_position_id
JOIN public.department dpt ON dpt.id = dp.department_id
JOIN public.branch b ON b.id = dpt.branch_id
JOIN public.division d ON d.id = dpt.division_id
JOIN public.position pos ON pos.id = dp.position_id
LEFT JOIN public.employee_position_history h
    ON h.employee_id = e.id AND h.end_date IS NULL
WHERE e.status = TRUE;


-- 5. Salary bands: base salary vs. what's actually being paid, by position.
--    Use for: compensation review, outlier detection (real pay far from base).
CREATE OR REPLACE VIEW public.vw_salary_band_by_position AS
SELECT
    pos.name AS posicion,
    dpt.name AS departamento,
    dp.base_salary,
    MIN(h.salary) AS salario_minimo_real,
    MAX(h.salary) AS salario_maximo_real,
    ROUND(AVG(h.salary::numeric), 2) AS salario_promedio_real,
    COUNT(DISTINCT h.employee_id) AS empleados
FROM public.employee_position_history h
JOIN public.department_position dp ON dp.id = h.department_position_id
JOIN public.position pos ON pos.id = dp.position_id
JOIN public.department dpt ON dpt.id = dp.department_id
GROUP BY pos.name, dpt.name, dp.base_salary;


-- 6. Position/salary change history per employee (promotions, transfers, raises).
--    Use for: mobility analysis, time-since-last-change, raise magnitude.
CREATE OR REPLACE VIEW public.vw_position_changes AS
SELECT
    e.id AS employee_id,
    e.name,
    pos.name AS posicion,
    dpt.name AS departamento,
    h.start_date,
    h.end_date,
    h.salary,
    LAG(h.salary) OVER (PARTITION BY h.employee_id ORDER BY h.start_date) AS salario_anterior,
    ROW_NUMBER() OVER (PARTITION BY h.employee_id ORDER BY h.start_date) AS numero_de_puesto
FROM public.employee_position_history h
JOIN public.employee e ON e.id = h.employee_id
JOIN public.department_position dp ON dp.id = h.department_position_id
JOIN public.position pos ON pos.id = dp.position_id
JOIN public.department dpt ON dpt.id = dp.department_id;


-- =========================================================================
-- FINANCIAL DOMAIN
-- =========================================================================

-- 7. Branch-month financial summary: disbursed/collected cash flow plus
--    portfolio health (past-due ratio).
--    Use for: the main financial KPI dashboard, branch comparison.
CREATE OR REPLACE VIEW public.vw_financial_summary_by_branch_month AS
SELECT
    t.date_key AS fecha,
    t.year_num,
    t.month_name,
    t.quarter,
    b.name AS sucursal,
    ft.disbursed_amount,
    ft.collected_amount,
    flp.active_loans_count,
    flp.outstanding_balance,
    flp.past_due_balance,
    CASE WHEN flp.outstanding_balance > 0
         THEN ROUND(flp.past_due_balance / flp.outstanding_balance * 100, 2)
         ELSE 0
    END AS pct_mora
FROM public.dim_time t
JOIN public.fact_transactions ft ON ft.time_id = t.id
JOIN public.fact_loan_portfolio flp ON flp.time_id = t.id AND flp.branch_id = ft.branch_id
JOIN public.branch b ON b.id = ft.branch_id;


-- 8. Disbursements by destination (loan purpose), with share-of-branch %.
--    Use for: destination mix pie/treemap, trend by destination over time.
CREATE OR REPLACE VIEW public.vw_disbursements_by_destination AS
SELECT
    t.date_key AS fecha,
    b.name AS sucursal,
    f.destination_name AS destino,
    f.disbursed_amount,
    ROUND(
        f.disbursed_amount / SUM(f.disbursed_amount) OVER (PARTITION BY t.date_key, b.name) * 100,
        2
    ) AS pct_del_total_sucursal
FROM public.fact_disbursements_by_destination f
JOIN public.dim_time t ON t.id = f.time_id
JOIN public.branch b ON b.id = f.branch_id;


-- 9. Financed area / borrower reach trend.
--    Use for: agricultural-impact reporting (hectares financed per borrower).
CREATE OR REPLACE VIEW public.vw_financed_areas_trend AS
SELECT
    t.date_key AS fecha,
    b.name AS sucursal,
    fa.financed_area_tasks,
    fa.borrowers_count,
    CASE WHEN fa.borrowers_count > 0
         THEN ROUND(fa.financed_area_tasks / fa.borrowers_count, 2)
         ELSE 0
    END AS tareas_promedio_por_beneficiario
FROM public.fact_financed_areas fa
JOIN public.dim_time t ON t.id = fa.time_id
JOIN public.branch b ON b.id = fa.branch_id;
