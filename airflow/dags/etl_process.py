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
    'retries': 0,
    #'retry_delay': datetime.timedelta(minutes=5),
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

    def get_variable(key):
        """
        Obtiene el valor de una variable de Airflow. Se define de forma separada para ejecutarla en
        el entorno general del contenedor, ya que en un entorno virtual independiente, 
        como se ejecutan las otras tareas, no tiene acceso a las variables.

        Args:
            key (str): Clave (Key) de la variable a obtener. 

        Returns:
            str: Valor de la variable solicitada.
        """
        from airflow.models import Variable
        
        value = Variable.get(key)
        if not value:
            raise ValueError(f"La variable '{key}' está vacía o no existe.")
        return value


    @task.virtualenv(
        task_id="get_raw_data",
        requirements=["awswrangler==3.6.0"],
        system_site_packages=True
    )
    def get_raw_data(dem_csv_url, temp_csv_url, dem_path, temp_path):
        """
        Descarga los archivos CSV de demanda eléctrica y temperatura desde Github y los sube al bucket S3.

        Args:
            dem_csv_url (str): URL de Github con los datos crudos de demandas en formato csv.
            temp_csv_url (str): URL de Github con los datos crudos de temperaturas en formato csv.
            dem_path (str): Ruta en el bucket S3 donde se guardará el archivo de demandas.
            temp_path (str): Ruta en el bucket S3 donde se guardará el archivo de temperaturas.

        Returns:
            dict: Diccionario con las rutas en S3 de los archivos subidos.
                - dem_path: Ruta del archivo de demandas en S3.
                - temp_path: Ruta del archivo de temperaturas en S3.
        """
        import awswrangler as wr
        import pandas as pd
        import logging

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
        requirements=["awswrangler==3.6.0"],
        system_site_packages=True
    )
    def data_wrangling(get_raw_data_res, clean_data_path):    
        """
        Realiza el preprocesamiento de los datos de demanda y temperatura.

        Proceso:
        - Lee los archivos de demanda y temperatura desde S3, usando las rutas provistas por la tarea anterior.
        - Filtra y transforma los datos relevantes.
        - Combina ambos datasets y genera el dataset limpio.
        - Guarda el dataset limpio en S3.

        Args:
            get_raw_data_res (dict): Diccionario retornado por la tarea get_raw_data, con las rutas:
                - dem_path (str): Ruta en S3 del archivo de demandas.
                - temp_path (str): Ruta en S3 del archivo de temperaturas.
            clean_data_path (str): Ruta en S3 donde se guardará el archivo de datos limpios.

        Returns:
            dict: Diccionario con información para la siguiente etapa:
                - clean_data_path (str): Ruta del archivo limpio en S3.
                - cat_cols (list): Lista con nombres de las columnas categóricas.
                - num_cols (list): Lista con nombres de las columnas numéricas.
                - target (list): Lista con el nombre de la columna objetivo.
        """
        import awswrangler as wr
        import pandas as pd
        import logging

        #-- 0. Datos de tarea anterior
        dem_path = get_raw_data_res["dem_path"]
        temp_path = get_raw_data_res["temp_path"]

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
            raise RuntimeError(f"Error al leer el archivo de temperatura de S3 en {temp_path}. Detalles: {e}")

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

            #-- 3.5 Eliminar columna year
            clean_data = clean_data.drop(columns='year')

            #-- 3.6 Redefinición de columnas numéricas: se elimina year
            num_cols = ['tmed']
        except Exception as e:
            raise RuntimeError(f"Error al procesar datos de demanda y temperatura: {e}")

        #-- 4. Cargar archivos a S3
        logging.info("Subiendo archivo a S3...")
        try:
            wr.s3.to_csv(df=clean_data, path=clean_data_path, index=False)
        except Exception as e:
            raise RuntimeError(f"Error al subir archivo a S3: {e}")

        logging.info("Carga completada.")
        return {"clean_data_path": clean_data_path, "cat_cols": cat_cols, "num_cols": num_cols, "target":target}


    @task.virtualenv(
        task_id="split_encoding",
        requirements=["awswrangler==3.6.0", "scikit-learn==1.7.2"],
        system_site_packages=True
    )
    def retrain(data_wrangling_res):        
        """
        Realiza el split en conjuntos de entrenamiento y test, y aplica codificaciones a las variables categóricas y temporales.

        Proceso:
        - Lee el dataset limpio desde S3, usando la ruta provista por la tarea anterior.
        - Separa los datos en X_train, X_test, y_train, y_test usando `train_test_split`.
        - Aplica codificación cíclica a la columna 'mes'.
        - Aplica target encoding a la combinación de 'age_nemo' y 'tipo_dia'.
        - Elimina las columnas originales categóricas tras la codificación.
        - Guarda los datasets procesados en S3.

        Args:
            data_wrangling_res (dict): Diccionario retornado por la tarea data_wrangling, con:
                - clean_data_path (str): Ruta en S3 del archivo limpio.
                - cat_cols (list): Lista con nombres de las columnas categóricas.
                - num_cols (list): Lista con nombres de las columnas numéricas.
                - target (list): Lista con el nombre de la columna objetivo.

        Returns:
            A COMPLETAR
        """
        import awswrangler as wr
        import numpy as np
        import pandas as pd
        import logging
        from sklearn.model_selection import train_test_split

        #-- 0. Datos de tarea anterior
        clean_data_path = data_wrangling_res["clean_data_path"]
        cat_cols = data_wrangling_res["cat_cols"]
        num_cols = data_wrangling_res["num_cols"]
        target = data_wrangling_res["target"]

        #-- 1. Lectura de datos limpios
        logging.info("Cargando datos...")
        try:
            clean_df = wr.s3.read_csv(clean_data_path)
        except Exception as e:
            raise RuntimeError(f"Error al leer el archivo de datos limpios de S3 en {clean_data_path}. Detalles: {e}")

        #-- 2. Split
        logging.info("Realizando split...")
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                clean_df[cat_cols + num_cols],
                clean_df[target],
                test_size=0.3,
                random_state=42,
                stratify=clean_df[cat_cols]
            )
        except Exception as e:
            raise RuntimeError(f"Error al realizar el split de datos. Detalles: {e}")

        ##### SE DEBE CONTINUAR CON EL REENTRENAMIENTO
        ### - Levantar pipeline "champion" de MLFlow
        ### - Hacer fit con los nuevos datos
        ### - Comparar métricas entre el modelo reentrenado y el champion (las métricas del champion están en MLFlow).
        ### - Si el reentrenado es mejor, guardarlo como nueva versión del champion.

        # Ver: https://github.com/alexisbarnique/amq2-service-ml/blob/example_implementation/airflow/dags/retrain_the_model.py

    
    get_raw_data_res = get_raw_data(
        get_variable("dem_csv_url"),
        get_variable("temp_csv_url"),
        get_variable("dem_path"),
        get_variable("temp_path")
    )
    data_wrangling_res = data_wrangling(
        get_raw_data_res,
        get_variable("clean_data_path")
    )
    retrain_res = retrain(
        data_wrangling_res
    )

dag = process_etl_electrical_demand()