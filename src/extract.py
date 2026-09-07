import pandas as pd
import re
import os

class NominaExtractor:
    def __init__(self):
        # Mapeamos SOLAMENTE los sinónimos que cambian de palabra (ej: cargo -> posicion)
        # Las claves van en minúsculas y sin tildes.
        self.mapeo_sinonimos = {
           'Cant.': 'cantidad',
            'cargo': 'posicion',
            'cargar': 'posicion',
            'ingreso bruto': 'sueldo_nominal',
            'sueldo nominal': 'sueldo_nominal',
            'sexo': 'genero',
            'categoria servidor': 'estatus',
            'estado': 'estatus',
            'fecha contratación': 'fecha_contratacion',
            'fecha contratacion': 'fecha_contratacion'
        }

    def _homologar_columnas(self, columnas_archivo):
        """
        Pasa a minúsculas, quita tildes y compara con el diccionario.
        Si la palabra limpia ya es igual al campo de la BD (como nombres, apellidos, departamento, genero, direccion),
        pasa directo sin necesidad de escribirlo en el diccionario.
        """
        columnas_procesadas = []
        for col in columnas_archivo:
            # 1. Limpieza básica estándar sin alterar caracteres clave
            col_limpia = str(col).strip().lower()
            
            # 2. Remover tildes estrictamente para comparar
            col_base = (col_limpia
                        .replace('á', 'a')
                        .replace('é', 'e')
                        .replace('í', 'i')
                        .replace('ó', 'o')
                        .replace('ú', 'u')
                        .replace('.', '')) # Quitamos el punto aquí adentro para no dañar el texto original antes
            
            # 3. Buscar en sinónimos o pasar el nombre limpio
            if col_base in self.mapeo_sinonimos:
                columnas_procesadas.append(self.mapeo_sinonimos[col_base])
            else:
                # Si es 'genero', 'direccion', 'departamento', 'nombres', 'apellidos', ya cae aquí directo en snake_case
                columnas_procesadas.append(col_base)
                
        return columnas_procesadas

    def reparar_y_extraer(self, file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"No se encontró el archivo en: {file_path}")
            
        df_temp = pd.read_excel(file_path, header=None, dtype=str)
        
        idx_inicio = 0
        for idx, fila in df_temp.iterrows():
            fila_valores = [str(val).strip().lower() for val in fila.values if pd.notna(val)]
            fila_unida = "".join(fila_valores).replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u')
            
            if any(k in fila_unida for k in ["cant", "sucursal", "cargo", "ingreso bruto", "sueldo nominal", "nombre", "apellido"]):
                idx_inicio = idx
                break
                
        df = pd.read_excel(file_path, skiprows=idx_inicio, dtype=str)
        df.columns = [str(col).strip() for col in df.columns]
        
        # Transformación directa de columnas a minúsculas y sin tildes (snake_case)
        df.columns = self._homologar_columnas(df.columns)
        
        # Forzar a que las columnas del DataFrame de Marzo-2026 que vienen en singular se llamen igual
        if 'nombre' in df.columns and 'nombres' not in df.columns:
            df = df.rename(columns={'nombre': 'nombres'})
        if 'apellido' in df.columns and 'apellidos' not in df.columns:
            df = df.rename(columns={'apellido': 'apellidos'})
            
        columnas_finales = [
            'cantidad', 'sucursal', 'direccion', 'departamento', 
            'nombres', 'apellidos', 'posicion', 'sueldo_nominal', 
            'estatus', 'genero', 'fecha_contratacion'
        ]
        
        for col in columnas_finales:
            if col not in df.columns:
                df[col] = None
        
        if 'cant' in df.columns and 'cantidad' not in df.columns:
            df = df.rename(columns={'cant': 'cantidad'})
            
        if 'cantidad' in df.columns:
            df['cantidad'] = df['cantidad'].fillna('1')
                
        df = df[columnas_finales]
        
        # Limpieza de filas basura
        if 'sueldo_nominal' in df.columns and len(df) > 0:
            try:
                df['sueldo_nominal'] = df['sueldo_nominal'].fillna('').astype(str).str.replace('$', '', regex=False)
                df['sueldo_nominal'] = df['sueldo_nominal'].str.replace(',', '', regex=False).str.strip()
                
                patron_numerico = r'^\d+(\.\d+)?$'
                df = df[
                    df['sueldo_nominal'].str.match(patron_numerico, na=True) | 
                    (df['sueldo_nominal'] == '') | df['sueldo_nominal'].isna()
                ]
            except Exception:
                pass
        
        if 'nombres' in df.columns and 'apellidos' in df.columns:
            df = df[df['nombres'].notna() & (df['nombres'] != '')]
            df = df[df['apellidos'].notna() & (df['apellidos'] != '')]
                
        return df