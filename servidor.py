from flask import Flask, jsonify
from flask_cors import CORS
import requests
import re
import time
import threading
import os
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
CORS(app)

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

API_PIPA_URL = "https://api.pipa.one"
API_PIPA_TOKEN = os.environ.get("PIPA_TOKEN", "SantoDomingo978!")

DATOS_EN_MEMORIA = []
ULTIMA_ACTUALIZACION = 0
LOCK_ACTUALIZACION = False
REEMPLAZOS_POR_NUMERO = {}


def es_reemplazo(nombre):
    n = nombre.upper()
    return bool(re.match(r'^(QR|BR|HR)-', n) or re.search(r'\(R\)', n))


def _numero_en_station(station_name):
    nums = re.findall(r'\b(\d{1,2})\b', station_name)
    return int(nums[0]) if nums else None


def obtener_reemplazos_api():
    global REEMPLAZOS_POR_NUMERO
    try:
        headers = {'Authorization': f'Bearer {API_PIPA_TOKEN}'}
        resp = requests.get(
            f'{API_PIPA_URL}/vehiculos',
            params={'disponible': 'true', 'limit': 500},
            headers=headers,
            timeout=15
        )
        resp.raise_for_status()
        vehiculos = resp.json()

        por_numero = {}
        for v in vehiculos:
            nombre = v.get('name', '')
            if not es_reemplazo(nombre):
                continue
            station_name = v.get('station_name') or ''
            num = _numero_en_station(station_name)
            if num is None:
                continue
            if num not in por_numero:
                por_numero[num] = []
            por_numero[num].append(nombre)

        REEMPLAZOS_POR_NUMERO = por_numero
        total = sum(len(v) for v in por_numero.values())
        print(f"--- REEMPLAZOS: {total} máquinas disponibles en {len(por_numero)} cuarteles ---")
    except Exception as e:
        print(f"Error al obtener reemplazos de API: {e}")


def obtener_token_y_datos(cuartel):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        response = session.get(cuartel['url'], timeout=10)
        html = response.text

        inputs_estados = re.findall(r'<input id="estado\d+" type="hidden" value="(\d+)"', html)
        personal_count = inputs_estados.count('1')
        personal_str = str(personal_count)

        match = re.search(r'var url="(https://icbs\.cl/cuartel/datos\.php\?id_proce=.*?&time=.*?&hash=.*?)"', html)

        carros_limpios = []
        if match:
            url_json = match.group(1)
            try:
                resp_json = session.get(url_json, timeout=10)
                datos_raw = resp_json.json()
            except:
                return {
                    "nombre_cuartel": cuartel['nombre'],
                    "personal": personal_str,
                    "carros": [{"nombre": "SISTEMA", "estado": "OFFLINE"}],
                    "reemplazos": []
                }

            if 'carros' in datos_raw and datos_raw['carros']:
                fuente = datos_raw['carros']
                lista = fuente.values() if isinstance(fuente, dict) else fuente

                for c in lista:
                    if isinstance(c, dict):
                        nombre = c.get('nombre', '??')
                        estado_raw = str(c.get('estado_nombre', '')).upper()

                        estado_final = "EN SERVICIO"
                        if "LLAMADO" in estado_raw:
                            if "DISPONIBLE" in estado_raw:
                                estado_final = "DISPONIBLE EN LLAMADO"
                            else:
                                estado_final = "EN LLAMADO"
                        elif "FUERA" in estado_raw:
                            continue

                        carros_limpios.append({
                            "nombre": nombre,
                            "estado": estado_final
                        })
        else:
            carros_limpios = [{"nombre": "SISTEMA", "estado": "OFFLINE"}]

        return {
            "nombre_cuartel": cuartel['nombre'],
            "personal": personal_str,
            "carros": carros_limpios,
            "reemplazos": []
        }

    except Exception as e:
        return {
            "nombre_cuartel": cuartel['nombre'],
            "personal": "0",
            "carros": [{"nombre": "SISTEMA", "estado": "SIN CONEXIÓN"}],
            "reemplazos": []
        }


def tarea_actualizar_todo():
    global DATOS_EN_MEMORIA, ULTIMA_ACTUALIZACION, LOCK_ACTUALIZACION
    if LOCK_ACTUALIZACION:
        return
    LOCK_ACTUALIZACION = True
    print("--- ⚡ RE-CONTANDO VOLUNTARIOS Y CARROS ---")

    with ThreadPoolExecutor(max_workers=10) as executor:
        res = list(executor.map(obtener_token_y_datos, URLS_CUARTELES))

    obtener_reemplazos_api()

    for cuartel in res:
        num_str = cuartel['nombre_cuartel'].split()[0]
        if num_str.isdigit():
            cuartel['reemplazos'] = REEMPLAZOS_POR_NUMERO.get(int(num_str), [])

    res.sort(key=lambda x: int(x['nombre_cuartel'].split()[0]) if x['nombre_cuartel'][0].isdigit() else 0)
    DATOS_EN_MEMORIA = res
    ULTIMA_ACTUALIZACION = time.time()
    LOCK_ACTUALIZACION = False
    print("--- DATOS ACTUALIZADOS ---")


@app.route('/api/carros')
def api_carros():
    if (time.time() - ULTIMA_ACTUALIZACION > 20) and not LOCK_ACTUALIZACION:
        threading.Thread(target=tarea_actualizar_todo).start()
    return jsonify(DATOS_EN_MEMORIA or [])


if __name__ == '__main__':
    threading.Thread(target=tarea_actualizar_todo).start()
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)
