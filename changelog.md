## Registro de cambios

Se agrega esta sección para hacer comentarios sobre cambios realizados.

-   2025-11-15
    -   Se modificó el AIRFLOW_UID en el archivo .env al valor 1000. Entiendemos que esto lo podemos dejar todo igual.
    -   En docker-compose.yaml Daniel tuvo que hacer algunos cambios para que funcione en Linux. No debería afectar al resto.
    -   Se sube el notebook del modelo base con los datos necesarios en csv. Realizamos algunas simplificaciones respecto al original.
-   2025-11-16
    -   Creación de primera DAG con dos tareas: get_raw_data y data_wrangling. Daniel: No pude hacer que funcionen, pero tengo un problema general para ejecutar dags, por lo que habría que probarlas bien.
    -   Cambio en docker-compose: ejemplos seteados en false para que no cargue las dags de ejemplo (eran 76 y ensuciaban mucho)
-   2025-11-17
    -   Ajustes de dag: se eliminaron dependencias innecesarias en entornos virtuales.
    -   Ajustes docker-compose:
        -   Se reemplazó el caracter `:` en las rutas de los logs, para compatibilizar con NTFS.
        -   Se agregaron volumes para temporales de uv, por problemas de permisos.
        -   Se agregó AIRFLOW__API__SECRET_KEY.
-   2025-11-17 parte 2
    -   Nueva tarea para split y encoding.
    -   Implementación de variables a través del uso de "Variables" de Airflow. Se creo un archivo /airflow/config/variables.json 
    para el manejo de variables (se evita harcodear)
    -   Documentación de tareas con docstrings.
-   2025-11-30  FASTAPI
    - `modelo_base/main.py`: adaptado para exponer funciones de entrenamiento/predicción vía API FastAPI.
    - `modelo_base/train_model.py`: refactorizado para integrarse con endpoints de FastAPI.
    - `README.md`: actualizado con instrucciones para correr el servicio FastAPI y ejemplos de uso.
    - Ajustes en notebooks (`demanda_distribuidor.ipynb`) para reflejar la nueva forma de consumir el modelo vía API.
    - `dockerfiles/fastapi/Dockerfile`: imagen base para servicio FastAPI.
    - `dockerfiles/fastapi/app.py`: aplicación FastAPI inicial con endpoints de prueba.
    - `dockerfiles/fastapi/requirements.txt`: dependencias específicas de FastAPI.
    - Configuración en `docker-compose.yaml` para levantar el servicio FastAPI junto con Airflow, MLflow y Postgres.
-   2025-12-01  DOCKER / STREAMLIT / FASTAPI
    - `docker-compose.yaml`: actualizado para incluir servicio de Streamlit junto al backend FastAPI.
    - `dockerfiles/fastapi/Dockerfile`: modificado para copiar el modelo `best_model.pkl` y asegurar dependencias de ML.
    - `dockerfiles/fastapi/requirements.txt`: actualizado con librerías adicionales (`joblib`, `numpy`, `xgboost`, `pydantic`).
    - `dockerfiles/streamlit/Dockerfile`: nueva imagen base para frontend Streamlit.
    - `dockerfiles/streamlit/frontend.py`: nueva interfaz Streamlit para interactuar con el backend FastAPI.
    - `dockerfiles/streamlit/requirements.txt`: dependencias específicas para Streamlit (`streamlit`, `requests`).
- 2025-12-05:
    - **Notebook `modelo_base/experimento_modelo.ipynb`**: búsqueda de hiperparámetros y registro del modelo (con los mejores hiperparámetros) en MLFlow. El preprocesamiento (encodings) se incluyó con el modelo en un objeto `pipeline`, de esta forma se registra todo en MLFlow y no es necesario codificar y decodificar a nivel de API.
    - **pipeline_backup**: se guardaron todos los archivos que se registran en MLFlow en el repo. Al momento de compilar los contenedores, estos archivos se guardan en el bucket s3. De esta forma, se asegura que siempre se pueda cargar un modelo (en caso que aún no se haya corrido el notebook del experimento). Tanto la api como la app de stremlit tiene un try/except para tomar primero de MLflow y si no puede tomar este modelo de backup.
    - **fastapi**: lectura del modelo registrado en MLFlow, con fallback para leer del modelo de backup.
    - **streamlit**: se lee el pipeline para levantar el preprocesador. En esa clase, se cuenta con el mapeo de los nombres de distribuidores, que se utiliza para generar una lista desplegable para poder elegir los solo los valores válidos. Además, se incluyeron diccionarios para el mes y el tipo de día, para elegir valores string de una lista desplegable. También se ajustó el formato de la predicción (redondeo y unidad de energía.)
    - **airflow**: se eliminó parte de la dag que hacía el encoding, ya que no es necesaria por haber incluido el encoding en el pipeline. **QUEDA PENDIENTE COMPLETAR ESTA DAG CON REENTRENAMIENTO, ver detalles en el código de la dag.**
    - **README**: se eliminó la mayor parte del readme original y se hizo una descripción del modelo implementado, con instrucciones básicas de uso.
    - **limpieza de archivos**: eliminación de archivos que no se usaban más.
    - **Proximos pasos**: 
        - Terminar dag de airflow. Este sería el punto más importante para cumplir con los requisitos del TP.
        - fastapi: se pueden agregar validaciones (por ejemplo, ver que el age_nemo sea válido), generar un código de warning si se está usando el modelo backup y mostrarlo en la app streamlit, etc.
        - predicción por lote: se podría generar un nuevo endpoint (y un botón asociado a este en la app de streamlit) para predecir por lote. En la app de streamlit, podría armarse un data frame con: todos los meses con todos los tipos de día, todos los distribuidores para cada mes (aprox 3x12x76 registros) y la temperatura media histórica para cada registro (se debería hacer join por región y mes). Luego pasarle este dataframe al modelo para que devuelva todas las predicciones y mostrarlas en la app. Así, se podría estimar la demanda de cada distribuidor para cada mes del año para los tres tipos de día (multiplicando por la cantidad de días de cada tipo de día en cada mes, se podría obtener las demandas mensuales de todas las distribuidoras, esto es un problema real a resolver).
