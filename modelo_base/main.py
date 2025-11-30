import joblib
import numpy as np
import fastapi
from pydantic import BaseModel
import logging

logging.basicConfig(level=logging.INFO)

app = fastapi.FastAPI()
# Cargar modelo y encoding
model = joblib.load("best_model.pkl")
encoding = joblib.load("encoding.pkl")

class InputData(BaseModel):
    mes: int
    age_nemo: str
    tipo_dia: str
    tmed: float

@app.post("/predict/")
async def predict(data: InputData):
    logging.info(f"Datos recibidos: {data}")

    mes_sin = np.sin(2*np.pi*data.mes/12)
    mes_cos = np.cos(2*np.pi*data.mes/12)
    dist_tipodia = f"{data.age_nemo}_{data.tipo_dia}"
    dist_tipodia_te = encoding.get(dist_tipodia, np.mean(list(encoding.values())))

    logging.debug(f"Valores calculados → mes_sin: {mes_sin}, mes_cos: {mes_cos}, dist_tipodia_te: {dist_tipodia_te}")

    X = np.array([[data.mes, data.tmed, data.tmed**2, mes_sin, mes_cos, dist_tipodia_te]])
    logging.info(f"Vector de features: {X}")

    y_pred = model.predict(X)
    logging.info(f"Predicción generada: {y_pred}")

    return {"prediction": float(y_pred[0])}

