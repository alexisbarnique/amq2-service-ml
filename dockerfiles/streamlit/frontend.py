import os
import streamlit as st
import requests
import mlflow

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

st.title("Demanda Eléctrica ⚡")
st.subheader("Estimación de demanda diaria por distruibuidora eléctrica", divider="gray")

# Inputs de usuario
meses_dict = {
    "Enero": 1,
    "Febrero": 2,
    "Marzo": 3,
    "Abril": 4,
    "Mayo": 5,
    "Junio": 6,
    "Julio": 7,
    "Agosto": 8,
    "Septiembre": 9,
    "Octubre": 10,
    "Noviembre": 11,
    "Diciembre": 12
}

tipo_dia_dict = {
    "Hábil":1,
    "Semi hábil":2,
    "No hábil":3
}

feature1 = st.selectbox("Mes", options = list(meses_dict.keys()))            # string
feature2 = st.selectbox("Distribuidor", options = age_unique_list)           # string
feature3 = st.selectbox("Tipo de día", options = list(tipo_dia_dict.keys())) # string
feature4 = st.number_input("Temperatura media", min_value=-20.0, max_value=60.0, value=20.0, step=1.0)                   # float


if st.button("Predecir"):
    # Llamada a la API FastAPI
    response = requests.post(
        f"{API_URL}/predict",
        json={"mes": meses_dict[feature1], "age_nemo": feature2, "tipo_dia": tipo_dia_dict[feature3], "tmed": feature4}
    )
    if response.status_code == 200:
        result = response.json()
        st.success(f"Predicción de demanda: {round(result['prediction']/1000,2)} GWh")
    else:
        st.error("Error al consultar la API")

# Sección de reentrenamiento
st.divider()
st.subheader("🔄 Gestión del Modelo")

st.write("Administra el ciclo de vida del modelo de demanda eléctrica.")

# URL de Airflow (ajustar según tu configuración)
AIRFLOW_URL = os.getenv("AIRFLOW_URL", "http://airflow-apiserver:8080")

# Crear sesión con autenticación
def get_airflow_token():
    """Get JWT token from Airflow Simple Auth Manager"""
    import requests
    
    try:
        # With simple_auth_manager_all_admins=True, we can get a token without credentials
        response = requests.get(
            f"{AIRFLOW_URL}/auth/token",
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            return result.get("access_token")
        else:
            st.error(f"Error obteniendo token: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error de conexión al obtener token: {str(e)}")
        return None

def trigger_dag(dag_id, dag_name):
    """Helper function to trigger a DAG with JWT token authentication"""
    import requests
    from datetime import datetime, timezone
    
    try:
        # Get JWT token
        token = get_airflow_token()
        if not token:
            return None
        
        # Trigger DAG with token
        # Airflow 3.0 API requires logical_date
        logical_date = datetime.now(timezone.utc).isoformat()
        response = requests.post(
            f"{AIRFLOW_URL}/api/v2/dags/{dag_id}/dagRuns",
            json={"logical_date": logical_date},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            },
            timeout=30
        )
        
        return response
    except Exception as e:
        st.error(f"Error de conexión: {str(e)}")
        return None

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🔄 Reentrenamiento Rápido")
    st.write("Reentrena el modelo con datos actualizados manteniendo los mismos hiperparámetros.")
    
    if st.button("🚀 Reentrenar Modelo", use_container_width=True):
        DAG_ID = "process_etl_electrical_demand"
        with st.spinner("Ejecutando reentrenamiento..."):
            response = trigger_dag(DAG_ID, "Reentrenamiento")
            
            if response and response.status_code in [200, 201]:
                result = response.json()
                dag_run_id = result.get("dag_run_id", "N/A")
                st.success(f"✅ Reentrenamiento iniciado! Run ID: {dag_run_id}")
                st.info(f"Monitorea el progreso: http://localhost:8080/dags/{DAG_ID}/grid")
            elif response:
                st.error(f"❌ Error: {response.status_code}")
                st.error(f"Detalle: {response.text}")
                st.info("💡 Prueba ejecutar manualmente desde Airflow UI: http://localhost:8080")

with col2:
    st.markdown("### 🎯 Optimización Completa")
    st.write("Búsqueda de hiperparámetros con Optuna para mejorar el rendimiento del modelo.")
    
    if st.button("⚡ Optimizar Hiperparámetros", use_container_width=True):
        DAG_ID = "hyperparameter_tuning"
        with st.spinner("Ejecutando optimización (esto puede tomar tiempo)..."):
            response = trigger_dag(DAG_ID, "Optimización")
            
            if response and response.status_code in [200, 201]:
                result = response.json()
                dag_run_id = result.get("dag_run_id", "N/A")
                st.success(f"✅ Optimización iniciada! Run ID: {dag_run_id}")
                st.info(f"Monitorea el progreso: http://localhost:8080/dags/{DAG_ID}/grid")
                st.warning("⏱️ Esta operación puede tomar 30-60 minutos.")
            elif response:
                st.error(f"❌ Error: {response.status_code}")
                st.error(f"Detalle: {response.text}")
                st.info("💡 Prueba ejecutar manualmente desde Airflow UI: http://localhost:8080")
