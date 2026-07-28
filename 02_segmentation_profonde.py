import os
import sys
import unicodedata
import pandas as pd
import numpy as np
import gdown

# --- 1. CHARGEMENT ET TÉLÉCHARGEMENT ---
dossier_actuel = os.path.dirname(os.path.abspath(__file__))

chemin_rfm = os.path.join(dossier_actuel, "donnees_boutique_propres_interne.csv")
chemin_transactions = os.path.join(dossier_actuel, "export_commandes.csv")
chemin_produits = os.path.join(dossier_actuel, "export_produits_KGI.csv")
chemin_sortie = os.path.join(dossier_actuel, "donnees_segmentation_profonde.csv")

drive_id_rfm = os.environ.get("DRIVE_ID_RFM")
drive_id_trans = os.environ.get("DRIVE_ID_TRANS")
drive_id_prod = os.environ.get("DRIVE_ID_PROD")

def telecharger_drive(drive_id, chemin_dest):
    if not drive_id: return
    url_csv = f"https://docs.google.com/spreadsheets/d/{drive_id}/export?format=csv"
    try:
        gdown.download(url_csv, chemin_dest, quiet=False)
    except Exception:
        url_standard = f"https://drive.google.com/uc?id={drive_id}"
        gdown.download(url_standard, chemin_dest, quiet=False)

telecharger_drive(drive_id_rfm, chemin_rfm)
telecharger_drive(drive_id_trans, chemin_transactions)
telecharger_drive(drive_id_prod, chemin_produits)

def charger_fichier(chemin):
    try:
        return pd.read_csv(chemin, low_memory=False)
    except Exception:
        return pd.read_excel(chemin)

df_rfm = charger_fichier(chemin_rfm)
df_trans = charger_fichier(chemin_transactions)

# --- 2. NETTOYAGE STRICT ET SÉCURISATION DES PRODUITS ---
def normaliser_texte(texte):
    if pd.isna(texte): return ""
    texte = str(texte).lower()
    texte = unicodedata.normalize('NFD', texte).encode('ascii', 'ignore').decode('utf-8')
    return texte

col_prod_trans = next((c for c in df_trans.columns if any(k in c.lower() for k in ['nom', 'produit', 'item', 'lineitem'])), df_trans.columns[0])
col_email_trans = next((c for c in df_trans.columns if 'email' in c.lower() or 'mail' in c.lower()), df_trans.columns[0])

df_trans['Email_Clean'] = df_trans[col_email_trans].astype(str).str.strip().str.lower()
df_trans['Produit_Clean'] = df_trans[col_prod_trans].apply(normaliser_texte)

# --- 3. DÉTECTION DES PRODUITS (UNIQUEMENT SUR LE NOM DU PRODUIT) ---

MOTS_KUMITE = ['kumite', 'protection', 'plastron', 'gant', 'patte d\'ours', 'pattes d\'ours', 'bouclier', 'casque', 'protege-dent', 'protege dent', 'protege-tibia', 'protege tibia', 'coque']

EXCLUSIONS_ELITE = ['kodomo', 'shoshin', 'bicolore', 'blanche', 'jaune', 'orange', 'verte', 'bleue', 'marron', 'junior', 'enfant', 'initiation']
MOTS_ELITE = ['wkf', 'master', 'ceinture noire', 'ceinture rouge et blanche', 'ceinture rouge/blanche', 'kata', 'tokyodo', 'hirota', 'seishin', 'expert']

EXCLUSIONS_DEBUTANT = ['ceinture noire', 'ceinture rouge et blanche', 'ceinture rouge/blanche', 'wkf', 'master', 'expert', 'tokyodo', 'hirota', 'seishin']
MOTS_DEBUTANT = [
    'kodomo', 'shoshin', 'initiation', 'debutant', 'ceinture blanche', 'ceinture jaune', 
    'ceinture orange', 'ceinture verte', 'ceinture bicolore', '100cm', '110cm', '120cm', '130cm', '140cm'
]

# POUR ENFANT : On cherche exclusivement du matériel enfant/junior dans le NOM DU PRODUIT
MOTS_ENFANT = ['enfant', 'junior', 'kodomo', 'taille enfant', 'kimono enfant', 'protege-tibia enfant']

def analyser_achats_client(produits_liste):
    texte_produits = " ".join(produits_liste)

    is_kumite = any(m in texte_produits for m in MOTS_KUMITE)
    
    has_elite_mot = any(m in texte_produits for m in MOTS_ELITE)
    has_elite_excl = any(m in texte_produits for m in EXCLUSIONS_ELITE)
    is_elite = has_elite_mot and not has_elite_excl

    has_deb_mot = any(m in texte_produits for m in MOTS_DEBUTANT)
    has_deb_excl = any(m in texte_produits for m in EXCLUSIONS_DEBUTANT)
    is_debutant = has_deb_mot and not has_deb_excl

    # Détection Enfant sécurisée
    is_enfant = any(m in texte_produits for m in MOTS_ENFANT)

    return pd.Series({
        'has_kumite': is_kumite,
        'has_elite': is_elite,
        'has_debutant': is_debutant,
        'has_enfant': is_enfant
    })

achats_par_client = df_trans.groupby('Email_Clean')['Produit_Clean'].apply(list).apply(analyser_achats_client)

# --- 4. PREPARATION RFM ET FUSION ---
col_email_rfm = next((c for c in df_rfm.columns if 'email' in c.lower() or 'mail' in c.lower()), df_rfm.columns[0])
df_rfm['Email'] = df_rfm[col_email_rfm].astype(str).str.strip().str.lower()

df = pd.merge(df_rfm, achats_par_client, left_on='Email', right_index=True, how='left')
df['has_kumite'] = df['has_kumite'].fillna(False)
df['has_elite'] = df['has_elite'].fillna(False)
df['has_debutant'] = df['has_debutant'].fillna(False)
df['has_enfant'] = df['has_enfant'].fillna(False)

col_orders = next((c for c in df.columns if any(k in c.lower() for k in ['commandes', 'orders', 'frequence'])), None)
col_amount = next((c for c in df.columns if any(k in c.lower() for k in ['montant', 'total', 'ca', 'valeur'])), None)
col_recency = next((c for c in df.columns if any(k in c.lower() for k in ['recence', 'derniere', 'days'])), None)

df['Frequence_Clean'] = pd.to_numeric(df[col_orders], errors='coerce').fillna(0).astype(int) if col_orders else 0
df['Montant_Clean'] = pd.to_numeric(df[col_amount], errors='coerce').fillna(0.0).astype(float) if col_amount else 0.0
df['Recence_Clean'] = pd.to_numeric(df[col_recency], errors='coerce').fillna(999).astype(int) if col_recency else 999

# --- 5. RÈGLES DE SEGMENTATION STRICTES ---
def attribuer_segmentation(row):
    freq = row['Frequence_Clean']
    montant = row['Montant_Clean']
    recence = row['Recence_Clean']

    # Clusters RFM
    if freq == 0 or montant == 0:
        cluster_id = 0
        rfm_label = "Prospect Non Converti"
    elif freq == 1 and recence <= 90:
        cluster_id = 1
        rfm_label = "Nouveau Client Récent"
    elif freq == 1 and recence > 90 and recence <= 240:
        cluster_id = 2
        rfm_label = "Client Occasionnel"
    elif freq >= 2 and recence <= 180 and montant < 300:
        cluster_id = 3
        rfm_label = "Client Régulier"
    elif (freq >= 3 or montant >= 300) and recence <= 365:
        cluster_id = 4
        rfm_label = "Client VIP / Élite RFM"
    else:
        cluster_id = 5
        rfm_label = "Inactif / Risque d'Attrition"

    # Attribution du Tunnel Marketing
    if row['has_kumite']:
        tunnel = 'tunnel_kumite'
        segment_metier = 'Passionné Kumite'
    elif row['has_elite']:
        tunnel = 'tunnel_elite_pro'
        segment_metier = 'Expert / Élite Pro'
    elif row['has_debutant']:
        tunnel = 'tunnel_debutant'
        segment_metier = 'Initiation / Débutant'
    elif row['has_enfant']:
        tunnel = 'tunnel_enfant'
        segment_metier = 'Équipement Enfant'
    elif cluster_id == 0:
        tunnel = 'tunnel_prospect_sans_achat'
        segment_metier = 'Prospect Non Converti'
    elif cluster_id == 4:
        tunnel = 'tunnel_elite_pro'
        segment_metier = 'Client VIP'
    elif cluster_id == 5:
        tunnel = 'tunnel_defaut'
        segment_metier = 'Client Inactif à Relancer'
    else:
        tunnel = 'tunnel_defaut'
        segment_metier = rfm_label

    return pd.Series({
        'Deep_Cluster': cluster_id,
        'RFM_Label': rfm_label,
        'Tunnel_Marketing': tunnel,
        'Segment_Metier': segment_metier
    })

res_seg = df.apply(attribuer_segmentation, axis=1)
df['Deep_Cluster'] = res_seg['Deep_Cluster']
df['RFM_Label'] = res_seg['RFM_Label']
df['Tunnel_Marketing'] = res_seg['Tunnel_Marketing']
df['Segment_Metier'] = res_seg['Segment_Metier']

# --- 6. SAUVEGARDE ---
df.to_csv(chemin_sortie, index=False, encoding='utf-8')
print(f"Fichier segmentation mis à jour : {chemin_sortie}")
print("\n--- RÉPARTITION DES TUNNELS ---")
print(df['Tunnel_Marketing'].value_counts())
