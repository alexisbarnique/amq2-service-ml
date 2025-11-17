import datetime

from airflow.decorators import dag, task

markdown_text = """
### ETL para datos de demanda eléctrica

Toma los datos crudos de demanda eléctrica y temperatura del [repositorio](https://github.com/dgpaniagua/amq2-service-ml/tree/main/modelo_base).
Realiza el preprocesamiento combinando ambos datasets y codificando variables, para luego guardar de forma separada
el dataset de entrenamiento y el de test en el bucket S3.
"""


default_args = {
    'owner': "Alexis, Bárbara, Brian, Daniel y Gabriela",
    'depends_on_past': False,
    'schedule_interval': None,
    'retries': 1,
    'retry_delay': datetime.timedelta(minutes=5),
    'dagrun_timeout': datetime.timedelta(minutes=15)
}


@dag(
    dag_id="process_etl_electrical_demand",
    description="Proceso de ETL para datos de demanda eléctrica y temperatura.",
    doc_md=markdown_text,
    tags=["ETL", "Demanda", "Temperatura"],
    default_args=default_args,
    catchup=False,
)
def process_etl_electrical_demand():

    @task.virtualenv(
        task_id="get_raw_data",
        requirements=["awswrangler==3.6.0","pandas==2.3.3", "logging==0.5.1.2"],
        system_site_packages=True
    )
    def get_raw_data():
        """
        Descargar CSV con datos de demanda y temperatura desde GitHub y subir a S3.
        """
        import awswrangler as wr
        import pandas as pd
        import logging
        from airflow.models import Variable

        # Variables fijadas por código
        dem_csv_url  = "https://raw.githubusercontent.com/alexisbarnique/amq2-service-ml/refs/heads/main/modelo_base/dem_20110401_20251022.csv"
        temp_csv_url = "https://raw.githubusercontent.com/alexisbarnique/amq2-service-ml/refs/heads/main/modelo_base/temperaturas.csv"
        dem_path  = "s3://data/raw/demandas.csv"
        temp_path = "s3://data/raw/temperaturas.csv"

        # Variables de Airflow
        # dem_csv_url = Variable.get("dem_csv_url")
        # temp_csv_url = Variable.get("temp_csv_url")
        # dem_path = Variable.get("dem_path")
        # temp_path = Variable.get("temp_path")

        logging.info("Descargando archivos CSV...")
        try:
            dem_df = pd.read_csv(dem_csv_url)
            temp_df = pd.read_csv(temp_csv_url)
        except Exception as e:
            raise RuntimeError(f"Error al descargar CSV: {e}")

        logging.info("Subiendo archivos a S3...")
        try:
            wr.s3.to_csv(df=dem_df, path=dem_path, index=False)
            wr.s3.to_csv(df=temp_df, path=temp_path, index=False)
        except Exception as e:
            raise RuntimeError(f"Error al subir archivos a S3: {e}")

        logging.info("Carga completada.")
        return {"dem_path": dem_path, "temp_path": temp_path}


    @task.virtualenv(
        task_id="data_wrangling",
        requirements=["awswrangler==3.6.0","pandas==2.3.3", "logging==0.5.1.2"],
        system_site_packages=True
    )
    def data_wrangling():
        """
        Combina y aplica transformaciones necesarias a los datos de temperatura y demanda.
        """
        import awswrangler as wr
        import pandas as pd
        import logging
        from airflow.models import Variable

        #-- 0. Rutas útiles
        # Variables fijadas por código
        dem_path  = "s3://data/raw/demandas.csv"
        temp_path = "s3://data/raw/temperaturas.csv"
        clean_data_path = "s3://data/raw/clean_data.csv"

        # Variables de Airflow
        # dem_path = Variable.get("dem_path")
        # temp_path = Variable.get("temp_path")

        #-- 1. Lectura de demanda histórica
        logging.info("Cargando datos de demanda...")
        try:
            dem_df = wr.s3.read_csv(dem_path)
            dem_df['fecha'] = pd.to_datetime(dem_df['fecha'])
        except Exception as e:
            raise RuntimeError(f"Error al leer el archivo de demanda de S3: {e}")

        #-- Se toman fechas desde el 2021, ya que tienen mayor relevancia por ser más actuales.
        dem_df = dem_df.copy().loc[dem_df['anio_cal']>=2021]

        #-- 2. Lectura de temperaturas
        logging.info("Cargando datos de temperatura...")
        try:
            temp_df = wr.s3.read_csv(temp_path)
            temp_df = temp_df.copy().loc[temp_df['fecha']>='2021-01-01'] #Se hace una copia para evitar warnings
            temp_df['fecha'] = pd.to_datetime(temp_df['fecha'])
        except Exception as e:
            raise RuntimeError(f"Error al leer el archivo de temperatura de S3: {e}")

        #-- 3. Conformación de todo el dataset
        #-- 3.1 Join entre temperatura y demanda
        logging.info("Procesando datos de demanda y temperatura...")
        try:
            df_full = pd.merge(dem_df, temp_df, left_on=['fecha', 'rge_nemo'], right_on=['fecha', 'region'])
            df_full = df_full.rename(columns={'anio_cal':'year'})

            #-- 3.2 Selección de columnas
            cat_cols = ['mes', 'age_nemo', 'tipo_dia']
            num_cols = ['year', 'tmed']
            target = ['dem_dia']
            df = df_full[cat_cols + num_cols + target]

            #-- 3.3 Se descartan filas con nulos (son pocos)
            df = df.dropna()

            #-- 3.4 Se toman los promedios mensuales
            clean_data = df.groupby(['year']+cat_cols).mean().round(2).reset_index()

            #-- 3.5 Se agrega la temperatura al cuadrado
            clean_data['tmed2'] = clean_data['tmed'] ** 2
        except Exception as e:
            raise RuntimeError(f"Error al procesar datos de demanda y temperatura: {e}")

        #-- 4. Cargar archivos a S3
        logging.info("Subiendo archivo a S3...")
        try:
            wr.s3.to_csv(df=clean_data, path=clean_data_path, index=False)
        except Exception as e:
            raise RuntimeError(f"Error al subir archivo a S3: {e}")

        logging.info("Carga completada.")
        return {"clean_data_path": clean_data_path}


    get_raw_data() >> data_wrangling()


dag = process_etl_electrical_demand()