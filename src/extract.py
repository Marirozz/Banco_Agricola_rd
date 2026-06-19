import pandas as pd
import re
import os

class NominaExtractor:
    def __init__(self):
        # ÚNICO DICCIONARIO: Mapea cualquier variación directamente a snake_case de base de datos
        self.mapeo_sinonimos = {
            'cant': 'cantidad',
            'cantidad': 'cantidad',
            'sucursal': 'sucursal',
            'direccion': 'direccion',
            'departamento': 'departamento',
            'nombres': 'nombres',
            'nombre': 'nombres',
            'apellidos': 'apellidos',
            'apellido': 'apellidos',
            'cargo': 'posicion',
            'posicion': 'posicion',
            'cargar': 'posicion',
            'ingreso bruto': 'sueldo_nominal',
            'sueldo nominal': 'sueldo_nominal',
            'estado': 'estatus',
            'estatus': 'estatus',
            'categoria servidor': 'estatus',
            'genero': 'genero',
            'sexo': 'genero',
            'fecha contratacion': 'fecha_contratacion',
            'fecha de contratacion': 'fecha_contratacion'
        }

    def _homologar_columnas(self, columnas_archivo):
        """Limpia tildes, puntos y espacios, y traduce directo al formato final de la base de datos."""
        columnas_procesadas = []
        for col in columnas_archivo:
            col_limpia = str(col).strip().lower().replace('.', '')
            col_comparar = (col_limpia
                            .replace('á', 'a')
                            .replace('é', 'e')
                            .replace('í', 'i')
                            .replace('ó', 'o')
                            .replace('ú', 'u'))
            
            if col_comparar in self.mapeo_sinonimos:
                columnas_procesadas.append(self.mapeo_sinonimos[col_comparar])
            else:
                columnas_procesadas.append(col_comparar)  # Si es desconocida, pasa limpia en minúsculas
                
        return columnas_processed if 'columnas_processed' in locals() else columnas_procesadas

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
        
        # Al salir de aquí, las columnas ya se llaman 'genero', 'sueldo_nominal', etc.
        df.columns = self._homologar_columnas(df.columns)
        
        columnas_finales = [
            'cantidad', 'sucursal', 'direccion', 'departamento', 
            'nombres', 'apellidos', 'posicion', 'sueldo_nominal', 
            'estatus', 'genero', 'fecha_contratacion'
        ]
        
        # Inyectar vacías si no existen nativamente en el Excel
        for col in columnas_finales:
            if col not in df.columns:
                df[col] = None
        
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
                
                df = df[~df['sueldo_nominal'].str.lower().isin(['sueldo nominal', 'ingreso bruto', 'ingreso neto'])]
            except Exception:
                pass
        
        if 'nombres' in df.columns and 'apellidos' in df.columns:
            df = df[df['nombres'].notna() & (df['nombres'] != '')]
            df = df[df['apellidos'].notna() & (df['apellidos'] != '')]
                
        return df