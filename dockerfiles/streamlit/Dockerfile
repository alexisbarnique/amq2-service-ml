FROM python:3.12-slim

WORKDIR /app

# Copiamos el frontend y los requerimientos
COPY frontend.py .
COPY requirements.txt requirements.txt

# Instalamos dependencias
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Exponemos el puerto de Streamlit
EXPOSE 8501

# Comando de inicio
CMD ["streamlit", "run", "frontend.py", "--server.port=8501", "--server.address=0.0.0.0"]
