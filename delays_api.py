from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi import HTTPException
import os
import requests
import httpx
import numpy as np
from pydantic import BaseModel
import pickle
import pandas as pd
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.calibration import LabelEncoder
import xgboost as xgb


# Création de l'application FastAPI
app = FastAPI()



# Définition des structures des données d'entrée
class Flight(BaseModel):
    MONTH: int
    DAY_OF_MONTH: int
    CARRIER_NAME: str
    CRS_DEP_TIME: int
    OP_UNIQUE_CARRIER: str
    OP_CARRIER_FL_NUM: int
    ORIGIN: str
    DEST: str
    CRS_ARR_TIME: int
    CRS_ELAPSED_TIME: float
    DISTANCE: float





# route pour un message de bienvenue à l'adresse racine
welcome_message = 'Bienvenue sur Flights Delays, votre compagnon de voyage!'


@app.get("/")
async def Welcome():
    return welcome_message


# Endpoint pour rechercher l'aeroport par son code

# Charger le fichier csv
airports_df = pd.read_csv("./assets/airports.csv")

# Endpoint pour rechercher l'aeroport par son code


@app.get("/airport/")
async def get_airport_name(code: str):
    code = code.upper()

    # Rechercher l'aéroport correspondant dans le dataframe
    airport = airports_df.loc[airports_df['IATA_CODE'] == code]

    # Vérifier si le code correspond à un aéroport existant
    if not airport.empty:
        iata_code = airport.iloc[0]['IATA_CODE']
        airport_name = airport.iloc[0]['AIRPORT']
        city = airport.iloc[0]['CITY']
        lat = airport.iloc[0]['LATITUDE']
        lon = airport.iloc[0]['LONGITUDE']

        # Retourner les informations de l'aéroport
        return {'iata_code': iata_code, 'airport': airport_name, 'city': city, 'lat': lat, 'lon': lon}

    # Si le code ne correspond à aucun aéroport existant, retourner une erreur 404
    else:
        raise HTTPException(
            status_code=404, detail="Airport not found, please check your airport code again!")


# Endpoint pour calculer la distance en milles entre deux villes

@app.get("/distance")
async def get_weather(lat_origin: float, lon_origin: float, lat_dest: float, lon_dest: float):
    try:
        # Calculer la distance en miles entre les deux villes à l'aide de la formule de Haversine
        from math import radians, cos, sin, asin, sqrt

        def distance(lat_origin, lon_origin, lat_dest, lon_dest):
            """
            Calcule la distance en miles entre deux points de coordonnées géographiques
            """
            # Convertir les coordonnées degrés en radians
            lon_origin, lat_origin, lon_dest, lat_dest = map(
                radians, [lon_origin, lat_origin, lon_dest, lat_dest])

            # Calculer la distance en utilisant la formule de Haversine
            dlon = lon_dest - lon_origin
            dlat = lat_dest - lat_origin
            a = sin(dlat / 2) ** 2 + cos(lat_origin) * \
                cos(lat_dest) * sin(dlon / 2) ** 2
            c = 2 * asin(sqrt(a))
            km = 6367 * c
            miles = km / 1.609344
            return miles

        distance_miles = f"{distance(lat_origin, lon_origin, lat_dest, lon_dest):.0f}"
        distance_miles = int(distance_miles)
        return distance_miles
    except:
        return 0


@app.get("/comparison")
async def predict_delay(airline: str, flight_number: int, position: int):
    position = 3
    from scraping.scrap_delay import ScrapDelay

    results = {}  # Initialize an empty results dictionary

    # Removed the try-except block
    with ScrapDelay(teardown=False) as bot:
        bot.land_first_page()
        bot.cookies()
        bot.select_airline(airline=airline)
        bot.type_flight_number(flight_number=flight_number)
        bot.select_date(position=position)
        bot.search()
        results = bot.results()
        bot.quit()

    if not results:
        return JSONResponse(status_code=200, content={"error": "Error while obtaining data, please try again later!"})

    # Convertir les heures programmées et réelles en objets datetime
    scheduled_time = datetime.strptime(
        results['scheduled_time'].split()[0], '%H:%M')
    actual_time = datetime.strptime(results['actual_time'].split()[0], '%H:%M')

    # Calculer la durée en minutes
    duration = int((actual_time - scheduled_time).total_seconds() / 60)

    # Définir le statut en fonction de la durée
    if duration == 0:
        status = 'On time'
    elif duration > 0:
        status = 'Delayed'
    else:
        status = 'In advance'

    # Ajouter les nouvelles clés et valeurs au dictionnaire results
    results['duration'] = duration
    results['status'] = status
    return JSONResponse(status_code=200, content=results)




@app.get("/predict")
async def predict_delay(MONTH: int, DAY_OF_MONTH: int, OP_UNIQUE_CARRIER: str, OP_CARRIER_FL_NUM: int, ORIGIN: str, DEST: str, CRS_DEP_TIME: int, CRS_ARR_TIME: int, CRS_ELAPSED_TIME: float, DISTANCE: float, CARRIER_NAME: str):
    results = {}  # Initialize an empty results dictionary

    # Charger les modèles pré-entraînés
    with open("./assets/xgb_model.pkl", "rb") as f:
        classifier = pickle.load(f)

    with open("./assets/xgb_reg_model.pkl", "rb") as f:
        regressor = pickle.load(f)

    # Charger le ColumnTransformer pré-entraîné
    with open("./assets/preprocessor.pkl", "rb") as f:
        preprocessor = pickle.load(f)

    # Créer un DataFrame à partir des caractéristiques fournies
    input_data = pd.DataFrame(data=[[MONTH, DAY_OF_MONTH, OP_UNIQUE_CARRIER, OP_CARRIER_FL_NUM, ORIGIN, DEST, CRS_DEP_TIME, CRS_ARR_TIME, CRS_ELAPSED_TIME, DISTANCE, CARRIER_NAME]], columns=['MONTH', 'DAY_OF_MONTH', 'OP_UNIQUE_CARRIER', 'OP_CARRIER_FL_NUM', 'ORIGIN', 'DEST', 'CRS_DEP_TIME', 'CRS_ARR_TIME', 'CRS_ELAPSED_TIME', 'DISTANCE', 'CARRIER_NAME'])

    # Transformer les données d'entrée avec le ColumnTransformer pré-entraîné
    input_data = preprocessor.transform(input_data)

    # Faire des prédictions avec les modèles
    pred_class = classifier.predict(input_data)
    if pred_class == 0:
        # Ajouter les nouvelles clés et valeurs au dictionnaire results
        results['duration'] = 0
        results['status'] = 'On time'
        return JSONResponse(status_code=200, content=results)

    else:
        pred_delay = regressor.predict(input_data)
        results['duration'] = pred_delay
        results['status'] = 'Delayed'
        return JSONResponse(status_code=200, content=results)







    # a = [ MONTH: int
    # DAY_OF_MONTH: int
    # CARRIER_NAME: str
    # CRS_DEP_TIME: int
    # OP_UNIQUE_CARRIER: str
    # OP_CARRIER_FL_NUM: int
    # ORIGIN: str
    # DEST: str
    # CRS_DEP_TIME: int
    # CRS_ARR_TIME: int
    # CRS_ELAPSED_TIME: int
    # DISTANCE: int]