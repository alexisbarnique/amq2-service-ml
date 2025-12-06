import os
import mlflow
import pandas as pd
import fastapi
from pydantic import BaseModel
import logging

logging.basicConfig(level=logging.INFO)

app = fastapi.FastAPI()

try:
    # Intenta cargar pipeline de MLFlow
    print("[load] Intentando cargar desde MLFlow ...")
    mlflow.set_tracking_uri("http://mlflow:5000") # en el contenedor corre en el puerto 5000, en el host en el 5001
    client_mlflow = mlflow.MlflowClient()
    #-- Carga de los datos del modelo (es la estructura general registrada en MLFlow)
    model_data_mlflow = client_mlflow.get_model_version_by_alias(name="demanda_distribuidores", alias="champion")
    #-- Carga del modelo propiamente dicho, en este caso es el pipeline que incluye el preprocesador y el modelo
    pipeline = mlflow.sklearn.load_model(model_data_mlflow.source)
except:
    # Si no puede desde MLFlow, intenta hacerlo desde el backup en el bucket s3
    os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://127.0.0.1:9000")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "minio")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "minio123")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    backup_uri = "s3://mlflow/backups/demanda_distribuidores/best_model"
    print(f"[load] Intentando cargar desde backup {backup_uri} ...")
    pipeline = mlflow.sklearn.load_model(backup_uri)

class InputData(BaseModel):
    mes: int
    age_nemo: str
    tipo_dia: int
    tmed: float

@app.post("/predict/")
async def predict(data: InputData):
    logging.info(f"Datos recibidos: {data}")

    X = pd.DataFrame([
    {"mes": data.mes,  "age_nemo": data.age_nemo, "tipo_dia": data.tipo_dia, "tmed": data.tmed}
])
    logging.info(f"Vector de features: {X}")

    y_pred = pipeline.predict(X)
    logging.info(f"Predicción generada: {y_pred}")

    return {"prediction": float(y_pred[0])}
