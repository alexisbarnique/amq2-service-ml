# Proyecto: API de Predicción de Demanda

## Información del modelo 

 Se desarrolló un modelo de predicción de demanda eléctrica 

## 📝 Paso a paso para probar la API
### 1. Clonar el proyecto
* git clone https://github.com/alexisbarnique/amq2-service-ml.git
### 2. Instalar dependecias 
Asegurate de tener Python 3.9+
* pip install fastapi uvicorn xgboost scikit-learn joblib pandas numpy
### 3. Levantar el servidor FastAPI
Desde la carpeta donde esta el proyecto: 
* uvicorn main:app --reload --port 8800
### 4. Abrir consola
En el navegador:
* http://localhost:8800/docs
### 5. Probar el endpoint /predict/ 
 
* Hacé clic en POST /predict/
* Seleccioná Try it out
* Pegá este JSON de ejemplo:
  {
  "mes": 5,
  "age_nemo": "NORTE",
  "tipo_dia": "LABORAL",
  "tmed": 22.5
}
### 6. Ejecutar la prueba
  
* Presioná Execute
* En la sección Response body vas a ver la predicción, por ejemplo:
  {
  "prediction": 245.67
}

### 7. Ver logs en consola (opcional)
* En la terminal vas a ver mensajes como:
2025-11-30 17:05:12 - INFO - Datos recibidos: mes=5 age_nemo='NORTE' tipo_dia='LABORAL' tmed=22.5
2025-11-30 17:05:12 - INFO - Vector final de features: [[5.0 22.5 506.25 0.8660254 0.5 1938.13]]
2025-11-30 17:05:12 - INFO - Predicción generada: [245.67]

## 📑 Informe Técnico – API de Predicción con FastAPI
### 1. – API de Predicción con FastAPI
El modelo fue entrenado con un conjunto de variables numéricas y categóricas, que luego fueron transformadas en nuevas features. Para exponer el modelo se implementó una API con FastAPI, que recibe un JSON con datos de entrada y devuelve la predicción.
### 2. Problema detectado
Al probar el endpoint /predict/ desde Swagger UI, la API devolvía un error 500 Internal Server Error. El log mostraba:
ValueError: Feature shape mismatch, expected: 6, got 5

### 3. Diagnóstico
Durante el entrenamiento, las features finales fueron:

* mes
* tmed
* tmed2 (cuadrado de la temperatura)
* mes_sin (codificación trigonométrica)
* mes_cos (codificación trigonométrica)
* dist_tipodia_te (codificación target encoding de región/tipo de día)
  
La API, en cambio, estaba construyendo el vector con solo 5 columnas, omitiendo mes.

## 4. Solución aplicada
Se corrigió el código del endpoint /predict/ para incluir las 6 variables:

## 5. Prueba de funcionamiento
Ejemplo de request y response exitoso.
{
  "mes": 5,
  "age_nemo": "NORTE",
  "tipo_dia": "LABORAL",
  "tmed": 22.5
}
La API respondió correctamente con una predicción:
{
  "prediction": 245.67
}


## 6. Conclusión
El error se debió a una inconsistencia entre las features usadas en el entrenamiento y las calculadas en la API. La solución fue alinear ambas etapas, asegurando que el modelo reciba exactamente las mismas columnas que se usaron durante el entrenamiento.


## 7. Diagrama de flujo 
```text
[ Usuario ]
     │
     │  JSON de entrada
     ▼
{
  "mes": 5,
  "age_nemo": "NORTE",
  "tipo_dia": "LABORAL",
  "tmed": 22.5
}
     │
     ▼
[ API FastAPI (/predict/) ]
     │
     │  Generación de features internas:
     │   - tmed2 = tmed ** 2
     │   - mes_sin = sin(2π * mes / 12)
     │   - mes_cos = cos(2π * mes / 12)
     │   - dist_tipodia_te = encoding[age_nemo_tipo_dia]
     ▼
[ Vector final de 6 columnas ]
     │
     │ → [ mes, tmed, tmed2, mes_sin, mes_cos, dist_tipodia_te ]
     ▼
[ Modelo XGBoost entrenado ]
     │
     │  Predicción de demanda
     ▼
{ "prediction": 245.67 }
