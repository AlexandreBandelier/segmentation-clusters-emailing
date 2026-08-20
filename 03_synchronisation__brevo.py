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

# --- 2. CHARGEMENT ET PRÉPARATION DES DONNÉES ---
print("Étape 2 : Chargement et préparation du fichier de segmentation...")
df = pd.read_csv(chemin_entree, low_memory=False)

if 'Email' not in df.columns:
    raise KeyError("Erreur : La colonne 'Email' est absente du fichier d'entrée.")

# Nettoyage
df['email'] = df['Email'].astype(str).str.strip().str.lower()
df = df[df['email'].str.contains(r'^[^@]+@[^@]+\.[^@]+$', regex=True, na=False)].copy()

df['rfm_label'] = df['RFM_Label'].fillna('Inactif / Risque').astype(str).str.strip() if 'RFM_Label' in df.columns else 'Inactif / Risque'
df['specialite'] = df['Specialite_Produit'].fillna('Général').astype(str).str.strip() if 'Specialite_Produit' in df.columns else 'Général'
df['pays'] = df['Pays'].fillna('FR').astype(str).str.strip().str.upper() if 'Pays' in df.columns else 'FR'
df['langue'] = df['Langue'].fillna('fr').astype(str).str.strip().str.lower() if 'Langue' in df.columns else 'fr'

# Structure conforme attendue par l'API importContacts de Brevo
contacts_payload = []
for _, r in df.iterrows():
    contacts_payload.append({
        "email": r['email'],
        "attributes": {
            "RFM_LABEL": r['rfm_label'],
            "SPECIALITE_PRODUIT": r['specialite'],
            "PAYS": r['pays'],
            "LANGUE": r['langue']
        }
    })

total_contacts = len(contacts_payload)
print(f"-> {total_contacts} contacts valides préparés pour la synchronisation.")

# --- 3. SYNCHRONISATION PAR LOTS AVEC RETRY & BACKOFF (OPTIMISATIONS 2 & 3) ---
print("\nÉtape 3 : Lancement de la synchronisation globale par lots (Batch Import)...")

TAILLE_LOT = 250   # Taille optimale par lot pour Brevo API
MAX_RETRIES = 3    # Nombre de réessais en cas d'erreur temporaire

compteur_succes = 0
compteur_erreur = 0

for i in range(0, total_contacts, TAILLE_LOT):
    batch = contacts_payload[i:i + TAILLE_LOT]
    num_lot = (i // TAILLE_LOT) + 1
    total_lots = (total_contacts + TAILLE_LOT - 1) // TAILLE_LOT

    request_import = sib_api_v3_sdk.RequestContactImport(
        json_body=batch,
        update_existing_contacts=True
    )

    succes = False
    for tentative in range(1, MAX_RETRIES + 1):
        try:
            api_instance.import_contacts(request_import)
            compteur_succes += len(batch)
            succes = True
            print(f"[+] Lot {num_lot}/{total_lots} synchronisé ({min(i + TAILLE_LOT, total_contacts)}/{total_contacts} contacts).")
            break
        except ApiException as e:
            # Interruption immédiate sur clé invalide ou permissions insuffisantes
            if e.status in [401, 403]:
                print(f"\n[!] ERREUR CRITIQUE AUTHENTIFICATION ({e.status}) : Clé API invalide ou permissions insuffisantes.")
                sys.exit(1)
            
            print(f"[!] Avertissement sur Lot {num_lot}/{total_lots} (Tentative {tentative}/{MAX_RETRIES}) - Erreur {e.status} : {e.reason}")
            if tentative < MAX_RETRIES:
                temps_attente = 2 ** tentative  # Reprise exponentielle (2s, 4s, etc.)
                time.sleep(temps_attente)

    if not succes:
        print(f"ÉCHEC DÉFINITIF pour le lot {num_lot} ({len(batch)} contacts ignorés).")
        compteur_erreur += len(batch)

    time.sleep(0.1)

print('\n' + '=' * 50)
print(f'SYNCHRONISATION TERMINÉE : {compteur_succes} contacts mis à jour / {compteur_erreur} échecs')
print('=' * 50)
