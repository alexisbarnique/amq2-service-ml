import os
import streamlit as st
import requests

# Base URL del backend
API_URL = os.getenv("API_URL", "http://fastapi:8800")

st.title("Estimación de Demanda Eléctrica ⚡")

# Inputs de usuario
feature1 = st.number_input("Mes", value=1, step=1, format="%d")  # entero
feature2 = st.text_input("age_nemo", value="")                   # string
feature3 = st.text_input("Tipo", value="")                       # string
feature4 = st.number_input("Temperatura media", value=0.0)       # float


if st.button("Predecir"):
    # Llamada a la API FastAPI
    response = requests.post(
        f"{API_URL}/predict",  # Ajustá el puerto según tu docker-compose
        json={"mes": feature1, "age_nemo": feature2, "tipo_dia": feature3, "tmed": feature4}
    )
    if response.status_code == 200:
        result = response.json()
        st.success(f"Predicción de demanda: {result['prediction']}")
    else:
        st.error("Error al consultar la API")
