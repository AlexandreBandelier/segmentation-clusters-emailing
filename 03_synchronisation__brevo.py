import os
import sys
import time
from dotenv import load_dotenv
import numpy as np
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

# Le script 03 lit DIRECTEMENT le fichier local généré par le script 02
chemin_entree = os.path.join(
    dossier_actuel, 'donnees_segmentation_profonde.csv'
)

if not os.path.exists(chemin_entree):
    raise FileNotFoundError(
        f"Erreur : Le fichier '{chemin_entree}' est introuvable. Exécutez le"
        " script 02 d'abord."
    )

# RÉCUPÉRATION DE LA CLÉ API BREVO
CLE_API_BREVO = os.getenv('BREVO_API_KEY')

if not CLE_API_BREVO:
    raise ValueError(
        "Erreur : La variable 'BREVO_API_KEY' est introuvable (ni dans le .env, ni"
        " dans les Secrets GitHub)."
    )

# DIAGNOSTIC DE LA CLÉ
cle_masquee = (
    CLE_API_BREVO[:6] + '...' + CLE_API_BREVO[-4:]
    if len(CLE_API_BREVO) > 10
    else 'TROP COURTE'
)
print(
    f'DIAGNOSTIC : Clé injectée = {cle_masquee} | Longueur ='
    f' {len(CLE_API_BREVO)} caractères.'
)

print("Étape 1 : Initialisation et connexion à l'API Brevo...")
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = CLE_API_BREVO
api_instance = sib_api_v3_sdk.ContactsApi(
    sib_api_v3_sdk.ApiClient(configuration)
)

# --- 2. CHARGEMENT DE LA BASE DE DONNÉES UNIQUE ---
print("Étape 2 : Chargement du fichier de segmentation frais...")
df_clients = pd.read_csv(chemin_entree, low_memory=False)
total_contacts = len(df_clients)
print(f'-> {total_contacts} contacts chargés.')

# --- 3. SYNCHRONISATION UNIFIÉE VERS BREVO ---
print('\nÉtape 3 : Lancement de la synchronisation globale vers Brevo...')

compteur_succes = 0
compteur_erreur = 0
erreurs_consecutives = 0

for idx, row in df_clients.iterrows():
    email = str(row['Email']).strip() if 'Email' in row and not pd.isna(row['Email']) else ''

    if email == '' or '@' not in email:
        compteur_erreur += 1
        continue

    # Récupération des deux nouvelles attributs nettoyés
    rfm_label = (
        str(row['RFM_Label']).strip()
        if 'RFM_Label' in row and not pd.isna(row['RFM_Label'])
        else 'Inactif / Risque'
    )
    specialite_produit = (
        str(row['Specialite_Produit']).strip()
        if 'Specialite_Produit' in row and not pd.isna(row['Specialite_Produit'])
        else 'Général'
    )

    attributes = {
        'RFM_LABEL': rfm_label,
        'SPECIALITE_PRODUIT': specialite_produit,
    }

    # Création ou mise à jour du contact dans Brevo
    create_contact = sib_api_v3_sdk.CreateContact(
        email=email,
        attributes=attributes,
        email_blacklisted=False,  # Permet la réinscription / mise à jour automatique
        update_enabled=True
    )

    try:
        api_instance.create_contact(create_contact)
        compteur_succes += 1
        erreurs_consecutives = 0
        if (idx + 1) % 50 == 0 or (idx + 1) == total_contacts:
            print(f'[+] Progression : {idx+1}/{total_contacts} contacts traités.')
    except ApiException as e:
        print(
            f'[!] Erreur API Brevo pour {email} (Ligne {idx+1}) : {e.status} -'
            f' {e.reason}'
        )
        print(f'DÉTAIL BREVO : {e.body}')
        compteur_erreur += 1
        erreurs_consecutives += 1

        if erreurs_consecutives >= 5:
            print(
                '\n ERREUR CRITIQUE : 5 échecs consécutifs d\'authentification'
                ' (Unauthorized).'
            )
            print('Arrêt du script pour éviter de boucler inutilement.')
            sys.exit(1)

    time.sleep(0.05)

print('\n' + '=' * 50)
print(
    f'SYNCHRONISATION TERMINÉE : {compteur_succes} mis à jour /'
    f' {compteur_erreur} erreurs'
)
print('=' * 50)
