import pandas as pd
import numpy as np
import os
import time
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from dotenv import load_dotenv

# --- 1. CONFIGURATION DES CHEMINS ET DE L'API ---
dossier_actuel = os.path.dirname(os.path.abspath(__file__))

# Charge le fichier .env localement ou depuis l'environnement système (GitHub Actions)
chemin_env = os.path.join(dossier_actuel, '.env')
if os.path.exists(chemin_env):
    load_dotenv(chemin_env)
else:
    load_dotenv()

# Recherche du CSV dans le dossier courant (GitHub/Local) ou dans le dossier parent Google Drive
chemin_entree_local = os.path.join(dossier_actuel, 'donnees_segmentation_profonde.csv')
chemin_entree_drive = os.path.join(
    os.path.expanduser('~'),
    'Google Drive',
    'Mon Drive',
    'Data Analyst Business / Ops',
    'Data Analyse - Segmentation Brevo clients KGI',
    'donnees_segmentation_profonde.csv'
)

if os.path.exists(chemin_entree_local):
    chemin_entree = chemin_entree_local
elif os.path.exists(chemin_entree_drive):
    chemin_entree = chemin_entree_drive
else:
    chemin_entree = chemin_entree_local  # Utilise le chemin local par défaut pour lever l'exception avec détails

if not os.path.exists(chemin_entree):
    raise FileNotFoundError(
        f"Erreur : Le fichier 'donnees_segmentation_profonde.csv' est introuvable à l'emplacement : {chemin_entree}\n"
        "Vérifie qu'il est présent à la racine de ton dépôt GitHub ou dans 'Mon Drive > Data Analyst Business / Ops > Data Analyse - Segmentation Brevo clients KGI'."
    )

# RÉCUPÉRATION DE LA CLÉ API BREVO
CLE_API_BREVO = os.getenv("BREVO_API_KEY")

if not CLE_API_BREVO:
    raise ValueError("Erreur : La variable 'BREVO_API_KEY' est introuvable (ni dans le .env, ni dans les Secrets GitHub).")

print("Étape 1 : Initialisation et connexion à l'API Brevo...")
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = CLE_API_BREVO
api_instance = sib_api_v3_sdk.ContactsApi(sib_api_v3_sdk.ApiClient(configuration))

# --- 2. CHARGEMENT DE LA BASE DE DONNÉES UNIQUE ---
print("Étape 2 : Chargement du fichier de segmentation profonde unifié...")
df_clients = pd.read_csv(chemin_entree, low_memory=False)
total_contacts = len(df_clients)
print(f"-> {total_contacts} contacts chargés (incluant Clients Actifs, Prospects et Enfants).")

# --- 3. SYNCHRONISATION UNIFIÉE VERS BREVO ---
print("\nÉtape 3 : Lancement de la synchronisation globale vers Brevo...")

compteur_succes = 0
compteur_erreur = 0

for idx, row in df_clients.iterrows():
    email = str(row['Email']).strip() if not pd.isna(row['Email']) else ''
    
    # Sécurité anti-nan / validation simple de l'adresse email
    if email == '' or '@' not in email:
        print(f"[-] Ligne {idx+1} ignorée : Adresse email invalide ou manquante.")
        compteur_erreur += 1
        continue

    # Récupération et nettoyage des indicateurs
    tunnel = str(row['Tunnel_Marketing']).strip() if 'Tunnel_Marketing' in row and not pd.isna(row['Tunnel_Marketing']) else ''
    segment = str(row['Segment_Metier']).strip() if 'Segment_Metier' in row and not pd.isna(row['Segment_Metier']) else ''
    cluster = int(row['Deep_Cluster']) if 'Deep_Cluster' in row and not pd.isna(row['Deep_Cluster']) else -1
    
    # Données RFM nettoyées
    recence = int(row['Recence_Clean']) if 'Recence_Clean' in row and not pd.isna(row['Recence_Clean']) else 999
    frequence = int(row['Frequence_Clean']) if 'Frequence_Clean' in row and not pd.isna(row
