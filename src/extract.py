import pandas as pd
import re
import os

class NominaExtractor:
    def __init__(self):
        # Diccionario de homologación
        # Las claves son las columnas originales y los valores son las columnas homologadas
        self.mapeo_sinonimos = {
            'cargo': 'Posición',
            'posicion': 'Posición',
            'ingreso bruto': 'Sueldo Nominal',
            'sueldo nominal': 'Sueldo Nominal',
            'estado': 'Estatus',
            'estatus': 'Estatus',
            'genero': 'Género',
            'sexo': 'Género',
            'cant': 'Cant.',
            'cantidad': 'Cant.',
            'sucursal': 'Sucursal',
            'direccion': 'Dirección',
            'departamento': 'Departamento',
            'nombres': 'Nombres',
            'apellidos': 'Apellidos',
            'fecha contratacion': 'Fecha Contratacion',
            'fecha de contratacion': 'Fecha Contratacion'
        }

    def _homologar_columnas(self, columnas_archivo):
        #Traduce las variaciones de nombres de columnas al estándar objetivo sin importar tildes, mayúsculas o puntos. Si no encuentra un mapeo, devuelve el nombre limpio en formato Título.
        columnas_procesadas = []
        for col in columnas_archivo:
            # 1. Pasamos a minúsculas, quitamos espacios extremos y eliminamos el punto final si existe (ej: "Cant." -> "cant")
            col_limpia = str(col).strip().lower().replace('.', '')
            
            # 2. Reemplazo explícito de vocales con tilde para normalizar por completo
            col_comparar = (col_limpia
                            .replace('á', 'a')
                            .replace('é', 'e')
                            .replace('í', 'i')
                            .replace('ó', 'o')
                            .replace('ú', 'u'))
            
            # 3. Validación directa contra el diccionario limpio
            if col_comparar in self.mapeo_sinonimos:
                columnas_procesadas.append(self.mapeo_sinonimos[col_comparar])
            else:
                # Si aparece una columna inesperada, la guardamos en formato Título de forma segura
                columnas_procesadas.append(col_limpia.title())
                
        return columnas_procesadas

    def reparar_y_extraer(self, file_path):
        """
        Lee un archivo Excel (.xlsx), localiza la cabecera principal eliminando el ruido institucional,
        y extrae el bloque de datos homologando las columnas a snake_case para PostgreSQL.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"No se encontró el archivo en: {file_path}")
            
        # 1. Buscar la fila exacta de la cabecera principal ignorando tildes y mayúsculas
        df_temp = pd.read_excel(file_path, header=None, dtype=str)
        
        idx_inicio = 0
        for idx, fila in df_temp.iterrows():
            fila_valores = [str(val).strip().lower() for val in fila.values if pd.notna(val)]
            fila_unida = "".join(fila_valores)
            fila_unida = (fila_unida
                          .replace('á', 'a')
                          .replace('é', 'e')
                          .replace('í', 'i')
                          .replace('ó', 'o')
                          .replace('ú', 'u'))
            
            # Evaluamos palabras clave de control en la estructura de la nómina
            if any(k in fila_unida for k in ["cant.", "sucursal", "cargo", "ingreso bruto", "sueldo nominal"]):
                idx_inicio = idx
                break
                
        # 2. Cargar el DataFrame saltando las filas basura de arriba
        df = pd.read_excel(file_path, skiprows=idx_inicio, dtype=str)
        
        # Limpiar espacios en blanco de los nombres de columnas que trae el Excel
        df.columns = [str(col).strip() for col in df.columns]
        
        # Homologar las columnas (Pasan de variaciones humanas a nuestro estándar con tilde bien puesto)
        df.columns = self._homologar_columnas(df.columns)
        
        
        # TRADUCCIÓN EXACTA A SNAKE_CASE PARA POSTGRESQL
        mapeo_columnas_sql = {
            'Cant.': 'cantidad',
            'Sucursal': 'sucursal',
            'Dirección': 'direccion',
            'Departamento': 'departamento',
            'Nombres': 'nombres',
            'Apellidos': 'apellidos',
            'Posición': 'posicion',
            'Sueldo Nominal': 'sueldo_nominal',
            'Estatus': 'estatus',
            'Género': 'genero',
            'Fecha Contratacion': 'fecha_contratacion'
        }
        
        df = df.rename(columns=mapeo_columnas_sql)
        
        # Si un mes viejo no tiene columnas nuevas (como genero o fecha_contratacion), las inyectamos vacías
        columnas_finales = list(mapeo_columnas_sql.values())
        for col in columnas_finales:
            if col not in df.columns:
                df[col] = None
                
        df = df[columnas_finales]
        
        
        # DEPURACIÓN DE FILAS BASURA (LOGOS INTERMEDIOS, TÍTULOS REPETIDOS)
        if 'sueldo_nominal' in df.columns:
            df['sueldo_nominal'] = df['sueldo_nominal'].astype(str).str.replace('$', '', regex=False)
            df['sueldo_nominal'] = df['sueldo_nominal'].str.replace(',', '', regex=False).str.strip()
            
        # Filtro numérico maestro para limpiar textos intercalados
        patron_numerico = r'^\d+(\.\d+)?$'
        df = df[
            df['sueldo_nominal'].str.match(patron_numerico, na=True) | 
            (df['sueldo_nominal'] == '') | 
            df['sueldo_nominal'].isna()
        ]
        
        df = df[df['sueldo_nominal'].str.lower() != 'sueldo nominal']
        df = df[df['sueldo_nominal'].str.lower() != 'ingreso bruto']
        df = df[df['nombres'].notna() & (df['nombres'] != '')]
        
        return df