FROM python:3.12-slim

# Crear directorio de trabajo
WORKDIR /app

# Copiar solo los requerimientos primero (para aprovechar cache de Docker)
COPY dockerfiles/fastapi/requirements.txt requirements.txt
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copiar la aplicación FastAPI
COPY dockerfiles/fastapi/app.py app.py

# Exponer el puerto del servicio 
EXPOSE 8800

# Comando de inicio con uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8800"]
