import pandas as pd
from datetime import datetime, timedelta

class NominaTransformer:
    # Eliminamos el método crear_maestro_sucursales porque ya no se necesita

    @staticmethod
    def _convertir_fecha_excel(valor):
        """Convierte números Excel o strings de fecha a formato DATE"""
        if pd.isna(valor) or valor is None or valor == '':
            return None
        
        # Primero intentar como número (fecha Excel)
        try:
            num = float(valor)
            if num < 0:
                return None
            
            # Conversión: Excel serial date a Python date
            excel_epoch = datetime(1900, 1, 1)
            # Ajustar por el bug de feb-1900 donde Excel cuenta el 29-feb-1900 que no existe
            if num > 59:
                num = num - 1
            fecha = excel_epoch + timedelta(days=int(num - 1))
            return fecha.date()
        except (ValueError, TypeError):
            # Si no es un número, intentar como string de fecha
            pass
        
        # Si es un string, intentar parsearlo como fecha
        if isinstance(valor, str):
            valor = valor.strip()
            if valor in ['null', 'NULL', 'nan', 'NaN', 'None', '']:
                return None
            # Intentar parsear en diferentes formatos
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y']:
                try:
                    return pd.to_datetime(valor, format=fmt).date()
                except:
                    pass
        
        # Si nada funcionó, devolver None
        return None

    @staticmethod
    def transformar_mes(df_mes, fecha_completa, maestro_genero=None, maestro_fecha_contratacion=None):
       
        #Transforma el mes 
        df = df_mes.copy()
        
        # Inicializar maestros si no vienen
        if maestro_genero is None:
            maestro_genero = {}
        if maestro_fecha_contratacion is None:
            maestro_fecha_contratacion = {}
        
        # 1. Limpieza de la Sucursal original del Excel
        if 'sucursal' in df.columns:
            df['sucursal'] = df['sucursal'].astype(str).str.strip()
            # Si viene completamente vacía o nula, le ponemos '0' por defecto o la dejamos limpia
            df['sucursal'] = df['sucursal'].replace(['nan', 'NaN', 'None', ''], '0')
        else:
            df['sucursal'] = '0'
        
        # 2. Preservación y limpieza del Género nativo del archivo + lookup maestro
        if 'genero' in df.columns:
            df['genero'] = df['genero'].astype(str).str.strip()
            df['genero'] = df['genero'].replace(['null', 'NULL', 'nan', 'NaN', 'None', ''], None)
        else:
            df['genero'] = None
        
        # Rellenar género desde maestro si está vacío
        if len(maestro_genero) > 0:
            df['_clave_genero'] = df['nombres'].astype(str).str.strip() + '|' + df['apellidos'].astype(str).str.strip()
            df['genero'] = df.apply(
                lambda row: maestro_genero.get(row['_clave_genero'], row['genero']) 
                if pd.isna(row['genero']) or row['genero'] == '' else row['genero'],
                axis=1
            )
            df = df.drop(columns=['_clave_genero'])
            
        # 3. Limpieza de Fecha de Contratación + lookup maestro
        if 'fecha_contratacion' in df.columns:
            df['fecha_contratacion'] = df['fecha_contratacion'].astype(str).str.strip()
            df['fecha_contratacion'] = df['fecha_contratacion'].replace(['null', 'NULL', 'nan', 'NaN', 'None', ''], None)
        else:
            df['fecha_contratacion'] = None
        
        # Convertir números Excel a fechas
        if 'fecha_contratacion' in df.columns:
            df['fecha_contratacion'] = df['fecha_contratacion'].apply(NominaTransformer._convertir_fecha_excel)
        
        # Rellenar fecha_contratacion desde maestro si está vacía
        if len(maestro_fecha_contratacion) > 0:
            df['_clave_fecha'] = df['nombres'].astype(str).str.strip() + '|' + df['apellidos'].astype(str).str.strip()
            
            def rellenar_fecha(row):
                if pd.isna(row['fecha_contratacion']) or row['fecha_contratacion'] is None:
                    fecha_str = maestro_fecha_contratacion.get(row['_clave_fecha'])
                    if fecha_str:
                        return NominaTransformer._convertir_fecha_excel(fecha_str)
                return row['fecha_contratacion']
            
            df['fecha_contratacion'] = df.apply(rellenar_fecha, axis=1)
            df = df.drop(columns=['_clave_fecha'])

        # 4. Estandarización numérica y temporal
        df['sueldo_nominal'] = pd.to_numeric(df['sueldo_nominal'], errors='coerce').fillna(0.0)
        df['cantidad'] = pd.to_numeric(df['cantidad'], errors='coerce').fillna(0).astype(int)
        df['fecha'] = fecha_completa
        
        columnas_finales = [
            'cantidad', 'sucursal', 'direccion', 'departamento', 
            'nombres', 'apellidos', 'posicion', 'sueldo_nominal', 
            'estatus', 'genero', 'fecha', 'fecha_contratacion'
        ]
        return df[columnas_finales]