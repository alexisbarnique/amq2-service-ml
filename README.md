# Modelo de Demanda Eléctrica ⚡

El modelo implementado en producción tiene como objetivo estimar la demanda eléctrica diaria de cada distribuidor de la República Argentina.

Las principales características que influyen en el consumo eléctrico diario son la temperatura y el tipo de día (hábil, semi hábil o no hábil). Por lo tanto, estos son los datos de entrada que se utilizan para realizar la predicción, además de la distribuidora.

Para el entrenamiento del modelo, se cuenta con datos de demanda diaria de todas las distribuidoras (son más de 70) y con los datos de temperatura media diaria de las distintas regiones del país. Luego, se combinan utilizando la región y la fecha.

Previo al entrenamiento, se toma la demanda media de cada distribuidora para cada mes de cada año y tipo de día, ya que el objetivo último de este modelo es realizar una estimación para obtener la demanda característica de cada tipo de día de los distintos meses del año, para todas las distribuidoras.

## Instalación

1.  Para poder levantar todos los servicios, primero instala [Docker](https://docs.docker.com/engine/install/) en tu computadora (o en el servidor que desees usar).
2.  Clona este repositorio.
3.  Crea las carpetas `airflow/config`, `airflow/dags`, `airflow/logs`, `airflow/plugins`, `airflow/logs`.
4.  Si estás en Linux o MacOS, en el archivo `.env`, reemplaza `AIRFLOW_UID` por el de tu usuario o alguno que consideres oportuno (para encontrar el UID, usa el comando `id -u <username>`). De lo contrario, Airflow dejará sus carpetas internas como root y no podrás subir DAGs (en `airflow/dags`) o plugins, etc.
5.  En la carpeta raíz de este repositorio, ejecuta:

``` bash
docker compose --profile all up
```

6.  Una vez que todos los servicios estén funcionando (verifica con el comando `docker ps -a` que todos los servicios estén healthy o revisa en Docker Desktop), podrás acceder a los diferentes servicios mediante:
    -   Apache Airflow: http://localhost:8080
    -   MLflow: http://localhost:5001
    -   MinIO: http://localhost:9001 (ventana de administración de Buckets)
    -   API: http://localhost:8800/
    -   Documentación de la API: http://localhost:8800/docs

Si estás usando un servidor externo a tu computadora de trabajo, reemplaza `localhost` por su IP (puede ser una privada si tu servidor está en tu LAN o una IP pública si no; revisa firewalls u otras reglas que eviten las conexiones).

Todos los puertos u otras configuraciones se pueden modificar en el archivo `.env`. Se invita a jugar y romper para aprender; siempre puedes volver a clonar este repositorio.

## Registro inicial del modelo

Para poder usar el modelo, es necesario hacer un registro inicial en MLFlow. Para esto, se debe ejecutar en su totalidad el notebook `modelo_base/experimento_modelo.ipynb`.

En caso de no hacer esto, el servicio que realiza las predicciones utilizará un modelo de backup cargado en el bucket s3 cuando se compilan los contenedores.

## Uso de app

Se desarrolló una app de streamlit para utilizar el servicio mediante una interfaz gráfica. Para acceder, ingresar a:

-   http://localhost:8501/

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