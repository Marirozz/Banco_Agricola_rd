import glob
import os
import re
import pandas as pd
from dotenv import load_dotenv
from src.extract import NominaExtractor
from src.transform import NominaTransformer
from src.load import NominaLoader
from sqlalchemy import Date

load_dotenv()

def obtener_fecha_desde_nombre(nombre_archivo):
    nombre_upper = nombre_archivo.upper()
    anio = "2026" if "2026" in nombre_upper else "2025"
    
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
    DATABASE_URL = f"postgresql://postgres:{os.getenv('DATABASE_PASSWORD')}@{os.getenv('DATABASE_HOST')}:5432/banco_agricola_rd"
    loader = NominaLoader(DATABASE_URL)
    
    patron_busqueda = os.path.join("data", "raw", "nomina", "NOMINA-EMPLEADO-FIJO-*.xlsx")
    archivos_nomina = glob.glob(patron_busqueda)
    
    print(f"--> Se han detectado {len(archivos_nomina)} archivos listos para procesar.")
    if not archivos_nomina:
        return

    maestro_genero = {}
    maestro_fecha_contratacion = {}
    dfs_crudos = {}
    
    # UN SOLO BUCLE MAESTRO: Extrae y recopila diccionarios a la vez (Evita leer el Excel dos veces)
    print("\n[EXTRACT & LOOKUP] Procesando archivos raw y construyendo maestros históricos...")
    for ruta in archivos_nomina:
        nombre_archivo = os.path.basename(ruta)
        nombre_upper = nombre_archivo.upper()
        try:
            # Extraemos el archivo una sola vez
            df_mes = extractor.reparar_y_extraer(ruta)
            dfs_crudos[nombre_archivo] = df_mes
            print(f"  ✓ {nombre_archivo} extraído. Registros: {len(df_mes)}")
            
            # Alimentar maestro de género si corresponde
            if ("MARZO" in nombre_upper or "ABRIL" in nombre_upper) and "2026" in nombre_upper:
                if 'genero' in df_mes.columns:
                    for _, row in df_mes.iterrows():
                        nombres = str(row['nombres']).strip() if pd.notna(row['nombres']) else ''
                        apellidos = str(row['apellidos']).strip() if pd.notna(row['apellidos']) else ''
                        if nombres and apellidos and row['genero']:
                            maestro_genero[f"{nombres}|{apellidos}"] = row['genero']
            
            # Alimentar maestro de fecha_contratacion si corresponde
            if any(m in nombre_upper for m in ["JULIO", "AGOSTO", "SEPTIEMBRE"]):
                if 'fecha_contratacion' in df_mes.columns:
                    for _, row in df_mes.iterrows():
                        nombres = str(row['nombres']).strip() if pd.notna(row['nombres']) else ''
                        apellidos = str(row['apellidos']).strip() if pd.notna(row['apellidos']) else ''
                        if nombres and apellidos and pd.notna(row['fecha_contratacion']):
                            maestro_fecha_contratacion[f"{nombres}|{apellidos}"] = row['fecha_contratacion']
                            
        except Exception as e:
            print(f"  ✗ Error crítico procesando {nombre_archivo}: {e}")

    print(f"--> Maestros consolidados: Géneros ({len(maestro_genero)}), Fechas Contratación ({len(maestro_fecha_contratacion)})")

    # Fase 3: Transformación en Memoria usando los maestros
    dfs_transformados = []
    for nombre_archivo, df_mes in dfs_crudos.items():
        if len(df_mes) == 0:
            continue
        fecha_completa = obtener_fecha_desde_nombre(nombre_archivo)
        try:
            df_listo = NominaTransformer.transformar_mes(
                df_mes=df_mes, 
                fecha_completa=fecha_completa,
                maestro_genero=maestro_genero,
                maestro_fecha_contratacion=maestro_fecha_contratacion
            )
            dfs_transformados.append(df_listo)
        except Exception as e:
            print(f" Error transformando {nombre_archivo}: {e}")

    # Capa de Carga y Persistencia
    if dfs_transformados:
        df_staging_final = pd.concat(dfs_transformados, ignore_index=True)
        
        # =====================================================================
        # CAPA SILVER: GUARDAR EL DATASET INTEGRADO Y LIMPIO EN PARQUET
        
        print("\n[SILVER LAYER] Guardando histórico consolidado y limpio en data/silver/...")
        try:
            os.makedirs(os.path.join("data", "silver"), exist_ok=True)
            ruta_silver = os.path.join("data", "silver", "historico_nominas_limpio.parquet")
            df_staging_final.to_parquet(ruta_silver, index=False)
            print(f"  ✓ Archivo Silver persistido correctamente en: {ruta_silver}")
        except Exception as e:
            error_msg = f"Error guardando capa Silver en Parquet: {e}"
            print(f"  ✗ {error_msg}")
            # Guardamos el error en nuestro log
            os.makedirs(os.path.join("data", "logs"), exist_ok=True)
            with open(os.path.join("data", "logs", "pipeline_errors.txt"), "a", encoding="utf-8") as log_file:
                log_file.write(f"[{pd.Timestamp.now()}] CRITICAL_SILVER: {error_msg}\n")

        # =====================================================================
        # CAPA BRONZE & RELACIONAL: CARGA A POSTGRESQL
        
        print("\n[LOAD] Cargando registros unificados a public.staging_excel...")
        df_staging_final.to_sql(
            name='staging_excel', con=loader.engine, if_exists='replace', 
            index=False, method='multi', dtype={'fecha': Date}
        )
        
        print("[TRANSFORM & LOAD - SQL] Orquestando inserciones relacionales en base de datos...")
        loader.ejecutar_inserts_relacionales()
        
        # 🌟 Si llegamos aquí, la base de datos y la operación base están perfectas
        print("\n=== ¡PIPELINE DE OPERACIÓN BASE FINALIZADO CON ÉXITO! ===")
        
        # =====================================================================
        #  CAPA GOLD: GENERAR AGREGACIONES DESDE UN ARCHIVO SQL EXTERNO
        print("\n[GOLD LAYER] Generando agregados analíticos desde src/queries_gold.sql...")
        try:
            os.makedirs(os.path.join("data", "gold"), exist_ok=True)
            ruta_sql_gold = os.path.join("src", "sql", "queries_gold.sql")
            
            if os.path.exists(ruta_sql_gold):
                with open(ruta_sql_gold, 'r', encoding='utf-8') as f:
                    contenido_sql = f.read()
                
                bloques_queries = contenido_sql.split('-- NAME: ')
                for bloque in bloques_queries:
                    if not bloque.strip():
                        continue
                    
                    lineas = bloque.split('\n')
                    nombre_reporte = lineas[0].strip()
                    query_pure = '\n'.join(lineas[1:])
                    
                    if query_pure.strip():
                        print(f"  -> Ejecutando reporte Gold: {nombre_reporte}...")
                        df_reporte = pd.read_sql(query_pure, con=loader.engine)
                        
                        ruta_salida = os.path.join("data", "gold", f"{nombre_reporte}.parquet")
                        df_reporte.to_parquet(ruta_salida, index=False, engine='pyarrow')
                        print(f"    Persistido correctamente en: {ruta_salida}")
            else:
                print(f"  Advertencia: No se encontró el archivo de consultas en {ruta_sql_gold}")
                
        except Exception as e:
            #MANEJO DE ERRORES DE CAPA GOLD CON VOLCADO A ARCHIVO LOG
            os.makedirs(os.path.join("data", "logs"), exist_ok=True)
            ruta_log = os.path.join("data", "logs", "pipeline_errors.txt")
            
            error_completo = f"[{pd.Timestamp.now()}] ERROR_GOLD en reporte: {e}"
            
            with open(ruta_log, "a", encoding="utf-8") as log_file:
                log_file.write(error_completo + "\n")
                
            print(f"\n  Advertencia: La capa Gold falló, pero los datos operativos ya se guardaron.")
            print(f"    Detalle del error registrado en: {ruta_log}")
            print(f"    Error técnico: {e}")
        # =====================================================================
        
    else:
        print("\nError: No se generó ningún dataset transformado.")
if __name__ == "__main__":
    run_pipeline()