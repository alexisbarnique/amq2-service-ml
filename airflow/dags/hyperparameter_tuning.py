import datetime

from airflow.decorators import dag, task

markdown_text = """
### Optimización de hiperparámetros con Optuna

Realiza búsqueda de hiperparámetros utilizando Optuna para el modelo de demanda eléctrica.
El mejor modelo encontrado se registra automáticamente como 'champion' en MLflow.
"""

default_args = {
    'owner': "Alexis, Bárbara, Brian, Daniel y Gabriela",
    'depends_on_past': False,
    'schedule_interval': None,
    'retries': 0,
    'dagrun_timeout': datetime.timedelta(minutes=60)
}

@dag(
    dag_id="hyperparameter_tuning",
    description="Optimización de hiperparámetros con Optuna para el modelo de demanda eléctrica.",
    doc_md=markdown_text,
    tags=["Optuna", "Hyperparameter", "Tuning"],
    default_args=default_args,
    catchup=False,
)
def hyperparameter_tuning():

    def get_variable(key):
        """Obtiene el valor de una variable de Airflow."""
        from airflow.models import Variable
        value = Variable.get(key)
        if not value:
            raise ValueError(f"La variable '{key}' está vacía o no existe.")
        return value

    @task.virtualenv(
        task_id="get_raw_data",
        requirements=["awswrangler==3.6.0", "pandas"],
        system_site_packages=True
    )
    def get_raw_data(dem_csv_url, temp_csv_url, dem_path, temp_path):
        """Descarga los archivos CSV de demanda eléctrica y temperatura desde Github y los sube al bucket S3."""
        import awswrangler as wr
        import pandas as pd
        import logging

        logging.info(f"Descargando datos de demanda desde {dem_csv_url}")
        logging.info(f"Descargando datos de temperatura desde {temp_csv_url}")

        try:
            # Use pandas to read from HTTP URLs
            dem_df = pd.read_csv(dem_csv_url)
            temp_df = pd.read_csv(temp_csv_url)
        except Exception as e:
            raise RuntimeError(f"Error al leer archivos desde GitHub: {e}")

        try:
            # Use awswrangler to write to S3
            wr.s3.to_csv(df=dem_df, path=dem_path, index=False)
            wr.s3.to_csv(df=temp_df, path=temp_path, index=False)
        except Exception as e:
            raise RuntimeError(f"Error al subir archivos a S3: {e}")

        logging.info("Archivos descargados y subidos a S3 exitosamente.")
        return {"dem_path": dem_path, "temp_path": temp_path}

    @task.virtualenv(
        task_id="data_wrangling",
        requirements=["awswrangler"],
        system_site_packages=True,
    )
    def data_wrangling(get_raw_data_res, clean_data_path):
        """Preprocesa y combina los datos de demanda y temperatura."""
        import awswrangler as wr
        import pandas as pd
        import logging

        dem_path = get_raw_data_res["dem_path"]
        temp_path = get_raw_data_res["temp_path"]

        logging.info("Leyendo datos desde S3...")
        try:
            dem_df = wr.s3.read_csv(dem_path)
            temp_df = wr.s3.read_csv(temp_path)
        except Exception as e:
            raise RuntimeError(f"Error al leer datos desde S3: {e}")

        logging.info("Preprocesando datos...")
        try:
            dem_df["fecha"] = pd.to_datetime(dem_df["fecha"])
            dem_df = dem_df[dem_df["anio_cal"] >= 2019].copy()

            temp_df = temp_df[temp_df["fecha"] >= "2019-01-01"].copy()
            temp_df["fecha"] = pd.to_datetime(temp_df["fecha"])

            df_full = pd.merge(
                dem_df, temp_df, left_on=["fecha", "rge_nemo"], right_on=["fecha", "region"]
            )

            df_mensual = (
                df_full.groupby(["mes", "age_nemo", "tipo_dia"])
                .agg({"dem_dia": "mean", "tmed": "mean"})
                .reset_index()
            )

            cat_cols = ["mes", "age_nemo", "tipo_dia"]
            num_cols = ["tmed"]
            target = ["dem_dia"]

            clean_data = df_mensual[cat_cols + num_cols + target]

        except Exception as e:
            raise RuntimeError(f"Error al procesar datos: {e}")

        logging.info("Subiendo datos limpios a S3...")
        try:
            wr.s3.to_csv(df=clean_data, path=clean_data_path, index=False)
        except Exception as e:
            raise RuntimeError(f"Error al subir archivo a S3: {e}")

        logging.info("Procesamiento completado.")
        return {"clean_data_path": clean_data_path, "cat_cols": cat_cols, "num_cols": num_cols, "target": target}

    @task.virtualenv(
        task_id="optimize_and_register",
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
    def optimize_and_register(data_wrangling_res):
        """Realiza búsqueda de hiperparámetros con Optuna y registra el mejor modelo."""
        import awswrangler as wr
        import logging
        import datetime
        import numpy as np
        import pandas as pd

        from sklearn.model_selection import train_test_split
        from sklearn.base import BaseEstimator, TransformerMixin
        from sklearn.pipeline import Pipeline
        from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

        from xgboost import XGBRegressor
        import optuna
        import mlflow
        import mlflow.sklearn
        from mlflow.models import infer_signature

        clean_data_path = data_wrangling_res["clean_data_path"]
        cat_cols = data_wrangling_res["cat_cols"]
        num_cols = data_wrangling_res["num_cols"]
        target = data_wrangling_res["target"]

        SEED = 42
        np.random.seed(SEED)

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
                df_te = pd.concat([X[['dist_tipodia']], y.rename('dem_dia')], axis=1)
                self.mapping_ = df_te.groupby('dist_tipodia')['dem_dia'].mean()
                self.global_mean_ = float(y.mean())
                return self

            def transform(self, X):
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

        logging.info("Realizando splits train/test/validation...")
        X = clean_df[cat_cols + num_cols]
        y = clean_df[target].iloc[:, 0]
        
        stratify_col = clean_df["mes"]

        X_train_raw, X_test_raw, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=SEED, stratify=stratify_col
        )

        X_tr, X_val, y_tr, y_val = train_test_split(
            X_train_raw, y_train, test_size=0.25, random_state=SEED,
            stratify=X_train_raw["mes"]
        )

        mlflow.set_tracking_uri("http://mlflow:5000")
        experiment = mlflow.set_experiment("Demanda Distribuidores")

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
            study.optimize(objective, n_trials=250)

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

    dem_csv_url = get_variable("dem_csv_url")
    temp_csv_url = get_variable("temp_csv_url")
    dem_path = get_variable("dem_path")
    temp_path = get_variable("temp_path")
    clean_data_path = get_variable("clean_data_path")

    # Llamamos a las tareas

    raw_data_result = get_raw_data(dem_csv_url, temp_csv_url, dem_path, temp_path)
    wrangling_result = data_wrangling(raw_data_result, clean_data_path)
    optimize_and_register(wrangling_result)

dag = hyperparameter_tuning()
