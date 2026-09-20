"""Configuración de los datasets financieros publicados en datos.gob.do.

Cada entrada corresponde a un dataset del portal CKAN de BAGRICOLA que alimenta
una tabla staging_* usada por src/sql/transform_financial.sql. `target_basename`
debe coincidir exactamente (sin extensión) con el nombre que espera
src/extract_financial.py, y `expected_columns` con el número de columnas que
ese script asume (asigna los nombres de columna por posición, sin leer el
encabezado real del archivo).

`formats` define el orden de preferencia de descarga: XLSX primero; si el
recurso no existe o el archivo publicado no se puede leer (p. ej. algunos
recursos vienen en OOXML "Strict", que openpyxl no soporta), se cae a CSV.
ODS nunca se usa, por decisión explícita del proyecto.
"""

ALLOWED_EXTENSIONS = ("xlsx", "csv")

DATASETS = [
    {
        "key": "desembolsos",
        "package_id": "3bc9bd7a-59e3-4535-8d4e-3494d85672d5",
        "formats": ["XLSX", "CSV"],
        "target_basename": "desembolsos-y-cobros-bagricola-2025-2026",
        "expected_columns": 5,  # sucursal, desembolsos, cobros, mes, ano
    },
    {
        "key": "cartera",
        "package_id": "79edae9a-4b58-4746-b026-01a060f4a170",
        "formats": ["XLSX", "CSV"],
        "target_basename": "cartera-de-prestamos-bagricola-2017-2026",
        "expected_columns": 5,  # sucursal, prestamos_activos, balance_pendiente, mes, ano
    },
    {
        "key": "areas",
        "package_id": "102b343f-a4c4-4aba-b253-77bff9ee4000",
        "formats": ["XLSX", "CSV"],
        "target_basename": "areas-financiadas-bagricola-2017-2026",
        "expected_columns": 6,  # sucursal, tareas_financiadas, beneficiarios, valores, mes, ano
    },
    {
        "key": "destinos",
        "package_id": "6064d590-5ebd-498c-9c20-9bedae54280c",
        "formats": ["XLSX", "CSV"],
        "target_basename": "montos-otorgados-por-destino-bagricola-2017-2026",
        "expected_columns": 7,  # destino, cantidad, monto_disbursado, tareas, beneficiados, mes, ano
    },
]

RAW_DIR = "data/raw/financial"
HISTORY_DIR = "data/raw/financial/history"
MANIFEST_PATH = "data/raw/financial/manifest.json"
