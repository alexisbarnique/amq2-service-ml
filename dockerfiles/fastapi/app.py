import os
import mlflow
import pandas as pd
import fastapi
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, ConfigDict
import logging
import awswrangler as wr

logging.basicConfig(level=logging.INFO)

app = fastapi.FastAPI()

# Traducciones de mensajes de validación
VALIDATION_MESSAGES = {
    "less_than_equal": "debe ser menor o igual a",
    "greater_than_equal": "debe ser mayor o igual a",
    "string_too_short": "debe tener al menos",
    "string_too_long": "debe tener como máximo",
    "missing": "campo requerido",
    "value_error": "valor no válido",
}

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        error_type = error["type"]
        field = error["loc"][-1] if error["loc"] else "unknown"
        
        if error_type == "less_than_equal":
            msg = f"{field} debe ser menor o igual a {error['ctx']['le']}"
        elif error_type == "greater_than_equal":
            msg = f"{field} debe ser mayor o igual a {error['ctx']['ge']}"
        elif error_type == "string_too_short":
            msg = f"{field} debe tener al menos {error['ctx']['min_length']} caracteres"
        elif error_type == "string_too_long":
            msg = f"{field} debe tener como máximo {error['ctx']['max_length']} caracteres"
        elif error_type == "missing":
            msg = f"{field} es un campo requerido"
        elif error_type == "value_error":
            msg = str(error.get("msg", "valor no válido"))
        else:
            msg = error.get("msg", "error de validación")
        
        errors.append({
            "campo": field,
            "tipo": error_type,
            "mensaje": msg,
            "valor_recibido": error.get("input")
        })
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"errores": errors}
    )

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

# Lista de valores permitidos
AGE_NEMO_CODES = {
    "C3AR3A3W", "CARECO1W", "CBARKE3W", "CCASTE3W", "CCHACA1W", "CCOLON1W",
    "CDORRE2W", "CEVIGE3W", "CLEZAM3W", "CLFLOR3W", "CLUJAN1W", "CMONTE1W",
    "CMOREN1W", "CNECNE3W", "COAZUL3W", "COLAVA3W", "SPSECRZD", "MUPITRZW",
    "DGSPCHUD", "CTRELEUW", "CPERGA1W", "CPIGUE2W", "CPRING2W", "CPUNTA2W",
    "CRAMAL1W", "CRANCH3W", "CRIVAD1W", "CROJAS1W", "CSALAD1W", "CSALTO1W",
    "CSBERN3W", "CSPEDR1W", "CSPUAN2W", "CTRLAU1W", "CZARAT1W", "EDEABA3D",
    "EDENBA1D", "EDESBA2D", "TANDIL3W", "EDESALDD", "EPECORXD", "APELPALD",
    "CALFAVQW", "CBARILRW", "EDERSARD", "EPENEUQD", "CGCRUZMW", "DECSASJW",
    "EDEMSAMD", "EDESTEMD", "ESANJUJD", "EDELAPID", "EDENOROD", "EDESURCD",
    "CEOSCOEW", "CGUALEEW", "ENERSAED", "EPESAFSD", "DPCORRWD", "EMISSAND",
    "REFSAFPD", "SECHEPHD", "EDELARFD", "EDESAEGD", "EDESASAD", "EDETUCTD",
    "EJUESAYD", "C16OCTUW", "CCOMODUW", "CGAIMAUW", "CMADRYUW", "CRAWSOUW",
    "CTRELEUW", "DGSPCHUD", "MUPITRZW", "SPSECRZD"
}

class InputData(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mes": 9,
                "age_nemo": "C3AR3A3W",
                "tipo_dia": 1,
                "tmed": 15.5
            }
        }
    )
    
    mes: int = Field(..., ge=1, le=12, description="Mes del año (1-12)")
    age_nemo: str = Field(..., min_length=8, max_length=8, description="Código de Agencia")
    tipo_dia: int = Field(..., ge=1, le=3, description="Tipo de día (1-3)")
    tmed: float = Field(..., ge=-50.0, le=60.0, description="Temperatura media en grados Celsius")

    @field_validator("age_nemo")
    @classmethod
    def validate_age_nemo(cls, v):
        if not v or not v.strip():
            raise ValueError("age_nemo no puede estar vacío")
        v = v.strip()
        if v not in AGE_NEMO_CODES:
            raise ValueError(f"age_nemo '{v}' no es un valor permitido")
        return v
    
    @field_validator("mes")
    @classmethod
    def validate_mes(cls, v):
        if v not in range(1, 13):
            raise ValueError(f"mes '{v}' no es un valor permitido")
        return v

@app.post("/predict/")
async def predict(data: InputData):
    logging.info(f"Datos recibidos: mes={data.mes} age_nemo='{data.age_nemo}' tipo_dia={data.tipo_dia} tmed={data.tmed}")

    # Crear DataFrame con el orden correcto de columnas
    X = pd.DataFrame({
        "mes": [data.mes],
        "age_nemo": [data.age_nemo],
        "tipo_dia": [data.tipo_dia],
        "tmed": [data.tmed]
    })
    logging.info(f"Vector de features:\n{X}")
    logging.info(f"Tipos de datos:\n{X.dtypes}")

    try:
        y_pred = pipeline.predict(X)
        logging.info(f"Predicción generada: {y_pred}")
        return {"prediction": float(y_pred[0])}
    except Exception as e:
        logging.error(f"Error en predicción: {type(e).__name__}: {str(e)}")
        raise


@app.post("/batch_predict/")
async def batch_predict():
    logging.info(f"Obteniendo datos de todos los meses, tipos de dia y distribuidoras con sus temperaturas promedio del mes")

    dem_df = wr.s3.read_csv("s3://data/raw/demandas.csv")

    logging.info(f"Obteniendo promedios de temperaturas por mes por distribuidora")

    temp_df = wr.s3.read_csv("s3://data/raw/temperaturas.csv")
        
    dem_df_unique = dem_df.drop_duplicates(subset=['mes', 'tipo_dia', 'age_nemo'])
    dem_df_unique = dem_df_unique.drop(columns=['fecha', 'anio_cal', 'dem_dia'])

    temp_df['mes']=pd.to_datetime(temp_df['fecha']).dt.month
    
    temp_df_grouped = temp_df.groupby(['mes', 'region'], as_index=False).mean(numeric_only=True).rename(columns={'region':'rge_nemo'})

    X = dem_df_unique.merge(temp_df_grouped, on=['mes','rge_nemo'], how='left').drop(columns=['rge_nemo'])

    logging.info(f"Realizando prediccion.")

    y_pred = pipeline.predict(X)
    logging.info(f"Predicción generada: {y_pred[:5]}")

    return {"prediction": float(y_pred[:5])}
