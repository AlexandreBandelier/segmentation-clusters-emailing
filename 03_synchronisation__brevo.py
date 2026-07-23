import os
import sys
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
    gdown.download(url, output_csv, quiet=False)
else:
    print("Attention : Aucune variable DRIVE_FILE_ID détectée. Utilisation du fichier local.")
# ------------------------------------------

# --- 1. CONFIGURATION DES CHEMINS ET DE L'API ---
dossier_actuel = os.path.dirname(os.path.abspath(__file__))

chemin_env = os.path.join(dossier_actuel, '.env')
if os.path.exists(chemin_env):
    load_dotenv(chemin_env)
else:
    load_dotenv()

chemin_entree = os.path.join(dossier_actuel, 'donnees_segmentation_profonde.csv')

if not os.path.exists(chemin_entree):
    raise FileNotFoundError(f"Erreur : Le fichier '{chemin_entree}' est introuvable.")

# RÉCUPÉRATION DE LA CLÉ API BREVO
CLE_API_BREVO = os.getenv("BREVO_API_KEY")

if not CLE_API_BREVO:
    raise ValueError("Erreur : La variable 'BREVO_API_KEY' est introuvable (ni dans le .env, ni dans les Secrets GitHub).")

# DIAGNOSTIC DE LA CLÉ
cle_masquee = CLE_API_BREVO[:6] + "..." + CLE_API_BREVO[-4:] if len(CLE_API_BREVO) > 10 else "TROP COURTE"
print(f"🔑 DIAGNOSTIC : Clé injectée = {cle_masquee} | Longueur = {len(CLE_API_BREVO)} caractères.")

print("Étape 1 : Initialisation et connexion à l'API Brevo...")
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = CLE_API_BREVO
api_instance = sib_api_v3_sdk.ContactsApi(sib_api_v3_sdk.ApiClient(configuration))

# --- 2. CHARGEMENT DE LA BASE DE DONNÉES UNIQUE ---
print("Étape 2 : Chargement du fichier de segmentation...")
df_clients = pd.read_csv(chemin_entree, low_memory=False)
total_contacts = len(df_clients)
print(f"-> {total_contacts} contacts chargés.")

# --- 3. SYNCHRONISATION UNIFIÉE VERS BREVO ---
print("\nÉtape 3 : Lancement de la synchronisation globale vers Brevo...")

compteur_succes = 0
compteur_erreur = 0
erreurs_consecutives = 0

for idx, row in df_clients.iterrows():
    email = str(row['Email']).strip() if not pd.isna(row['Email']) else ''
    
    if email == '' or '@' not in email:
        compteur_erreur += 1
        continue

    tunnel = str(row['Tunnel_Marketing']).strip() if 'Tunnel_Marketing' in row and not pd.isna(row['Tunnel_Marketing']) else ''
    segment = str(row['Segment_Metier']).strip() if 'Segment_Metier' in row and not pd.isna(row['Segment_Metier']) else ''
    cluster = int(row['Deep_Cluster']) if 'Deep_Cluster' in row and not pd.isna(row['Deep_Cluster']) else -1
    
    recence = int(row['Recence_Clean']) if 'Recence_Clean' in row and not pd.isna(row['Recence_Clean']) else 999
    frequence = int(row['Frequence_Clean']) if 'Frequence_Clean' in row and not pd.isna(row['Frequence_Clean']) else 0
    montant = float(row['Montant_Clean']) if 'Montant_Clean' in row and not pd.isna(row['Montant_Clean']) else 0.0

    attributes = {
        "TUNNEL_MARKETING": tunnel,
        "SEGMENT_METIER": segment,
        "DEEP_CLUSTER": cluster,
        "RECENCE": recence,
        "FREQUENCE": frequence,
        "MONTANT": montant
    }

    create_contact = sib_api_v3_sdk.CreateContact(
        email=email,
        attributes=attributes,
        update_enabled=True
    )

    try:
        api_instance.create_contact(create_contact)
        compteur_succes += 1
        erreurs_consecutives = 0
        if (idx + 1) % 50 == 0 or (idx + 1) == total_contacts:
            print(f"[+] Progression : {idx+1}/{total_contacts} contacts traités.")
    except ApiException as e:
        print(f"[!] Erreur API Brevo pour {email} (Ligne {idx+1}) : {e.status} - {e.reason}")
        print(f"👉 DÉTAIL BREVO : {e.body}")
        compteur_erreur += 1
        erreurs_consecutives += 1
        
        if erreurs_consecutives >= 5:
            print("\n❌ ERREUR CRITIQUE : 5 échecs consécutifs d'authentification (Unauthorized).")
            print("Arret du script pour éviter de boucler inutilement.")
            sys.exit(1)

    time.sleep(0.05)

print("\n" + "="*50)
print(f"SYNCHRONISATION TERMINÉE : {compteur_succes} mis à jour / {compteur_erreur} erreurs")
print("="*50)
