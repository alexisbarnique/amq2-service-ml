import os
import mlflow
import pandas as pd
import fastapi
from pydantic import BaseModel, Field, validator
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
    mes: int = Field(..., ge=1, le=12, description="Mes del año (1-12)")
    age_nemo: str = Field(..., min_length=8, description="Código de Agencia")
    tipo_dia: int = Field(..., ge=1, le=3, description="Tipo de día (1-3)")
    tmed: float = Field(..., ge=-50.0, le=60.0, description="Temperatura media en grados Celsius")

    @validator("age_nemo")
    def validate_age_nemo(cls, v):
        if not v or not v.strip():
            raise ValueError("age_nemo no puede estar vacío")
        v = v.strip()
        if v not in AGE_NEMO_CODES:
            raise ValueError(f"age_nemo '{v}' no es un valor permitido. Valores posibles: age_nemo
C3AR3A3W
CARECO1W
CBARKE3W
CCASTE3W
CCHACA1W
CCOLON1W
CDORRE2W
CEVIGE3W
CLEZAM3W
CLFLOR3W
CLUJAN1W
CMONTE1W
CMOREN1W
CNECNE3W
COAZUL3W
COLAVA3W
SPSECRZD
MUPITRZW
DGSPCHUD
CTRELEUW
CPERGA1W
CPIGUE2W
CPRING2W
CPUNTA2W
CRAMAL1W
CRANCH3W
CRIVAD1W
CROJAS1W
CSALAD1W
CSALTO1W
CSBERN3W
CSPEDR1W
CSPUAN2W
CTRLAU1W
CZARAT1W
EDEABA3D
EDENBA1D
EDESBA2D
TANDIL3W
EDESALDD
EPECORXD
APELPALD
CALFAVQW
CBARILRW
EDERSARD
EPENEUQD
CGCRUZMW
DECSASJW
EDEMSAMD
EDESTEMD
ESANJUJD
EDELAPID
EDENOROD
EDESURCD
CEOSCOEW
CGUALEEW
ENERSAED
EPESAFSD
DPCORRWD
EMISSAND
REFSAFPD
SECHEPHD
EDELARFD
EDESAEGD
EDESASAD
EDETUCTD
EJUESAYD
C16OCTUW
CCOMODUW
CGAIMAUW
CMADRYUW
CRAWSOUW
CTRELEUW
DGSPCHUD
MUPITRZW
SPSECRZD
C3AR3A3W
CARECO1W
CBARKE3W
CCASTE3W")
        return v
    
    @validator('mes')
    def validate_mes(cls, v):
        if not isinstance(v, int) or v < 1 or v > 12:
            raise ValueError('mes debe ser un entero entre 1 y 12')
        return v
    
    @validator('tipo_dia')
    def validate_tipo_dia(cls, v):
        if not isinstance(v, int) or v < 1 or v > 3:
            raise ValueError('tipo_dia debe ser un entero entre 1 y 3')
        return v
    
    @validator('tmed')
    def validate_tmed(cls, v):
        if not isinstance(v, (int, float)):
            raise ValueError('tmed debe ser un número')
        if v < -50.0 or v > 60.0:
            raise ValueError('tmed debe estar entre -50.0 y 60.0 grados Celsius')
        return float(v)

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
