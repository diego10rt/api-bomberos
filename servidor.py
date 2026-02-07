from flask import Flask, jsonify
from flask_cors import CORS
import requests
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
CORS(app)

# TUS 22 CUARTELES
URLS_CUARTELES = [
    {"nombre": "1 CBS", "url": "https://icbs.cl/c/v/124"},
    {"nombre": "2 CBS", "url": "https://icbs.cl/c/v/247"},
    {"nombre": "3 CBS", "url": "https://icbs.cl/c/v/370"},
    {"nombre": "4 CBS", "url": "https://icbs.cl/c/v/493"},
    {"nombre": "5 CBS", "url": "https://icbs.cl/c/v/616"},
    {"nombre": "6 CBS", "url": "https://icbs.cl/c/v/739"},
    {"nombre": "7 CBS", "url": "https://icbs.cl/c/v/862"},
    {"nombre": "8 CBS", "url": "https://icbs.cl/c/v/985"},
    {"nombre": "9 CBS", "url": "https://icbs.cl/c/v/1108"},
    {"nombre": "10 CBS", "url": "https://icbs.cl/c/v/1231"},
    {"nombre": "11 CBS", "url": "https://icbs.cl/c/v/1354"},
    {"nombre": "12 CBS", "url": "https://icbs.cl/c/v/1477"},
    {"nombre": "13 CBS", "url": "https://icbs.cl/c/v/1600"},
    {"nombre": "14 CBS", "url": "https://icbs.cl/c/v/1723"},
    {"nombre": "15 CBS", "url": "https://icbs.cl/c/v/1846"},
    {"nombre": "16 CBS", "url": "https://icbs.cl/c/v/1969"},
    {"nombre": "17 CBS", "url": "https://icbs.cl/c/v/2092"},
    {"nombre": "18 CBS", "url": "https://icbs.cl/c/v/2215"},
    {"nombre": "19 CBS", "url": "https://icbs.cl/c/v/2338"},
    {"nombre": "20 CBS", "url": "https://icbs.cl/c/v/2461"},
    {"nombre": "21 CBS", "url": "https://icbs.cl/c/v/2584"},
    {"nombre": "22 CBS", "url": "https://icbs.cl/c/v/2707"}
]

DATOS_EN_MEMORIA = []
ULTIMA_ACTUALIZACION = 0
LOCK_ACTUALIZACION = False

def obtener_token_y_datos(cuartel):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        response = session.get(cuartel['url'], timeout=10)
        
        # 1. Buscar la URL secreta
        match = re.search(r'var url="(https://icbs\.cl/cuartel/datos\.php\?id_proce=.*?&time=.*?&hash=.*?)"', response.text)
        
        if match:
            url_json = match.group(1)
            try:
                # 2. Intentar leer el JSON
                resp_json = session.get(url_json, timeout=10)
                datos_raw = resp_json.json()
            except:
                # ERROR CRÍTICO: El JSON vino roto (ej: la compañía 6 y 18)
                return {
                    "nombre_cuartel": cuartel['nombre'], 
                    "carros": [{"nombre": "SISTEMA", "estado": "OFFLINE"}]
                }
            
            carros_limpios = []
            
            if 'carros' in datos_raw and datos_raw['carros']:
                fuente = datos_raw['carros']
                lista = fuente.values() if isinstance(fuente, dict) else fuente
                
                for c in lista:
                    if isinstance(c, dict):
                        nombre = c.get('nombre', '??')
                        estado_raw = str(c.get('estado_nombre', '')).upper()
                        
                        # Lógica de estados (La que ya funciona bien)
                        estado_final = "EN SERVICIO"
                        if "LLAMADO" in estado_raw:
                             if "DISPONIBLE" in estado_raw:
                                 estado_final = "DISPONIBLE EN LLAMADO"
                             else:
                                 estado_final = "EN LLAMADO"
                        elif "FUERA" in estado_raw:
                             continue # Ocultamos los fuera de servicio
                        
                        carros_limpios.append({
                            "nombre": nombre,
                            "estado": estado_final
                        })

            return {"nombre_cuartel": cuartel['nombre'], "carros": carros_limpios}
        else:
            # ERROR: No encontramos la URL secreta
            return {
                "nombre_cuartel": cuartel['nombre'], 
                "carros": [{"nombre": "SISTEMA", "estado": "OFFLINE"}]
            }
            
    except Exception as e:
        print(f"Error conexión {cuartel['nombre']}: {e}")
        # ERROR: Falla de internet o tiempo de espera
        return {
            "nombre_cuartel": cuartel['nombre'], 
            "carros": [{"nombre": "SISTEMA", "estado": "SIN CONEXIÓN"}]
        }

def tarea_actualizar_todo():
    global DATOS_EN_MEMORIA, ULTIMA_ACTUALIZACION, LOCK_ACTUALIZACION
    if LOCK_ACTUALIZACION: return
    LOCK_ACTUALIZACION = True
    print("--- ⚡ ESCANEANDO... ---")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        res = list(executor.map(obtener_token_y_datos, URLS_CUARTELES))
    
    # Ordenar
    res.sort(key=lambda x: int(x['nombre_cuartel'].split()[0]) if x['nombre_cuartel'][0].isdigit() else 0)
    DATOS_EN_MEMORIA = res
    ULTIMA_ACTUALIZACION = time.time()
    LOCK_ACTUALIZACION = False
    print("--- FIN ESCANEO ---")

@app.route('/api/carros')
def api_carros():
    if (time.time() - ULTIMA_ACTUALIZACION > 20) and not LOCK_ACTUALIZACION:
        threading.Thread(target=tarea_actualizar_todo).start()
    return jsonify(DATOS_EN_MEMORIA or [])

if __name__ == '__main__':
    threading.Thread(target=tarea_actualizar_todo).start()
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)