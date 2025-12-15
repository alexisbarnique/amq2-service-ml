import os
import streamlit as st
import requests
import mlflow
import pandas as pd

# Base URL del backend
API_URL = os.getenv("API_URL", "http://fastapi:8800")

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

#-- Se obtiene el mapeo de age_nemo
age_map = pipeline.named_steps['pre'].mapping_.reset_index()
age_unique_list = sorted(age_map['dist_tipodia'].str[:-2].unique(), key=str.casefold)

st.title("Demanda Eléctrica ⚡ predicción en lote")
st.subheader("Estimación de demanda diaria por distruibuidora eléctrica", divider="gray")

st.text("Herramienta para producir predicción en lote. Se recuperarán los datos de todos los meses, tipos de dia y distribuidoras, con la temperatura promedio del mes para esa distribuidora.")

st.text("Luego, se realizará la predicción sobre todos esos registros.")

if st.button("Predecir en lote"):
    # Llamada a la API FastAPI
    response = requests.post(
        f"{API_URL}/batch_predict",
    )
    if response.status_code == 200:
        result = response.json()
        st.success("Predicción de demanda en GWh:")
        batch_df = pd.DataFrame(result)
        batch_df['demanda'] = (batch_df['demanda']/1000).round(2)
        batch_df['tmed'] = batch_df['tmed'].round(1)
        st.dataframe(batch_df.sort_values(by=['mes', 'age_nemo', 'tipo_dia'])[['mes', 'age_nemo', 'tipo_dia', 'tmed', 'demanda']])

    else:
        st.error("Error al consultar la API")
