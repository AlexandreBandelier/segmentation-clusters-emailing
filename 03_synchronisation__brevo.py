import os
import time
import pandas as pd
import numpy as np
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from dotenv import load_dotenv
import gdown

# --- TELECHARGEMENT DEPUIS GOOGLE DRIVE ---
drive_file_id = os.environ.get("DRIVE_FILE_ID")
output_csv = "donnees_segmentation_profonde.csv"

if drive_file_id:
    print(f"Téléchargement du fichier CSV depuis Google Drive (ID: {drive_file_id})...")
    url = f"https://drive.google.com/uc?id={drive_file_id}"
    gdown.download(url, output_csv, quiet=False, fuzzy=True)
else:
    print("Attention : Aucune variable DRIVE_FILE_ID détectée. Utilisation du fichier local.")
# ------------------------------------------

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
    chemin_entree = chemin_entree_local  # Utilise le chemin local par défaut

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
    
    # Données RFM nettoyées (corrige la ligne coupée)
    recence = int(row['Recence_Clean']) if 'Recence_Clean' in row and not pd.isna(row['Recence_Clean']) else 999
    frequence = int(row['Frequence_Clean']) if 'Frequence_Clean' in row and not pd.isna(row['Frequence_Clean']) else 0
    montant = float(row['Montant_Clean']) if 'Montant_Clean' in row and not pd.isna(row['Montant_Clean']) else 0.0

    # Construction du dictionnaire d'attributs pour Brevo
    attributes = {
        "TUNNEL_MARKETING": tunnel,
        "SEGMENT_METIER": segment,
        "DEEP_CLUSTER": cluster,
        "RECENCE": recence,
        "FREQUENCE": frequence,
        "MONTANT": montant
    }

    # Préparation du contact Brevo
    create_contact = sib_api_v3_sdk.CreateContact(
        email=email,
        attributes=attributes,
        update_enabled=True  # Met à jour le contact s'il existe déjà dans Brevo
    )

    try:
        api_instance.create_contact(create_contact)
        compteur_succes += 1
        if (idx + 1) % 50 == 0 or (idx + 1) == total_contacts:
            print(f"[+] Progression : {idx+1}/{total_contacts} contacts traités.")
    except ApiException as e:
        print(f"[!] Erreur API Brevo pour {email} (Ligne {idx+1}) : {e.reason}")
        compteur_erreur += 1

    # Pause très courte pour respecter les limites de rate-limit de l'API Brevo
    time.sleep(0.05)

# --- 4. BILAN DE LA SYNCHRONISATION ---
print("\n" + "="*50)
print(f"SYNCHRONISATION TERMINÉE : {compteur_succes} mis à jour / {compteur_erreur} erreurs")
print("="*50)
