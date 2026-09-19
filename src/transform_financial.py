import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import pandas as pd
import numpy as np

load_dotenv()

# Configuración de la conexión
DATABASE_URL = f"postgresql://postgres:{os.getenv('DATABASE_PASSWORD')}@{os.getenv('DATABASE_HOST')}:5432/banco_agricola_rd"
engine = create_engine(DATABASE_URL)


def limpiar_columna_anio(df):
    if 'ano' in df.columns:
        # 1. Convertir todo a string, limpiar espacios y rellenar nulos
        df['ano'] = df['ano'].astype(str).str.strip()
        
        # 2. Reemplazar valores vacíos, nulos o filas de "Total" por NaN
        df['ano'] = df['ano'].replace(['nan', 'None', '', 'Total'], np.nan)
        
        # 3. Remover el decimal ".0" si existe al final del string
        df['ano'] = df['ano'].str.replace(r'\.0$', '', regex=True)
        
        # 4. Eliminar las filas que se quedaron sin un año válido antes de subir a staging
        df = df.dropna(subset=['ano'])
        
        # 5. Forzar el tipo a entero (así sube como INT puro a Postgres)
        df['ano'] = df['ano'].astype(int)
    return df

def run_financial_transformations():
    print("Iniciando la fase de transformación unificada de datos financieros...")
    
    sql_file_path = "src/sql/transform_financial.sql"
    
    if not os.path.exists(sql_file_path):
        print(f"X ERROR: No se encontró el script SQL en: {sql_file_path}")
        return
        
    try:
        # Leemos todo el contenido del script unificado
        with open(sql_file_path, 'r', encoding='utf-8') as file:
            full_sql_script = file.read()
            
        # Ejecutamos de forma atómica todo el archivo SQL
        with engine.begin() as connection:
            print("Ejecutando consultas de transformación en PostgreSQL...")
            connection.execute(text(full_sql_script))
            
        print("\n¡Fase de transformación completada con éxito en el Modelo en Estrella desde un solo archivo SQL!")
        
    except Exception as e:
        print(f"\nX ERROR DURANTE LA TRANSFORMACIÓN: {str(e)}")
        print("La transacción fue cancelada automáticamente en la base de datos (Rollback).")

if __name__ == "__main__":
    run_financial_transformations()