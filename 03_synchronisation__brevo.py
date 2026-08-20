import os
import sys
import time
from dotenv import load_dotenv
import pandas as pd
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

# --- 1. CONFIGURATION DES CHEMINS ET DE L'API ---
dossier_actuel = os.path.dirname(os.path.abspath(__file__))

chemin_env = os.path.join(dossier_actuel, '.env')
if os.path.exists(chemin_env):
    load_dotenv(chemin_env)
else:
    load_dotenv()

chemin_entree = os.path.join(dossier_actuel, 'donnees_segmentation_profonde.csv')

if not os.path.exists(chemin_entree):
    raise FileNotFoundError(
        f"Erreur : Le fichier '{chemin_entree}' est introuvable. Exécutez le script 02 d'abord."
    )

CLE_API_BREVO = os.getenv('BREVO_API_KEY')
if not CLE_API_BREVO:
    raise ValueError(
        "Erreur : La variable 'BREVO_API_KEY' est introuvable (ni dans le .env, ni dans les Secrets GitHub)."
    )

cle_masquee = (
    CLE_API_BREVO[:6] + '...' + CLE_API_BREVO[-4:]
    if len(CLE_API_BREVO) > 10
    else 'TROP COURTE'
)
print(f"DIAGNOSTIC : Clé injectée = {cle_masquee} | Longueur = {len(CLE_API_BREVO)} caractères.")

print("Étape 1 : Initialisation et connexion à l'API Brevo...")
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = CLE_API_BREVO
api_instance = sib_api_v3_sdk.ContactsApi(sib_api_v3_sdk.ApiClient(configuration))

# --- 2. CHARGEMENT ET NETTOYAGE DES DONNÉES ---
print("Étape 2 : Chargement du fichier de segmentation frais...")
df = pd.read_csv(chemin_entree, low_memory=False)

if 'Email' not in df.columns:
    raise KeyError("Erreur : La colonne 'Email' est absente du fichier CSV.")

# Filtrage et normalisation
df['email'] = df['Email'].astype(str).str.strip().str.lower()
df = df[df['email'].str.contains(r'^[^@]+@[^@]+\.[^@]+$', regex=True, na=False)].copy()

df['rfm_label'] = df['RFM_Label'].fillna('Inactif / Risque').astype(str).str.strip() if 'RFM_Label' in df.columns else 'Inactif / Risque'
df['specialite'] = df['Specialite_Produit'].fillna('Général').astype(str).str.strip() if 'Specialite_Produit' in df.columns else 'Général'
df['pays'] = df['Pays'].fillna('FR').astype(str).str.strip().str.upper() if 'Pays' in df.columns else 'FR'
df['langue'] = df['Langue'].fillna('fr').astype(str).str.strip().str.lower() if 'Langue' in df.columns else 'fr'

total_contacts = len(df)
print(f"-> {total_contacts} contacts valides préparés.")

# --- 3. SYNCHRONISATION VERS BREVO ---
print("\nÉtape 3 : Lancement de la synchronisation globale vers Brevo...")
compteur_succes = 0
compteur_erreur = 0
erreurs_consecutives = 0

for idx, row in df.iterrows():
    attributes = {
        'RFM_LABEL': row['rfm_label'],
        'SPECIALITE_PRODUIT': row['specialite'],
        'PAYS': row['pays'],
        'LANGUE': row['langue'],
    }

    create_contact = sib_api_v3_sdk.CreateContact(
        email=row['email'],
        attributes=attributes,
        email_blacklisted=False,
        update_enabled=True
    )

    try:
        api_instance.create_contact(create_contact)
        compteur_succes += 1
        erreurs_consecutives = 0
        if (idx + 1) % 500 == 0 or (idx + 1) == total_contacts:
            print(f"[+] Progression : {idx+1}/{total_contacts} contacts traités.")
    except ApiException as e:
        compteur_erreur += 1
        erreurs_consecutives += 1
        print(f"[!] Erreur API Brevo pour {row['email']} (Ligne {idx+1}) : {e.status} - {e.reason}")
        print(f"DÉTAIL BREVO : {e.body}")

        if e.status in [401, 403] or erreurs_consecutives >= 5:
            print("\nERREUR CRITIQUE : Arrêt du script suite à des erreurs répétées d'authentification ou d'API.")
            sys.exit(1)

    time.sleep(0.02)  # Pause pour respecter la limite de débit

print('\n' + '=' * 50)
print(f'SYNCHRONISATION TERMINÉE : {compteur_succes} mis à jour / {compteur_erreur} erreurs')
print('=' * 50)
