# Modelo de Demanda Eléctrica ⚡

El modelo implementado en producción tiene como objetivo estimar la demanda eléctrica diaria de cada distribuidor de la República Argentina.

Las principales características que influyen en el consumo eléctrico diario son la temperatura y el tipo de día (hábil, semi hábil o no hábil). Por lo tanto, estos son los datos de entrada que se utilizan para realizar la predicción, además de la distribuidora.

Para el entrenamiento del modelo, se cuenta con datos de demanda diaria de todas las distribuidoras (son más de 70) y con los datos de temperatura media diaria de las distintas regiones del país. Luego, se combinan utilizando la región y la fecha.

Previo al entrenamiento, se toma la demanda media de cada distribuidora para cada mes de cada año y tipo de día, ya que el objetivo último de este modelo es realizar una estimación para obtener la demanda característica de cada tipo de día de los distintos meses del año, para todas las distribuidoras.

## Resumen
- Objetivo: estimar la demanda eléctrica diaria por distribuidor en la República Argentina.
- Entradas principales: temperatura media diaria, tipo de día (hábil / semi hábil / no hábil) y distribuidora.
- Salida: demanda característica por tipo de día y mes para cada distribuidora.

## Contenido del repo
- airflow/: DAGs, configuración y logs de Airflow.
- modelo_base/: notebooks y código para entrenar/experimentar el modelo base.
- docker-compose.yaml, .env: despliegue local (Airflow, MLflow, MinIO, API, Streamlit).

## Requisitos
- Docker & Docker Compose (instrucciones oficiales).
- Git.
- macOS / Linux: se recomienda usar UID del usuario para evitar permisos en volúmenes de Airflow.

## Preparación rápida (macOS / Linux)
1. Clonar:
   git clone <repo>
   cd amq2-service-ml

2. Crear carpetas esperadas por Airflow (si no existen):
   mkdir -p airflow/{config,dags,logs,plugins}

3. Ajustar UID en `.env` (macOS / Linux):
   - Obtener UID: id -u $(whoami)
   - Reemplazar `AIRFLOW_UID` en `.env` con ese valor.

## Despliegue local
- Levantar todos los servicios:

``` bash
  docker compose --profile all up
```

## Apagar los servicios

Estos servicios ocupan cierta cantidad de memoria RAM y procesamiento, por lo que cuando no se están utilizando, se recomienda detenerlos. Para hacerlo, ejecuta el siguiente comando:

``` bash
docker compose --profile all down
```

Si deseas no solo detenerlos, sino también eliminar toda la infraestructura (liberando espacio en disco), utiliza el siguiente comando:

``` bash
docker compose down --rmi all --volumes
```

Nota: Si haces esto, perderás todo en los buckets y bases de datos.

## URLs por defecto (contenedores locales)
- Airflow UI: http://localhost:8080
- MLflow UI: http://localhost:5001
- MinIO (UI): http://localhost:9001
- API: http://localhost:8800/
- API docs (Swagger): http://localhost:8800/docs
- Streamlit app: http://localhost:8501/

## Registro inicial del modelo (obligatorio para producción)
- Ejecutar el notebook `modelo_base/experimento_modelo.ipynb` para registrar el modelo inicial en MLflow.
- Si no se registra, la API usará un modelo de backup almacenado en un bucket S3 incluido en el repo.

## Airflow — DAGs relevantes
- airflow/dags/etl_process.py: ETL que prepara datos limpios y guarda splits en S3.
- airflow/dags/retrain_and_promote.py: DAG de reentrenamiento automático que compara y promueve modelos en MLflow.

## Variables de Airflow importantes (definidas en Airflow → Admin → Variables)
- clean_data_path: ruta S3 al CSV limpio (ej. s3://data/clean/clean_data.csv)
- mlflow_tracking_uri: URI del tracking server (ej. http://mlflow:5000)
- model_name: nombre en el Model Registry (ej. demanda_distribuidores)
- target_col: nombre de la columna objetivo (ej. dem_dia)
- improvement_threshold: fracción mínima de mejora para promover (ej. 0.01)

## Uso de app

Se desarrolló una app de streamlit para utilizar el servicio mediante una interfaz gráfica. Para acceder, ingresar a:

-   http://localhost:8501/

## Recomendaciones para DAGs y reentrenamiento
- Definir correctamente `clean_data_path` y `model_name` antes de ejecutar `retrain_and_promote_model`.
- Revisar permisos y credenciales para acceso a S3/MinIO desde contenedores.
- Habilitar logging y alertas (Slack / email) para procesos críticos.

## Depuración rápida
- Verificar que todos los contenedores estén healthy:
  docker ps -a
- Logs de Airflow (scheduler / webserver): revisar en la carpeta `airflow/logs` o desde la UI.
- Si MLflow no conecta desde el DAG, revisar `mlflow_tracking_uri` y el puerto en `.env`.
- MinIO: credenciales por defecto están en `.env` (examinar variables MINIO_ROOT_USER, MINIO_ROOT_PASSWORD).