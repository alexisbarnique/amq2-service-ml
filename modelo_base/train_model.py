import pandas as pd
import numpy as np
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
import joblib

# --- Lectura de datos
dem_df = pd.read_csv('dem_20110401_20251022.csv')
dem_df['fecha'] = pd.to_datetime(dem_df['fecha'])
dem_df = dem_df.loc[dem_df['anio_cal'] >= 2021]

temp_df = pd.read_csv('temperaturas.csv')
temp_df = temp_df.loc[temp_df['fecha'] >= '2021-01-01']
temp_df['fecha'] = pd.to_datetime(temp_df['fecha'])

# --- Merge
df_full = pd.merge(dem_df, temp_df, left_on=['fecha','rge_nemo'], right_on=['fecha','region'])
df_full = df_full.rename(columns={'anio_cal':'year'})

cat_cols = ['mes','age_nemo','tipo_dia']
num_cols = ['year','tmed']
target = ['dem_dia']
df = df_full[cat_cols+num_cols+target].dropna()

df_mensual = df.groupby(['year']+cat_cols).mean().round(2).reset_index()
df_mensual['tmed2'] = df_mensual['tmed']**2
num_cols = ['tmed','tmed2']

# --- Split
X_train, X_test, y_train, y_test = train_test_split(
    df_mensual[cat_cols+num_cols],
    df_mensual[target],
    test_size=0.3,
    random_state=42,
    stratify=df_mensual[cat_cols]
)

# --- Codificación (ejemplo simplificado)
X_train['mes_sin'] = np.sin(2*np.pi*X_train['mes']/12)
X_train['mes_cos'] = np.cos(2*np.pi*X_train['mes']/12)
X_train['dist_tipodia'] = X_train['age_nemo'].astype(str)+'_'+X_train['tipo_dia'].astype(str)
encoding = pd.concat([X_train,y_train],axis=1).groupby('dist_tipodia')['dem_dia'].mean()
X_train['dist_tipodia_te'] = X_train['dist_tipodia'].map(encoding)
X_train_coded = X_train.drop(columns=['age_nemo','tipo_dia','dist_tipodia'])

X_test['mes_sin'] = np.sin(2*np.pi*X_test['mes']/12)
X_test['mes_cos'] = np.cos(2*np.pi*X_test['mes']/12)
X_test['dist_tipodia'] = X_test['age_nemo'].astype(str)+'_'+X_test['tipo_dia'].astype(str)
X_test['dist_tipodia_te'] = X_test['dist_tipodia'].map(encoding)
X_test['dist_tipodia_te'].fillna(y_train['dem_dia'].mean(), inplace=True)
X_test_coded = X_test.drop(columns=['age_nemo','tipo_dia','dist_tipodia'])

# --- Entrenamiento
best_model = XGBRegressor(
    booster='gbtree',
    objective='reg:squarederror',
    eval_metric='mape',
    verbosity=0
)
best_model.fit(X_train_coded, y_train)

# --- Evaluación
y_pred = best_model.predict(X_test_coded)
mae = mean_absolute_error(y_test, y_pred)
mape = mean_absolute_percentage_error(y_test, y_pred)
print(f"MAE: {mae:.2f}, MAPE: {mape:.2%}")

# Guardar modelo y encoding
joblib.dump(best_model, "best_model.pkl")
joblib.dump(encoding.to_dict(), "encoding.pkl")

