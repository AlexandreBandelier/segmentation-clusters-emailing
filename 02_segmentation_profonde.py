import os
import re
import sys
import unicodedata
from datetime import datetime
import gdown
import numpy as np
import pandas as pd

# --- 1. CONFIGURATION DES CHEMINS ET TELECHARGEMENT DRIVE ---
dossier_actuel = os.path.dirname(os.path.abspath(__file__))

chemin_rfm = os.path.join(dossier_actuel, 'donnees_boutique_propres_interne.csv')
chemin_transactions = os.path.join(dossier_actuel, 'export_commandes.csv')
chemin_produits = os.path.join(dossier_actuel, 'export_produits_KGI.csv')
chemin_sortie_profonde = os.path.join(
    dossier_actuel, 'donnees_segmentation_profonde.csv'
)

drive_id_rfm = os.environ.get('DRIVE_ID_RFM')
drive_id_trans = os.environ.get('DRIVE_ID_TRANS')
drive_id_prod = os.environ.get('DRIVE_ID_PROD')

print('Étape 1 : Téléchargement des données depuis Google Drive...')


def telecharger_drive(drive_id, chemin_dest):
  if not drive_id:
    return
  url_csv = (
      f'https://docs.google.com/spreadsheets/d/{drive_id}/export?format=csv'
  )
  try:
    gdown.download(url_csv, chemin_dest, quiet=False)
  except Exception:
    url_standard = f'https://drive.google.com/uc?id={drive_id}'
    gdown.download(url_standard, chemin_dest, quiet=False)


telecharger_drive(drive_id_rfm, chemin_rfm)
telecharger_drive(drive_id_trans, chemin_transactions)
telecharger_drive(drive_id_prod, chemin_produits)


def charger_fichier(chemin):
  try:
    return pd.read_csv(chemin, low_memory=False)
  except Exception:
    try:
      return pd.read_excel(chemin)
    except Exception as e:
      raise Exception(f"Impossible de lire '{chemin}' : {e}")


df_rfm = charger_fichier(chemin_rfm)
df_trans = charger_fichier(chemin_transactions)
df_prod = charger_fichier(chemin_produits)

# --- 2. NETTOYAGE DES TEXTES ET FONCTIONS DE NORMALISATION ---


def normaliser_texte(texte):
  if pd.isna(texte):
    return ''
  texte = str(texte).lower()
  texte = unicodedata.normalize('NFD', texte).encode('ascii', 'ignore').decode('utf-8')
  return texte


# Normalisation des colonnes d'achats
col_prod_trans = next(
    (c for c in df_trans.columns if 'nom' in c.lower() or 'produit' in c.lower() or 'item' in c.lower() or 'lineitem' in c.lower()),
    df_trans.columns[0],
)
col_email_trans = next(
    (c for c in df_trans.columns if 'email' in c.lower() or 'mail' in c.lower()),
    df_trans.columns[0],
)

df_trans['Email_Clean'] = df_trans[col_email_trans].astype(str).str.strip().str.lower()
df_trans['Produit_Clean'] = df_trans[col_prod_trans].apply(normaliser_texte)

# --- 3. DÉTECTION DES AFFINITÉS PRODUITS PAR CLIENT ---
print('Étape 2 : Analyse fine des produits achetés par client...')

# Mots-clés
MOTS_KUMITE = [
    'kumite',
    'protection',
    'plastron',
    'gant',
    'patte d\'ours',
    'pattes d\'ours',
    'bouclier',
    'casque',
    'protege-dent',
    'protege dent',
    'protege-tibia',
    'protege tibia',
    'coque',
]

EXCLUSIONS_ELITE = [
    'kodomo',
    'shoshin',
    'bicolore',
    'blanche',
    'jaune',
    'orange',
    'verte',
    'bleue',
    'marron',
    'junior',
    'enfant',
    'initiation',
]
MOTS_ELITE = [
    'wkf',
    'master',
    'ceinture noire',
    'ceinture rouge et blanche',
    'ceinture rouge/blanche',
    'kata',
    'tokyodo',
    'hirota',
    'seishin',
    'expert',
]

EXCLUSIONS_DEBUTANT = [
    'ceinture noire',
    'ceinture rouge et blanche',
    'ceinture rouge/blanche',
    'wkf',
    'master',
    'expert',
    'tokyodo',
    'hirota',
    'seishin',
]
MOTS_DEBUTANT = [
    'kodomo',
    'shoshin',
    'initiation',
    'debutant',
    'ceinture blanche',
    'ceinture jaune',
    'ceinture orange',
    'ceinture verte',
    'ceinture bicolore',
]

MOTS_ENFANT = [
    'enfant',
    'junior',
    'kodomo',
    'poussin',
    'pupille',
    'benjamin',
    'minime',
]


def analyser_achats_client(produits_liste):
  texte_global = ' '.join(produits_liste)

  # Check Kumite
  is_kumite = any(m in texte_global for m in MOTS_KUMITE)

  # Check Elite Pro (Doit avoir mot elite ET aucune exclusion)
  has_elite_mot = any(m in texte_global for m in MOTS_ELITE)
  has_elite_excl = any(m in texte_global for m in EXCLUSIONS_ELITE)
  is_elite = has_elite_mot and not has_elite_excl

  # Check Débutant (Doit avoir mot débutant ET aucune exclusion maître/noire)
  has_deb_mot = any(m in texte_global for m in MOTS_DEBUTANT)
  has_deb_excl = any(m in texte_global for m in EXCLUSIONS_DEBUTANT)
  is_debutant = has_deb_mot and not has_deb_excl

  # Check Enfant
  is_enfant = any(m in texte_global for m in MOTS_ENFANT)

  return pd.Series({
      'has_kumite': is_kumite,
      'has_elite': is_elite,
      'has_debutant': is_debutant,
      'has_enfant': is_enfant,
  })


achats_par_client = (
    df_trans.groupby('Email_Clean')['Produit_Clean']
    .apply(list)
    .apply(analyser_achats_client)
)

# --- 4. PRÉPARATION DU DATAFRAME CLIENTS (RFM) ---
print('Étape 3 : Calcul des métriques RFM et nettoyage des dates...')

col_email_rfm = next(
    (c for c in df_rfm.columns if 'email' in c.lower() or 'mail' in c.lower()),
    df_rfm.columns[0],
)
df_rfm['Email'] = df_rfm[col_email_rfm].astype(str).str.strip().str.lower()

# Fusion avec l'analyse produits
df = pd.merge(df_rfm, achats_par_client, left_on='Email', right_index=True, how='left')
df['has_kumite'] = df['has_kumite'].fillna(False)
df['has_elite'] = df['has_elite'].fillna(False)
df['has_debutant'] = df['has_debutant'].fillna(False)
df['has_enfant'] = df['has_enfant'].fillna(False)

# Normalisation RFM
col_orders = next(
    (c for c in df.columns if 'commandes' in c.lower() or 'orders' in c.lower() or 'frequence' in c.lower()),
    None,
)
col_amount = next(
    (c for c in df.columns if 'montant' in c.lower() or 'total' in c.lower() or 'ca' in c.lower() or 'valeur' in c.lower()),
    None,
)
col_recency = next(
    (c for c in df.columns if 'recence' in c.lower() or 'derniere' in c.lower() or 'days' in c.lower()),
    None,
)

df['Frequence_Clean'] = pd.to_numeric(df[col_orders], errors='coerce').fillna(0).astype(int) if col_orders else 0
df['Montant_Clean'] = pd.to_numeric(df[col_amount], errors='coerce').fillna(0.0).astype(float) if col_amount else 0.0
df['Recence_Clean'] = pd.to_numeric(df[col_recency], errors='coerce').fillna(999).astype(int) if col_recency else 999

# --- 5. APPLICATION DES RÈGLES MÉTIER STRICTES (CLUSTER ID & TUNNELS) ---
print('Étape 4 : Application des règles métier déterministes...')


def attribuer_segmentation(row):
  freq = row['Frequence_Clean']
  montant = row['Montant_Clean']
  recence = row['Recence_Clean']

  # 1. RÈGLES DE CLUSTERS RFM STRICTES
  if freq == 0 or montant == 0:
    cluster_id = 0
    rfm_label = 'Prospect Non Converti'
  elif freq == 1 and recence <= 90:
    cluster_id = 1
    rfm_label = 'Nouveau Client Récent'
  elif freq == 1 and recence > 90 and recence <= 180:
    cluster_id = 2
    rfm_label = 'Client Occasionnel Actif'
  elif freq >= 2 and recence <= 180 and montant < 300:
    cluster_id = 3
    rfm_label = 'Client Régulier'
  elif (freq >= 3 or montant >= 300) and recence <= 365:
    cluster_id = 4
    rfm_label = 'Client VIP / Élite RFM'
  else:
    # Recence > 180 (ou > 365 pour les gros) = Client Dormant / Inactif
    cluster_id = 5
    rfm_label = 'Inactif / Risque d\'Attrition'

  # 2. RÈGLES DE TUNNELS MARKETING (Priorité au comportement produit)
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
    segment_metier = 'Client VIP / Grand Acheteur'
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
      'Segment_Metier': segment_metier,
  })


res_seg = df.apply(attribuer_segmentation, axis=1)
df['Deep_Cluster'] = res_seg['Deep_Cluster']
df['RFM_Label'] = res_seg['RFM_Label']
df['Tunnel_Marketing'] = res_seg['Tunnel_Marketing']
df['Segment_Metier'] = res_seg['Segment_Metier']

# --- 6. EXPORT DU FICHIER PROPRE ---
print('Étape 5 : Sauvegarde du fichier final...')
df.to_csv(chemin_sortie_profonde, index=False, encoding='utf-8')
print(
    f'Fichier généré avec succès ({len(df)} contacts) :'
    f' {chemin_sortie_profonde}'
)

# Résumé des Tunnels pour contrôle
print('\n--- REPARTITION DES TUNNELS MARKETING ---')
print(df['Tunnel_Marketing'].value_counts())
print('\n--- REPARTITION DES CLUSTERS ---')
print(df['Deep_Cluster'].value_counts())
