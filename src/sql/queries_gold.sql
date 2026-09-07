-- NAME: gasto_por_sucursales
SELECT 
    p.payroll_date::text AS fecha,
    b.name AS sucursal,
    SUM(pd.salary::numeric) AS total_gasto_salarial,
    COUNT(DISTINCT pd.employee_id) AS total_empleados
FROM public.payroll_detail pd
INNER JOIN public.payroll p ON p.id = pd.payroll_id
INNER JOIN public.employee_position_history h ON h.id = pd.employee_position_history_id
INNER JOIN public.department_position dp ON dp.id = h.department_position_id
INNER JOIN public.department dpt ON dpt.id = dp.department_id
INNER JOIN public.branch b ON b.id = dpt.branch_id
GROUP BY p.payroll_date, b.name
ORDER BY p.payroll_date ASC, total_gasto_salarial DESC;

-- NAME: analisis_demografico_salarios
SELECT 
    p.payroll_date::text AS fecha,
    pos.name AS posicion,
    e.gender AS genero,
    COUNT(e.id) AS cantidad_empleados,
    ROUND(AVG(pd.salary::numeric), 2) AS salario_promedio
FROM public.payroll_detail pd
INNER JOIN public.payroll p ON p.id = pd.payroll_id
INNER JOIN public.employee e ON e.id = pd.employee_id
INNER JOIN public.employee_position_history h ON h.id = pd.employee_position_history_id
INNER JOIN public.department_position dp ON dp.id = h.department_position_id
INNER JOIN public.position pos ON pos.id = dp.position_id
GROUP BY p.payroll_date, pos.name, e.gender
ORDER BY p.payroll_date ASC, pos.name ASC;