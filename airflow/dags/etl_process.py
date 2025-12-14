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
        task_id="optimize_hyperparameters",
        requirements=[
            "awswrangler",
            "scikit-learn",
            "mlflow",
            "xgboost",
            "optuna",
            "optuna-integration",
        ],
        system_site_packages=True,
    )
    def optimize_hyperparameters(data_wrangling_res):
        """
        Realiza búsqueda de hiperparámetros con Optuna y registra el mejor modelo.
        """
        import awswrangler as wr
        import logging
        import datetime
        import numpy as np

        from sklearn.model_selection import train_test_split
        from sklearn.base import BaseEstimator, TransformerMixin
        from sklearn.pipeline import Pipeline
        from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

        from xgboost import XGBRegressor
        import optuna
        import mlflow
        import mlflow.sklearn
        from mlflow.models import infer_signature

        # Datos generados por la tarea de data_wrangling
        clean_data_path = data_wrangling_res["clean_data_path"]
        cat_cols = data_wrangling_res["cat_cols"]
        num_cols = data_wrangling_res["num_cols"]
        target = data_wrangling_res["target"]

        SEED = 42
        np.random.seed(SEED)

        # Leer datos limpios desde S3
        logging.info("Cargando datos limpios desde S3...")
        clean_df = wr.s3.read_csv(clean_data_path)

        # Preprocesador personalizado
        class DemandPreprocessor(BaseEstimator, TransformerMixin):
            def __init__(self, period=12):
                self.period = period
                self.mapping_ = None
                self.global_mean_ = None

            def fit(self, X, y=None):
                X = X.copy()
                X['dist_tipodia'] = X['age_nemo'].astype(str) + '_' + X['tipo_dia'].astype(str)
                if y is None:
                    raise ValueError("Target y es requerido para target mean encoding.")
                import pandas as pd
                df_te = pd.concat([X[['dist_tipodia']], y.rename('dem_dia')], axis=1)
                self.mapping_ = df_te.groupby('dist_tipodia')['dem_dia'].mean()
                self.global_mean_ = float(y.mean())
                return self

            def transform(self, X):
                import pandas as pd
                import numpy as np
                X = X.copy()
                X['mes_sin'] = np.sin(2 * np.pi * X['mes'] / self.period)
                X['mes_cos'] = np.cos(2 * np.pi * X['mes'] / self.period)
                X['dist_tipodia'] = X['age_nemo'].astype(str) + '_' + X['tipo_dia'].astype(str)
                X['dist_tipodia_te'] = X['dist_tipodia'].map(self.mapping_)
                X['dist_tipodia_te'] = X['dist_tipodia_te'].fillna(self.global_mean_)
                X['tmed2'] = X['tmed'] ** 2
                X = X.drop(columns=['age_nemo', 'tipo_dia', 'dist_tipodia', 'mes'])
                ordered_cols = ['mes_sin', 'mes_cos', 'tmed', 'tmed2', 'dist_tipodia_te']
                return X[ordered_cols]

        # Split train/test estratificado
        logging.info("Realizando splits train/test/validation...")
        X = clean_df[cat_cols + num_cols]
        y = clean_df[target].iloc[:, 0]
        strata = clean_df[cat_cols]

        X_train_raw, X_test_raw, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=SEED, stratify=strata
        )

        X_tr, X_val, y_tr, y_val = train_test_split(
            X_train_raw, y_train, test_size=0.25, random_state=SEED,
            stratify=X_train_raw[cat_cols]
        )

        # Configuración de MLflow
        mlflow.set_tracking_uri("http://mlflow:5000")
        experiment = mlflow.set_experiment("Demanda Distribuidores")

        # Función para construir pipeline
        def build_pipeline(trial=None):
            if trial is not None:
                params = {
                    "n_estimators": trial.suggest_int("n_estimators", 500, 1200),
                    "max_depth": trial.suggest_int("max_depth", 5, 10),
                    "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
                    "subsample": trial.suggest_float("subsample", 0.7, 1.0),
                    "colsample_bytree": trial.suggest_float("colsample_bytree", 0.8, 0.9),
                    "min_child_weight": trial.suggest_float("min_child_weight", 1.0, 8.0),
                    "gamma": trial.suggest_float("gamma", 0.0, 1.0),
                    "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 1.0),
                    "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 1.5),
                }
            else:
                params = {
                    "n_estimators": 500,
                    "max_depth": 6,
                    "learning_rate": 0.05,
                    "subsample": 0.8,
                    "colsample_bytree": 0.8,
                    "min_child_weight": 1.0,
                    "gamma": 0.0,
                    "reg_alpha": 0.0,
                    "reg_lambda": 1.0,
                }

            model = XGBRegressor(
                booster='gbtree',
                objective='reg:squarederror',
                eval_metric='mae',
                random_state=SEED,
                **params
            )
            pipeline = Pipeline(steps=[
                ("pre", DemandPreprocessor(period=12)),
                ("model", model)
            ])
            return pipeline, params

        # Función objetivo de Optuna
        def objective(trial):
            pipeline, params = build_pipeline(trial)
            with mlflow.start_run(run_name=f"trial_{trial.number}", nested=True):
                mlflow.log_params(params)
                pipeline.fit(X_tr, y_tr)
                y_pred_val = pipeline.predict(X_val)
                mae_val = mean_absolute_error(y_val, y_pred_val)
                mape_val = mean_absolute_percentage_error(y_val, y_pred_val)
                mlflow.log_metric("mae_val", float(mae_val))
                mlflow.log_metric("mape_val", float(mape_val))
                trial.set_user_attr("mae_val", float(mae_val))
                trial.set_user_attr("mape_val", float(mape_val))
                return mae_val

        # Búsqueda de hiperparámetros
        logging.info("Iniciando búsqueda de hiperparámetros con Optuna...")
        with mlflow.start_run(
            run_name="hyperparam_search_" + datetime.datetime.today().strftime('%Y-%m-%d_%H:%M:%S'),
            experiment_id=experiment.experiment_id
        ):
            mlflow.set_tags({
                "stage": "hyperparam_search",
                "framework": "xgboost+sklearn",
                "optimizer": "optuna",
                "metric_objective": "mae",
            })

            study = optuna.create_study(direction="minimize", study_name="demanda_distribuidores")
            study.sampler = optuna.samplers.TPESampler(seed=SEED)
            study.pruner = optuna.pruners.MedianPruner(n_warmup_steps=10)
            study.optimize(objective, n_trials=20)

            best_trial = study.best_trial
            mlflow.log_metric("best_value_mae_val", float(best_trial.value))
            mlflow.log_params({
                "best_trial_number": best_trial.number,
                "n_trials": len(study.trials),
            })
            mlflow.log_dict(
                {
                    "best_trial_number": best_trial.number,
                    "best_params": best_trial.params,
                    "best_user_attrs": best_trial.user_attrs,
                    "n_trials": len(study.trials),
                },
                artifact_file="study_summary.json"
            )
            logging.info(f"Mejor MAE (valid): {best_trial.value:.4f}")
            logging.info(f"Mejores params: {best_trial.params}")

        # Entrenar modelo final con mejores hiperparámetros
        logging.info("Entrenando modelo final con mejores hiperparámetros...")
        best_params = best_trial.params
        best_pipeline, _ = build_pipeline(trial=None)
        best_pipeline.set_params(**{f"model__{k}": v for k, v in best_params.items()})

        with mlflow.start_run(
            run_name="best_model_" + datetime.datetime.today().strftime('%Y-%m-%d_%H:%M:%S'),
            experiment_id=experiment.experiment_id
        ):
            mlflow.set_tags({
                "stage": "training_final",
                "framework": "xgboost+sklearn",
                "encoding": "cyclic_month + target_mean(age_nemo,tipo_dia)",
            })
            mlflow.log_params(best_params)

            best_pipeline.fit(X_train_raw, y_train)

            y_pred_test = best_pipeline.predict(X_test_raw)
            mae_test = mean_absolute_error(y_test, y_pred_test)
            mape_test = mean_absolute_percentage_error(y_test, y_pred_test)

            mlflow.log_metric("mae_test", float(mae_test))
            mlflow.log_metric("mape_test", float(mape_test))

            import pandas as pd
            input_example = pd.DataFrame(X_train_raw).head(5)
            signature = infer_signature(input_example, best_pipeline.predict(input_example))

            info = mlflow.sklearn.log_model(
                sk_model=best_pipeline,
                artifact_path="best_model",
                signature=signature,
                input_example=input_example
            )

            model_uri = info.model_uri
            run_id = info.run_id

            logging.info(f"Best model logueado. MAE test: {mae_test:.4f} | MAPE test: {mape_test:.4f}")

        # Registrar modelo
        logging.info("Registrando modelo en MLflow Model Registry...")
        client = mlflow.MlflowClient()
        registered_name = "demanda_distribuidores"
        desc = "XGB + meses con encoding cíclico + target mean para distribuidor y tipo de día"
        alias = "champion"

        try:
            client.create_registered_model(name=registered_name, description=desc)
        except:
            pass

        tags = {**best_params, "mae_test": str(mae_test), "mape_test": str(mape_test)}
        result = client.create_model_version(
            name=registered_name,
            source=model_uri,
            run_id=run_id,
            tags=tags
        )
        client.set_registered_model_alias(registered_name, alias, result.version)
        logging.info(f"Registrado '{registered_name}' v{result.version} como '{alias}'.")

        return {"model_version": result.version, "mae_test": mae_test, "mape_test": mape_test}


    @task.virtualenv(
        task_id="train",
        requirements=[
            "awswrangler",
            "scikit-learn",
            "mlflow",
            "xgboost",
        ],
        system_site_packages=True,
    )
    def train(data_wrangling_res):
        """
        Reentrena el modelo de demanda y actualiza el champion si el nuevo modelo
        mejora el MAE en el conjunto de test actual.
        """
        import awswrangler as wr
        import logging
        import datetime

        from sklearn.model_selection import train_test_split
        from sklearn.base import clone
        from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

        import mlflow
        import mlflow.sklearn
        from mlflow.models import infer_signature

        # Datos generados por la tarea de data_wrangling
        clean_data_path = data_wrangling_res["clean_data_path"]
        cat_cols = data_wrangling_res["cat_cols"]
        num_cols = data_wrangling_res["num_cols"]
        target = data_wrangling_res["target"]  # lista con un solo nombre de columna

        # Leer datos limpios desde S3
        logging.info("Cargando datos limpios desde S3...")
        try:
            clean_df = wr.s3.read_csv(clean_data_path)
        except Exception as e:
            raise RuntimeError(
                f"Error al leer datos limpios de S3 en {clean_data_path}. Detalles: {e}"
            )

        # Split train/test estratificado por columnas categóricas
        logging.info("Realizando split train/test...")
        try:
            X = clean_df[cat_cols + num_cols]
            # target es una lista con un solo elemento → tomamos la serie 1D
            y = clean_df[target].iloc[:, 0]
            strata = clean_df[cat_cols]

            X_train, X_test, y_train, y_test = train_test_split(
                X,
                y,
                test_size=0.3,
                random_state=42,
                stratify=strata,
            )
        except Exception as e:
            raise RuntimeError(f"Error al realizar el split de datos. Detalles: {e}")

        # Guardar splits en S3 para trazabilidad
        logging.info("Guardando splits en S3...")
        try:
            wr.s3.to_csv(
                df=X_train,
                path="s3://data/clean/X_train_coded.csv",
                index=False,
            )
            wr.s3.to_csv(
                df=X_test,
                path="s3://data/clean/X_test_coded.csv",
                index=False,
            )
            wr.s3.to_csv(
                df=y_train.to_frame(name=target[0]),
                path="s3://data/clean/y_train.csv",
                index=False,
            )
            wr.s3.to_csv(
                df=y_test.to_frame(name=target[0]),
                path="s3://data/clean/y_test.csv",
                index=False,
            )
        except Exception as e:
            raise RuntimeError(f"Error al guardar los splits en S3: {e}")

        # Configuración de MLflow (tracking server del docker-compose)
        mlflow.set_tracking_uri("http://mlflow:5000")
        experiment = mlflow.set_experiment("Demanda Distribuidores")

        client = mlflow.MlflowClient()
        model_name = "demanda_distribuidores"

        # Cargar modelo champion desde el Model Registry
        logging.info("Cargando modelo 'champion' desde MLflow Model Registry...")
        champion_version = client.get_model_version_by_alias(model_name, "champion")
        champion_model = mlflow.sklearn.load_model(champion_version.source)

        # Evaluar champion en el test actual
        y_pred_champion = champion_model.predict(X_test)
        mae_champion = mean_absolute_error(y_test, y_pred_champion)
        mape_champion = mean_absolute_percentage_error(y_test, y_pred_champion)

        # Clonar pipeline champion para usarlo como challenger
        logging.info("Entrenando modelo 'challenger' a partir del champion...")
        challenger_model = clone(champion_model)

        run_name = "train_challenger_" + datetime.datetime.today().strftime(
            "%Y-%m-%d_%H:%M:%S"
        )

        with mlflow.start_run(
            run_name=run_name,
            experiment_id=experiment.experiment_id,
            tags={"stage": "train", "model_name": model_name},
            log_system_metrics=True,
        ):
            # Entrenar challenger con los datos nuevos
            challenger_model.fit(X_train, y_train)

            # Evaluar challenger en el mismo test
            y_pred_challenger = challenger_model.predict(X_test)
            mae_challenger = mean_absolute_error(y_test, y_pred_challenger)
            mape_challenger = mean_absolute_percentage_error(y_test, y_pred_challenger)

            # Loguear métricas de champion vs challenger
            mlflow.log_metric("mae_champion", float(mae_champion))
            mlflow.log_metric("mape_champion", float(mape_champion))
            mlflow.log_metric("mae_challenger", float(mae_challenger))
            mlflow.log_metric("mape_challenger", float(mape_challenger))

            # Loguear parámetros del modelo challenger (para inspección en MLflow)
            try:
                params = challenger_model.get_params()
            except Exception:
                params = {}
            params["model"] = type(challenger_model).__name__
            mlflow.log_params(params)

            # Guardar el modelo challenger como artefacto de MLflow
            artifact_path = "trained_model"
            input_example = X_train.head(5)
            signature = infer_signature(
                input_example, challenger_model.predict(input_example)
            )

            info = mlflow.sklearn.log_model(
                sk_model=challenger_model,
                artifact_path=artifact_path,
                signature=signature,
                input_example=input_example,
            )

            model_uri = info.model_uri
            run_id = info.run_id

            # Comparar y, si el challenger es mejor, registrarlo como nuevo champion
            logging.info(
                f"MAE champion = {mae_champion:.3f} | MAE challenger = {mae_challenger:.3f}"
            )

            if mae_challenger < mae_champion:
                logging.info(
                    "El challenger mejora al champion: registrando nueva versión como 'champion'..."
                )

                tags = {
                    "mae_test": float(mae_challenger),
                    "mape_test": float(mape_challenger),
                    "model": type(challenger_model).__name__,
                }

                result = client.create_model_version(
                    name=model_name,
                    source=model_uri,
                    run_id=run_id,
                    tags=tags,
                )

                # Actualizar alias 'champion' a la nueva versión
                client.set_registered_model_alias(model_name, "champion", result.version)
                mlflow.log_param("winner", "challenger")
            else:
                logging.info(
                    "El champion actual sigue siendo mejor: se mantiene la versión actual."
                )
                mlflow.log_param("winner", "champion")

        # Métricas básicas para inspeccionar en XCom
        return {
            "mae_champion": float(mae_champion),
            "mae_challenger": float(mae_challenger),
        }

    # Get Airflow variables
    dem_csv_url = get_variable("dem_csv_url")
    temp_csv_url = get_variable("temp_csv_url")
    dem_path = get_variable("dem_path")
    temp_path = get_variable("temp_path")
    clean_data_path = get_variable("clean_data_path")

    # Invoke tasks and define dependencies for quick retraining workflow
    get_raw_data_result = get_raw_data(dem_csv_url, temp_csv_url, dem_path, temp_path)
    data_wrangling_result = data_wrangling(get_raw_data_result, clean_data_path)
    train_result = train(data_wrangling_result)

dag = process_etl_electrical_demand()