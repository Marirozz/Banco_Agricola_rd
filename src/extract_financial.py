import os
import pandas as pd
import numpy as np  # <-- Añadido para manejar los nulos en la limpieza del año
from sqlalchemy import create_engine

# Configuración de la conexión (Asegúrese de colocar sus credenciales correctas)
DATABASE_URL = "postgresql://postgres:1234@localhost:5432/banco_agricola_rd"
engine = create_engine(DATABASE_URL)

def clean_common_data(df):
    """Función para limpiar filas de totales, espacios en blanco comunes y blindar el año"""
    df = df.dropna(how='all')
    
    # Limpieza estándar de totales
    for col in df.columns:
        df = df[~df[col].astype(str).str.contains('Total|TOTAL', case=False, na=False)]
        
    # --- ESCUDO PARA EL AÑO: Evita el error "2040.0" antes de enviar a staging ---
    if 'ano' in df.columns:
        # 1. Convertir a string, quitar espacios y homogeneizar nulos
        df['ano'] = df['ano'].astype(str).str.strip()
        df['ano'] = df['ano'].replace(['nan', 'None', '', 'nan.0'], np.nan)
        
        # 2. Remover el decimal ".0" que deja Excel (ej: "2040.0" -> "2040")
        df['ano'] = df['ano'].str.replace(r'\.0$', '', regex=True)
        
        # 3. Eliminar filas si el año quedó vacío o nulo
        df = df.dropna(subset=['ano'])
        df = df[df['ano'] != '']
        
        # 4. Convertirlo a entero puro
        df['ano'] = df['ano'].astype(int)
        
    return df

def clean_numeric_column(series):
    """Elimina comas, espacios y símbolos de moneda para convertir a texto limpio"""
    return series.astype(str).str.replace(r'[RDS\$,\s]', '', regex=True).str.strip()

def process_financial_files():
    # Ruta base apuntando a la carpeta 'raw'
    base_path = "data/raw/financial/"
    
    print(f"Buscando archivos en la ruta: {os.path.abspath(base_path)}")
    
    # 1. Procesar Desembolsos y Cobros
    file_desembolsos = os.path.join(base_path, "desembolsos-y-cobros-bagricola-2025-2026.xlsx")
    if os.path.exists(file_desembolsos):
        print("Procesando desembolsos y cobros...")
        df = pd.read_excel(file_desembolsos)
        
        df.columns = ['sucursal', 'desembolsos', 'cobros', 'mes', 'ano']
        df = clean_common_data(df) # <-- Ahora limpia también el año aquí
        
        df['desembolsos'] = clean_numeric_column(df['desembolsos'])
        df['cobros'] = clean_numeric_column(df['cobros'])
        
        df.to_sql('staging_desembolsos', con=engine, if_exists='append', index=False)
        print("✓ Desembolsos cargados a staging.")
    else:
        print(f"X No se encontró el archivo de desembolsos en: {file_desembolsos}")

    # 2. Procesar Cartera de Préstamos
    file_cartera = os.path.join(base_path, "cartera-de-prestamos-bagricola-2017-2026.xlsx")
    if os.path.exists(file_cartera):
        print("Procesando cartera de préstamos...")
        df = pd.read_excel(file_cartera)
        
        df.columns = ['sucursal', 'prestamos_activos', 'balance_pendiente', 'mes', 'ano']
        df = clean_common_data(df) # <-- Ahora limpia también el año aquí
        
        df['prestamos_activos'] = clean_numeric_column(df['prestamos_activos'])
        df['balance_pendiente'] = clean_numeric_column(df['balance_pendiente'])
        df['balance_vencido'] = '0.00' 

        if 'prestamos_activos' in df.columns:
             # 1. Convertimos a numérico de manera segura (maneja los decimales ".0")
            df['prestamos_activos'] = pd.to_numeric(df['prestamos_activos'], errors='coerce')
            # 2. Llenamos posibles vacíos con 0 y lo transformamos a tipo entero limpio
            df['prestamos_activos'] = df['prestamos_activos'].fillna(0).astype(int)
             # --------------------------------------------

        # Limpieza de totales
        df = df[~df['prestamos_activos'].astype(str).str.contains('Total|TOTAL', case=False, na=False)]
        
        df.to_sql('staging_cartera', con=engine, if_exists='append', index=False)
        print("✓ Cartera cargada a staging.")
    else:
        print(f"X No se encontró el archivo de cartera en: {file_cartera}")

    # 3. Procesar Áreas Financiadas
    file_areas = os.path.join(base_path, "areas-financiadas-bagricola-2017-2026.xlsx")
    if os.path.exists(file_areas):
        print("Procesando áreas financiadas...")
        df = pd.read_excel(file_areas)
        
        df.columns = ['sucursal', 'tareas_financiadas', 'beneficiarios', 'valores', 'mes', 'ano']
        df = clean_common_data(df) # <-- Ahora limpia también el año aquí
        
        df['tareas_financiadas'] = clean_numeric_column(df['tareas_financiadas'])
        df['beneficiarios'] = clean_numeric_column(df['beneficiarios'])
        df['sector'] = 'General'
        
        df_final = df[['ano', 'mes', 'sucursal', 'sector', 'tareas_financiadas', 'beneficiarios']]
        df_final.to_sql('staging_areas', con=engine, if_exists='append', index=False)
        print("✓ Áreas financiadas cargadas a staging.")
    else:
        print(f"X No se encontró el archivo de áreas en: {file_areas}")

    # 4. Procesar Montos Otorgados por Destino
    file_destinos = os.path.join(base_path, "montos-otorgados-por-destino-bagricola-2017-2026.xlsx")
    if os.path.exists(file_destinos):
        print("Procesando montos otorgados por destino...")
        df = pd.read_excel(file_destinos)
        
        df.columns = ['destino', 'cantidad', 'monto_disbursado', 'tareas', 'beneficiados', 'mes', 'ano']
        df = clean_common_data(df) # <-- Ahora limpia también el año aquí
        
        df['monto_disbursado'] = clean_numeric_column(df['monto_disbursado'])
        df['sucursal'] = 'Sede Central'
        
        df_final = df[['ano', 'mes', 'sucursal', 'destino', 'monto_disbursado']]
        df_final.to_sql('staging_destinos', con=engine, if_exists='append', index=False)
        print("✓ Destinos cargados a staging.")
    else:
        print(f"X No se encontró el archivo de destinos en: {file_destinos}")

if __name__ == "__main__":
    process_financial_files()