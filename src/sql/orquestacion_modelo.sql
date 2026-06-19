-- public.division
INSERT INTO public.division (name)
SELECT DISTINCT direccion FROM public.staging_excel 
WHERE direccion IS NOT NULL AND direccion <> ''
ON CONFLICT DO NOTHING;

-- public.type_employee
INSERT INTO public.type_employee (description)
SELECT DISTINCT estatus FROM public.staging_excel WHERE estatus IS NOT NULL
ON CONFLICT DO NOTHING;

-- public.department
INSERT INTO public.department (name, branch_id, division_id)
SELECT DISTINCT 
    se.departamento, 
    b.id AS branch_id,
    d.id AS division_id
FROM public.staging_excel se
INNER JOIN public.branch b ON b.id = se.sucursal::INT
INNER JOIN public.division d ON d.name = se.direccion
WHERE se.departamento IS NOT NULL AND se.departamento <> ''
ON CONFLICT (branch_id, division_id, name) DO NOTHING;

-- public.position
INSERT INTO public.position (name)
SELECT DISTINCT posicion FROM public.staging_excel WHERE posicion IS NOT NULL
ON CONFLICT DO NOTHING;

-- public.department_position
INSERT INTO public.department_position (department_id, position_id, base_salary)
SELECT DISTINCT 
	dpt.id AS department_id, p.id AS position_id, 
	MIN(se.sueldo_nominal)::numeric::money AS base_salary
FROM public.staging_excel se
INNER JOIN public.branch b ON b.id = se.sucursal::INT
INNER JOIN public.division d ON d.name = se.direccion
INNER JOIN public.department dpt ON dpt.name = se.departamento AND dpt.branch_id = b.id AND dpt.division_id = d.id
INNER JOIN public.position p ON p.name = se.posicion
GROUP BY dpt.id, p.id
ON CONFLICT (department_id, position_id) DO NOTHING;

-- public.employee (Manejo inteligente del género basado en la última fecha registrada)
INSERT INTO public.employee (name, gender, type_employee_id, department_position_id, status, hire_date)
WITH consulta_empleados AS (
    SELECT 
        CONCAT(se.nombres, ' ', se.apellidos) AS nombre_completo,
        se.sucursal::INT AS sucursal_id, 
        se.direccion AS division_name, 
        se.departamento AS department_name, 
        se.posicion AS position_name, 
        --se.estatus AS estatus_name, 
		LAST_VALUE(se.estatus) OVER(
            PARTITION BY se.nombres, se.apellidos 
            ORDER BY CASE WHEN se.estatus IS NOT NULL AND se.estatus != '' THEN 0 ELSE 1 END, se.fecha DESC
        ) AS estatus_name,
        se.fecha,
        
        -- 1. Rescatamos el primer género que NO sea nulo en todo su historial
        FIRST_VALUE(se.genero) OVER(
            PARTITION BY se.nombres, se.apellidos 
            ORDER BY CASE WHEN se.genero IS NOT NULL AND se.genero != '' THEN 0 ELSE 1 END, se.fecha DESC
        ) AS genero_consolidado,
        
        -- 2. Aseguramos la fecha de contratación más antigua registrada para esa persona
        MIN(CAST(NULLIF(TRIM(se.fecha_contratacion), '') AS DATE)) OVER(
            PARTITION BY se.nombres, se.apellidos
        ) AS fecha_contratacion_minima,
        
        -- 3. Identificamos el registro con su situación laboral y puesto más reciente
        ROW_NUMBER() OVER(
            PARTITION BY se.nombres, se.apellidos 
            ORDER BY se.fecha DESC
        ) AS rn 
    FROM public.staging_excel se
),
empleados_unicos AS (
    -- Filtramos para quedarnos únicamente con la fila del estado y puesto actual
    SELECT * FROM consulta_empleados WHERE rn = 1 
)
SELECT 
    e.nombre_completo, 
    -- Homologación limpia basada en el género consolidado sin nulos
    CASE 
        WHEN e.genero_consolidado IS NOT NULL AND UPPER(e.genero_consolidado) LIKE 'MASC%' THEN 'M'
        WHEN e.genero_consolidado IS NOT NULL AND UPPER(e.genero_consolidado) LIKE 'FEM%' THEN 'F'
        WHEN e.genero_consolidado IN ('M', 'F') THEN e.genero_consolidado
        ELSE 'N' -- Valor por defecto seguro
    END AS gender, 
    te.id AS type_employee_id,
    dp.id AS department_position_id,
    CASE 
        WHEN (e.fecha = (SELECT MAX(fecha) FROM public.staging_excel)) THEN TRUE 
        ELSE FALSE 
    END AS status,
    e.fecha_contratacion_minima AS hire_date
FROM empleados_unicos e
INNER JOIN public.branch b 
    ON b.id = e.sucursal_id
INNER JOIN public.division d 
    ON d.name = e.division_name
INNER JOIN public.department dpt 
    ON dpt.name = e.department_name 
   AND dpt.branch_id = b.id 
   AND dpt.division_id = d.id
INNER JOIN public.position p 
    ON p.name = e.position_name
INNER JOIN public.department_position dp 
    ON dp.department_id = dpt.id 
   AND dp.position_id = p.id
INNER JOIN public.type_employee te 
    ON te.description = e.estatus_name
ON CONFLICT DO NOTHING;

-- public.employee_position_history
INSERT INTO public.employee_position_history(employee_id, department_position_id, start_date, end_date, salary)
WITH detectar_cambios AS (
    SELECT 
        CONCAT(se.nombres, ' ', se.apellidos) AS nombre_completo,
        e.id AS employee_id,
        dp.id AS department_position_id,
        CAST(se.fecha AS DATE) AS fecha_registro, -- <-- Forzamos la conversión a DATE aquí
        se.sueldo_nominal::numeric::money AS salary,
        LAG(dp.id) OVER(PARTITION BY se.nombres, se.apellidos ORDER BY CAST(se.fecha AS DATE) ASC) AS puesto_anterior
    FROM public.staging_excel se
    INNER JOIN public.branch b ON b.name = se.sucursal
    INNER JOIN public.division d ON d.name = se.direccion
    INNER JOIN public.department dpt ON dpt.name = se.departamento AND dpt.branch_id = b.id AND dpt.division_id = d.id
    INNER JOIN public.position p ON p.name = se.posicion
    INNER JOIN public.department_position dp ON dp.department_id = dpt.id AND dp.position_id = p.id
    LEFT JOIN public.employee e ON e.name = CONCAT(se.nombres, ' ', se.apellidos)
),
marcar_grupos AS (
    SELECT 
        *,
        COUNT(CASE WHEN puesto_anterior IS NULL OR department_position_id <> puesto_anterior THEN 1 END) 
        OVER(PARTITION BY employee_id ORDER BY fecha_registro ASC) AS grupo_puesto
    FROM detectar_cambios
),
historial_consolidado AS (
    SELECT 
        employee_id,
        department_position_id,
        MIN(fecha_registro) AS start_date, -- Al ser fecha_registro un DATE, start_date ahora es DATE
        MAX(fecha_registro) AS fin_registro, 
        MAX(salary) AS salary,
        grupo_puesto
    FROM marcar_grupos
    GROUP BY employee_id, department_position_id, grupo_puesto
)
SELECT 
    employee_id,
    department_position_id,
    start_date,
    CASE 
        WHEN LEAD(start_date) OVER(PARTITION BY employee_id ORDER BY start_date ASC) IS NOT NULL 
        -- Ahora la resta aritmética entre DATE e INTERVAL se ejecutará correctamente
        THEN (LEAD(start_date) OVER(PARTITION BY employee_id ORDER BY start_date ASC) - INTERVAL '1 day')::date
        ELSE NULL 
    END AS end_date,
    salary
FROM historial_consolidado
ON CONFLICT (employee_id, start_date) DO NOTHING;

-- public.payroll
INSERT INTO public.payroll (payroll_date, description)
SELECT DISTINCT fecha::date, CONCAT(
    'Pago nomina ', 
	CASE TO_CHAR(fecha::date, 'MM')
		WHEN '01' THEN 'Enero' WHEN '02' THEN 'Febrero' WHEN '03' THEN 'Marzo'
        WHEN '04' THEN 'Abril' WHEN '05' THEN 'Mayo' WHEN '06' THEN 'Junio'
        WHEN '07' THEN 'Julio' WHEN '08' THEN 'Agosto' WHEN '09' THEN 'Septiembre'
        WHEN '10' THEN 'Octubre' WHEN '11' THEN 'Noviembre' WHEN '12' THEN 'Diciembre'
    END,
    ' ', 
    TO_CHAR(fecha::date, 'YYYY')
) AS descripcion
FROM public.staging_excel
ON CONFLICT DO NOTHING;

-- public.payroll_detail
INSERT INTO public.payroll_detail (payroll_id, employee_id, employee_position_history_id, salary, deductions)
SELECT 
    pr.id AS payroll_id,
    e.id AS employee_id,
    h.id AS employee_position_history_id,
    se.sueldo_nominal::numeric::money AS salary,
    0.00::money AS deductions
FROM public.staging_excel se
INNER JOIN public.payroll pr ON pr.payroll_date = se.fecha
INNER JOIN public.employee e ON e.name = CONCAT(se.nombres, ' ', se.apellidos)
INNER JOIN public.employee_position_history h ON h.employee_id = e.id
    AND se.fecha >= h.start_date 
    AND (h.end_date IS NULL OR se.fecha <= h.end_date)
ON CONFLICT (payroll_id, employee_id) DO NOTHING;