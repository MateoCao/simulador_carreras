from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import socketio
import asyncio
import random
import xml.etree.ElementTree as ET
import os
from io import BytesIO
import math
from typing import List, Dict
from datetime import datetime

app = FastAPI()

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de Socket.IO
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*")
app.mount("/socket.io", socketio.ASGIApp(sio))

# Parámetros de la carrera
distancia_pista = 50
cantidad_corredores = 5
corredores: List[Dict] = []
simulacion_activa = False  # Estado de la simulación
start_time = None

# Inicialización de corredores
def inicializar_corredores():
    global corredores
    corredores = []
    for i in range(cantidad_corredores):
        velocidad_inicial = random.uniform(8, 9)
        corredores.append({
            "id": i + 1,
            "vuelta_actual": 0,
            "tiempo_total": 0.0,
            "mejor_vuelta": float("inf"),
            "ultimo_tiempo_vuelta": 0.0,
            "velocidad_actual": velocidad_inicial,
            "distancia_total_recorrida": 0.0
        })

# Función para simular el paso de una vuelta
async def simular_vuelta(corredor: Dict):
    velocidad_variada = corredor["velocidad_actual"] + random.uniform(-0.8, 0.8)
    tiempo_vuelta = distancia_pista / velocidad_variada
    
    corredor["tiempo_total"] += tiempo_vuelta
    corredor["ultimo_tiempo_vuelta"] = tiempo_vuelta
    corredor["velocidad_actual"] = velocidad_variada
    corredor["distancia_total_recorrida"] += velocidad_variada
    corredor["vuelta_actual"] = math.floor(corredor["distancia_total_recorrida"] / distancia_pista)

    if tiempo_vuelta < corredor["mejor_vuelta"]:
        corredor["mejor_vuelta"] = tiempo_vuelta

# Función para generar el XML
async def generar_xml():
    while simulacion_activa:
        root = ET.Element("timing")
        primer_lugar = min(corredores, key=lambda x: x["tiempo_total"])
        
        for corredor in corredores:
            runner = ET.SubElement(root, "runner", id=str(corredor["id"]))
            
            datos = {
                "vuelta_completada": str(corredor["vuelta_actual"]),
                "velocidad_actual": f"{corredor['velocidad_actual']:.2f}",
                "tiempo_ultima_vuelta": f"{corredor['ultimo_tiempo_vuelta']:.2f}",
                "tiempo_total": f"{corredor['tiempo_total']:.2f}",
                "tiempo_mejor_vuelta": f"{corredor['mejor_vuelta']:.2f}",
                "distancia_total_recorrida": f"{corredor['distancia_total_recorrida']:.2f}",
            }
            
            diferencia_primer = corredor["tiempo_total"] - primer_lugar["tiempo_total"]
            sorted_corredores = sorted(corredores, key=lambda x: x["tiempo_total"])
            indice = sorted_corredores.index(corredor)
            
            for key, value in datos.items():
                ET.SubElement(runner, key).text = value
            
            ET.SubElement(runner, "diferencia_primer_lugar").text = f"{diferencia_primer:.2f}"
            diferencia_siguiente = (corredor["tiempo_total"] - sorted_corredores[indice + 1]["tiempo_total"]) if indice < len(sorted_corredores) - 1 else 0.0
            ET.SubElement(runner, "diferencia_siguiente").text = f"{diferencia_siguiente:.2f}"

        # Guardar XML
        xml_data = BytesIO()
        ET.ElementTree(root).write(xml_data, encoding='utf-8', xml_declaration=True)
        with open("timing.xml", "wb") as f:
            f.write(xml_data.getvalue())

        await asyncio.sleep(1)

# Tarea de simulación
async def simular_carrera():
    while simulacion_activa:
        tiempo_transcurrido = (datetime.now() - start_time).total_seconds()
        await asyncio.gather(*[simular_vuelta(c) for c in corredores])
        await sio.emit('update', {
            'runners': corredores,
            'timestamp': tiempo_transcurrido
        })
        await asyncio.sleep(1)

# Endpoint para iniciar la simulación
@app.post("/iniciar-simulacion")
async def iniciar_simulacion():
    global start_time,simulacion_activa
    if not simulacion_activa:
        start_time = datetime.now()
        simulacion_activa = True
        inicializar_corredores()
        asyncio.create_task(generar_xml())
        asyncio.create_task(simular_carrera())
        return {"mensaje": "Simulación iniciada"}
    else:
        return {"mensaje": "La simulación ya está activa"}

# Endpoint para detener la simulación
@app.post("/detener-simulacion")
async def detener_simulacion():
    global simulacion_activa
    if simulacion_activa:
        simulacion_activa = False
        return {"mensaje": "Simulación detenida"}
    else:
        return {"mensaje": "La simulación no está activa"}

# Endpoint para obtener el XML
@app.get("/timing.xml")
async def get_xml():
    try:
        with open("timing.xml", "rb") as f:
            return Response(content=f.read(), media_type="application/xml")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="XML no disponible")

# Endpoint de salud
@app.get("/health")
async def health_check():
    return {"status": "ok", "websocket_clients": len(sio.manager.get_pids())}

# Eventos de Socket.IO
@sio.event
async def connect(sid, environ):
    print(f"Cliente conectado: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Cliente desconectado: {sid}")

# Ejecutar con Uvicorn
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)