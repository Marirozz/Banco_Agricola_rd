import glob
import os
import re
import pandas as pd
from src.extract import NominaExtractor
from src.transform import NominaTransformer
from src.load import NominaLoader
from sqlalchemy import Date

def obtener_fecha_desde_nombre(nombre_archivo):
    
    #Detecta dinámicamente el año (2025 o 2026) y el mes desde el nombre del archivo.
   
    nombre_upper = nombre_archivo.upper()
    
    # Detectar año de manera inteligente
    anio = "2025"
    if "2026" in nombre_upper:
        anio = "2026"
        
    meses_mapeo = {
        'ENERO': '-01-31', 'FEBRERO': '-02-28', 'MARZO': '-03-31',
        'ABRIL': '-04-30', 'MAYO': '-05-31', 'JUNIO': '-06-30',
        'JULIO': '-07-31', 'AGOSTO': '-08-31', 'SEPTIEMBRE': '-09-30',
        'OCTUBRE': '-10-31', 'NOVIEMBRE': '-11-30', 'DICIEMBRE': '-12-31'
    }
    
    for mes, sufijo in meses_mapeo.items():
        if mes in nombre_upper:
            return f"{anio}{sufijo}"
            
    return f"{anio}-12-31"

def run_pipeline():
    print("=== INICIANDO PIPELINE DE INGESTA MASIVA EN CASCADA (ELT) ===")
    
    extractor = NominaExtractor()
    DATABASE_URL = "postgresql://postgres:1234@localhost:5432/banco_agricola_rd"
    loader = NominaLoader(DATABASE_URL)
    
    patron_busqueda = os.path.join("data", "raw", "nomina", "NOMINA-EMPLEADO-FIJO-*.xlsx")
    archivos_nomina = glob.glob(patron_busqueda)
    
    print(f"--> Se han detectado {len(archivos_nomina)} archivos listos para procesar.")
    
    if not archivos_nomina:
        print("Alerta: No se encontraron archivos.")
        return

    # Fase 1: Extracción Cruda de todos los archivos
    dfs_crudos = {}
    for ruta in archivos_nomina:
        nombre_archivo = os.path.basename(ruta)
        try:
            df_mes = extractor.reparar_y_extraer(ruta)
            dfs_crudos[nombre_archivo] = df_mes
            print(f"[EXTRACT] {nombre_archivo} -> Éxito. Registros crudos: {len(df_mes)}")
        except Exception as e:
            print(f" Error crítico extrayendo {nombre_archivo}: {e}")



    # Fase 3: Transformación en Memoria (Pandas) por cada mes
    dfs_transformados = []
    for nombre_archivo, df_mes in dfs_crudos.items():
        if len(df_mes) == 0:
            continue
            
        fecha_completa = obtener_fecha_desde_nombre(nombre_archivo)
        
        try:
            df_listo = NominaTransformer.transformar_mes(
                df_mes=df_mes, 
                fecha_completa=fecha_completa
            )
            dfs_transformados.append(df_listo)
            print(f"[TRANSFORM] {nombre_archivo} -> Homologado con éxito.")
        except Exception as e:
            print(f" Error transformando {nombre_archivo}: {e}")

    # Fase 4: Carga Unificada a Staging y Ejecución SQL
    if dfs_transformados:
        print("\n[LOAD] Unificando todos los meses en memoria para la capa Bronze...")
        df_staging_final = pd.concat(dfs_transformados, ignore_index=True)
        
        print("--> Volcando bloque unificado en public.staging_excel...")
        df_staging_final.to_sql(
            name='staging_excel', 
            con=loader.engine, 
            if_exists='replace', 
            index=False,
            method='multi',
            dtype={'fecha': Date}
        )
        print("¡Tabla public.staging_excel poblada con éxito!")
        
        print("\n[TRANSFORM & LOAD - SQL] Ejecutando orquestación relacional en PostgreSQL...")
        loader.ejecutar_inserts_relacionales()
        print("\n=== ¡PIPELINE FINALIZADO CON ÉXITO! ===")
    else:
        print("\nError: No se pudo transformar ningún dataset.")

if __name__ == "__main__":
    run_pipeline()