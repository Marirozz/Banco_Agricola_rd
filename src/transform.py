import pandas as pd

class NominaTransformer:
    # Eliminamos el método crear_maestro_sucursales porque ya no se necesita

    @staticmethod
    def transformar_mes(df_mes, fecha_completa):
       
        #Transforma el mes 
        df = df_mes.copy()
        
        # 1. Limpieza de la Sucursal original del Excel
        if 'sucursal' in df.columns:
            df['sucursal'] = df['sucursal'].astype(str).str.strip()
            # Si viene completamente vacía o nula, le ponemos '0' por defecto o la dejamos limpia
            df['sucursal'] = df['sucursal'].replace(['nan', 'NaN', 'None', ''], '0')
        else:
            df['sucursal'] = '0'
        
        # 2. Preservación y limpieza del Género nativo del archivo
        if 'genero' in df.columns:
            df['genero'] = df['genero'].astype(str).str.strip()
            df['genero'] = df['genero'].replace(['null', 'NULL', 'nan', 'NaN', 'None', ''], None)
        else:
            df['genero'] = None
            
        # 3. Limpieza de Fecha de Contratación
        if 'fecha_contratacion' in df.columns:
            df['fecha_contratacion'] = df['fecha_contratacion'].astype(str).str.strip()
            df['fecha_contratacion'] = df['fecha_contratacion'].replace(['null', 'NULL', 'nan', 'NaN', 'None', ''], None)
        else:
            df['fecha_contratacion'] = None

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