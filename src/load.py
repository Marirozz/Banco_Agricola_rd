import os
from sqlalchemy import create_engine, text

class NominaLoader:
    def __init__(self, connection_string):
        # Inicializa el motor de base de datos
        self.engine = create_engine(connection_string)

    def ejecutar_inserts_relacionales(self):
        #Ejecuta de manera secuencial los scripts SQL para poblar el modelo 3NF desde Staging
        
        # Leemos el script SQL externo
        ruta_sql = "src/sql/orquestacion_modelo.sql"
        
        if not os.path.exists(ruta_sql):
            raise FileNotFoundError(f"No se encontró el script SQL en la ruta: {ruta_sql}")
            
        with open(ruta_sql, "r", encoding="utf-8") as f:
            script_sql = f.read()
            
        # Ejecutamos todo el bloque relacional dentro de una sola transacción segura
        with self.engine.begin() as conn:
            # Dividimos las sentencias por punto y coma y ejecutamos en orden
            statements = script_sql.split(";")
            for statement in statements:
                stmt_clean = statement.strip()
                if stmt_clean: # Evitamos ejecutar bloques vacíos
                    conn.execute(text(stmt_clean))
                    
        print("--> ¡Éxito! Todas las tablas relacionales se actualizaron.")