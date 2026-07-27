import os
import numpy as np
import pandas as pd
import gdown
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

# --- 1. CONFIGURATION DES CHEMINS ET TELECHARGEMENT DRIVE ---
dossier_actuel = os.path.dirname(os.path.abspath(__file__))

chemin_rfm = os.path.join(dossier_actuel, 'donnees_boutique_propres_interne.csv')
chemin_transactions = os.path.join(dossier_actuel, 'export_commandes.csv')
chemin_produits = os.path.join(dossier_actuel, 'export_produits_KGI.csv')
chemin_sortie_profonde = os.path.join(
    dossier_actuel, 'donnees_segmentation_profonde.csv'
)

# Téléchargement des fichiers sources depuis Google Drive si les ID sont fournis
drive_id_rfm = os.environ.get('DRIVE_ID_RFM')
drive_id_trans = os.environ.get('DRIVE_ID_TRANS')
drive_id_prod = os.environ.get('DRIVE_ID_PROD')

print('Étape 1 : Téléchargement et chargement des données depuis Google Drive...')


def telecharger_drive(drive_id, chemin_dest):
  """Télécharge un fichier Google Drive en forçant l'export CSV si c'est un Google Sheet."""
  if not drive_id:
    return
  # Lien d'export CSV universel pour Google Sheets
  url_csv = (
      f'https://docs.google.com/spreadsheets/d/{drive_id}/export?format=csv'
  )
  try:
    gdown.download(url_csv, chemin_dest, quiet=False, fuzzy=True)
  except Exception:
    # Fallback sur le lien standard si ce n'est pas un Google Sheet
    url_standard = f'https://drive.google.com/uc?id={drive_id}'
    gdown.download(url_standard, chemin_dest, quiet=False, fuzzy=True)


telecharger_drive(drive_id_rfm, chemin_rfm)
telecharger_drive(drive_id_trans, chemin_transactions)
telecharger_drive(drive_id_prod, chemin_produits)


def charger_fichier(chemin):
  """Charge un fichier qu'il soit au format CSV brut ou Excel/Google Sheet."""
  try:
    return pd.read_csv(chemin, low_memory=False)
  except Exception:
    try:
      return pd.read_excel(chemin)
    except Exception as e:
      raise Exception(
          f"Impossible de lire le fichier '{chemin}'. Vérifiez son format ou son"
          f' contenu. Détails : {e}'
      )


# Chargement des DataFrames
df_rfm = charger_fichier(chemin_rfm)
df_trans = charger_fichier(chemin_transactions)
df_prod = charger_fichier(chemin_produits)


# --- 2. HARMONISATION DE L'EMAIL ---
print('Étape 2 : Harmonisation des adresses e-mails...')
for df in [df_rfm, df_trans]:
  col_email = [
      col
      for col in df.columns
      if 'mail' in col.lower() or 'client' in col.lower()
  ]
  if col_email:
    df.rename(columns={col_email[0]: 'Email'}, inplace=True)

# --- 3. INDEXATION DU CATALOGUE ---
print('Étape 3 : Indexation sémantique et par catégories du catalogue KGI...')
df_prod['post_title_clean'] = (
    df_prod['post_title'].astype(str).str.strip().str.lower()
)
df_prod['row_searchable_text'] = (
    df_prod.fillna('')
    .astype(str)
    .apply(lambda x: ' '.join(x).lower(), axis=1)
)
df_prod['product_cat_clean'] = (
    df_prod['product_cat'].fillna('').astype(str).str.strip().str.lower()
)

df_prod_sorted = df_prod.sort_values(
    by='post_title_clean', key=lambda x: x.str.len(), ascending=False
)
product_lookup = list(
    zip(
        df_prod_sorted['post_title_clean'],
        df_prod_sorted['row_searchable_text'],
        df_prod_sorted['product_cat_clean'],
    )
)

# --- 4. ANALYSE LINGUISTIQUE PROFONDE PAR PRODUIT ---
print(
    'Étape 4 : Analyse linguistique avec arbitrage des volumes et filtres'
    ' métier...'
)

mots_kumite = [
    'gant',
    'kumite',
    'plastron',
    'protection',
    'protege',
    'protèges',
    'pied',
    'combat',
    'coquille',
    'casque',
    'mitaine',
    'shin',
    'guard',
]
mots_kata = [
    'kata',
    'lourd',
    'claquant',
    'traditionnel',
    'gi-lourd',
    'karategi lourd',
    'master',
]
mots_debutant = [
    'initiation',
    'debutant',
    'blanche',
    'jaune',
    'ceinture blanche',
    'ceinture jaune',
    'pack club',
]
mots_enfant = [
    'enfant',
    'enfants',
    'kids',
    'junior',
    'fillette',
    'garconnet',
    'ado',
    'jeune',
    'baby',
    'petit',
    'pack enfant',
    '110cm',
    '120cm',
    '130cm',
    '140cm',
    '150cm',
]
mots_wado = [
    'wado',
    'wado-ryu',
    'wadoryu',
    'wado ryu',
]  # CORRECTION : Mots-clés Wado-Ryu à exclure d'Enfant

df_trans['Nb_Articles_Total'] = 0
df_trans['Nb_Kumite'] = 0
df_trans['Nb_Kata'] = 0
df_trans['Nb_Debutant'] = 0
df_trans['Nb_Enfant'] = 0

colonnes_articles = [f'Nom de l’élément #{i}' for i in range(1, 11)]

for idx, row in df_trans.iterrows():
  for col_art in colonnes_articles:
    if col_art in df_trans.columns:
      val = row[col_art]
      if (
          pd.isna(val)
          or str(val).strip() == ''
          or str(val).lower() in ['nan', 'none']
      ):
        continue

      df_trans.at[idx, 'Nb_Articles_Total'] += 1
      val_clean = str(val).strip().lower()

      row_text = val_clean
      prod_cat = ''
      found = False

      for post_title, row_text_catalog, cat_catalog in product_lookup:
        if post_title and val_clean.startswith(post_title):
          row_text = row_text_catalog
          prod_cat = cat_catalog
          found = True
          break

      is_enfant = False
      is_kumite = False
      is_debutant = False
      is_kata = False
      is_wado = any(
          w in val_clean or w in row_text for w in mots_wado
      )  # Détection Wado-Ryu

      # Catégories officielles
      if found and prod_cat != '':
        if any(
            x in prod_cat for x in ['enfant', 'enfants', 'kids', 'junior']
        ):
          is_enfant = True
        if any(x in prod_cat for x in ['kumite', 'combat']):
          is_kumite = True
        if any(x in prod_cat for x in ['debutant', 'initiation']):
          is_debutant = True
        if 'kata' in prod_cat:
          is_kata = True

      # Mots-clés subsidiaires
      if not is_enfant and any(mot in val_clean for mot in mots_enfant):
        is_enfant = True
      if not is_debutant and any(mot in row_text for mot in mots_debutant):
        is_debutant = True
      if not is_kumite and any(mot in row_text for mot in mots_kumite):
        is_kumite = True
      if not is_kata and any(mot in row_text for mot in mots_kata):
        is_kata = True

      # CORRECTION : Si c'est du Wado-Ryu, on retire strictement le flag Enfant
      if is_wado:
        is_enfant = False

      # Incrémentation des compteurs
      if is_enfant:
        df_trans.at[idx, 'Nb_Enfant'] += 1
      if is_kumite:
        df_trans.at[idx, 'Nb_Kumite'] += 1
      if is_debutant:
        df_trans.at[idx, 'Nb_Debutant'] += 1
      if is_kata:
        df_trans.at[idx, 'Nb_Kata'] += 1

# --- 5. AGRÉGATION ET ARBITRAGE DU VOLUME PAR CLIENT ---
print(
    'Étape 5 : Agrégation et arbitrage final des volumes (Kumite/Kata >'
    ' Enfant)...'
)
df_produits_clients = (
    df_trans.groupby('Email')
    .agg({
        'Nb_Articles_Total': 'sum',
        'Nb_Kumite': 'sum',
        'Nb_Kata': 'sum',
        'Nb_Debutant': 'sum',
        'Nb_Enfant': 'sum',
    })
    .reset_index()
)

# Arbitrage : Si Kumite ou Kata >= Enfant, on annule le flag Enfant
mask_arbitrage = (df_produits_clients['Nb_Enfant'] > 0) & (
    (df_produits_clients['Nb_Kumite'] >= df_produits_clients['Nb_Enfant'])
    | (df_produits_clients['Nb_Kata'] >= df_produits_clients['Nb_Enfant'])
)
df_produits_clients.loc[mask_arbitrage, 'Nb_Enfant'] = 0

# Calcul des ratios réels
df_produits_clients['Part_Kumite'] = (
    df_produits_clients['Nb_Kumite'] / df_produits_clients['Nb_Articles_Total']
).fillna(0.0)
df_produits_clients['Part_Kata'] = (
    df_produits_clients['Nb_Kata'] / df_produits_clients['Nb_Articles_Total']
).fillna(0.0)
df_produits_clients['Part_Debutant'] = (
    df_produits_clients['Nb_Debutant']
    / df_produits_clients['Nb_Articles_Total']
).fillna(0.0)
df_produits_clients['Part_Enfant'] = (
    df_produits_clients['Nb_Enfant'] / df_produits_clients['Nb_Articles_Total']
).fillna(0.0)

df_produits_clients.drop(
    columns=['Nb_Kumite', 'Nb_Kata', 'Nb_Debutant', 'Nb_Enfant'], inplace=True
)

# --- 6. FUSION RFM ---
print("Étape 6 : Jointure finale des données de valeur (RFM) et d'affinité...")
df_complet = pd.merge(df_rfm, df_produits_clients, on='Email', how='left')

col_recence = (
    'Recence_Jours' if 'Recence_Jours' in df_complet.columns else 'Recence'
)
col_frequence = (
    'Commandes' if 'Commandes' in df_complet.columns else 'Frequence'
)
col_montant = (
    'Dépense totale' if 'Dépense totale' in df_complet.columns else 'Montant'
)

df_complet[col_frequence] = (
    pd.to_numeric(df_complet[col_frequence], errors='coerce').fillna(0).astype(int)
)
df_complet[col_montant] = pd.to_numeric(
    df_complet[col_montant], errors='coerce'
).fillna(0.0)
df_complet[col_recence] = (
    pd.to_numeric(df_complet[col_recence], errors='coerce')
    .fillna(999)
    .astype(int)
)

for col in ['Part_Kumite', 'Part_Kata', 'Part_Debutant', 'Part_Enfant']:
  df_complet[col] = df_complet[col].fillna(0.0)

# --- 7. APPLICATION DES FILTRES COHORTE HYBRIDE ---
print('Étape 7 : Application des règles métier prioritaires...')
df_complet['Segment_Metier'] = 'A_Classer'
df_complet['Tunnel_Marketing'] = 'A_Classer'
df_complet['Deep_Cluster'] = -1

# CORRECTION : Prospects / Non-acheteurs strictly isolés dans le Cluster 0
mask_sans_achat = df_complet[col_frequence] == 0
df_complet.loc[mask_sans_achat, 'Segment_Metier'] = 'Prospect Sans Achat'
df_complet.loc[mask_sans_achat, 'Tunnel_Marketing'] = (
    'tunnel_prospect_sans_achat'
)
df_complet.loc[mask_sans_achat, 'Deep_Cluster'] = 0

# Filtre Enfant Déterministe (Cluster 1)
mask_enfant = (df_complet[col_frequence] > 0) & (
    df_complet['Part_Enfant'] > 0.0
)
df_complet.loc[mask_enfant, 'Segment_Metier'] = 'Équipement Enfant'
df_complet.loc[mask_enfant, 'Tunnel_Marketing'] = 'tunnel_enfant'
df_complet.loc[mask_enfant, 'Deep_Cluster'] = 1

# --- 8. STANDARDISATION ET K-MEANS DYNAMIQUE ---
print('Étape 8 : Normalisation et K-Means avec attribution dynamique...')
df_a_clusteriser = df_complet[df_complet['Segment_Metier'] == 'A_Classer'].copy()

if len(df_a_clusteriser) > 0:
  seuil_montant = df_a_clusteriser[col_montant].quantile(0.99)
  seuil_freq = df_a_clusteriser[col_frequence].quantile(0.99)

  df_a_clusteriser['Montant_Clean'] = np.clip(
      df_a_clusteriser[col_montant], 0, seuil_montant
  )
  df_a_clusteriser['Frequence_Clean'] = np.clip(
      df_a_clusteriser[col_frequence], 0, seuil_freq
  )
  df_a_clusteriser['Recence_Clean'] = df_a_clusteriser[col_recence]

  features_clustering = [
      'Recence_Clean',
      'Frequence_Clean',
      'Montant_Clean',
      'Part_Kumite',
      'Part_Kata',
      'Part_Debutant',
  ]

  scaler = StandardScaler()
  donnees_standardisees = scaler.fit_transform(
      df_a_clusteriser[features_clustering].fillna(0)
  )

  pca = PCA(n_components=3, random_state=42)
  donnees_pca = pca.fit_transform(donnees_standardisees)

  # Clustering sur 4 groupes restants (Clusters 2 à 5)
  kmeans = KMeans(
      n_clusters=4, init='k-means++', max_iter=300, random_state=42
  )
  labels_bruts = kmeans.fit_predict(donnees_pca)

  #
  df_a_clusteriser['temp_cluster'] = labels_bruts
  stats_clusters = (
      df_a_clusteriser.groupby('temp_cluster')
      .agg({
          'Montant_Clean': 'mean',
          'Frequence_Clean': 'mean',
          'Recence_Clean': 'mean',
          'Part_Kumite': 'mean',
          'Part_Debutant': 'mean',
      })
      .reset_index()
  )

  # Tri dynamique pour identifier physiquement la valeur des clusters
  # 1. Cluster avec la plus forte affinité Kumite
  id_kumite = stats_clusters.sort_values(
      by='Part_Kumite', ascending=False
  ).iloc[0]['temp_cluster']

  # 2. Parmi le reste, le cluster avec la plus forte valeur client (Montant + Fréquence) -> Elite / Pro
  reste_1 = stats_clusters[stats_clusters['temp_cluster'] != id_kumite]
  id_elite = reste_1.sort_values(
      by=['Montant_Clean', 'Frequence_Clean'], ascending=[False, False]
  ).iloc[0]['temp_cluster']

  # 3. Parmi le reste, le cluster avec la récence la plus ancienne (> inactifs/dormants)
  reste_2 = reste_1[reste_1['temp_cluster'] != id_elite]
  id_dormant = reste_2.sort_values(by='Recence_Clean', ascending=False).iloc[0][
      'temp_cluster'
  ]

  # 4. Le dernier cluster restant -> Nouveaux / Impulsifs / Débutants
  reste_3 = reste_2[reste_2['temp_cluster'] != id_dormant]
  id_debutant = reste_3.iloc[0]['temp_cluster']

  # Dictionnaire de correspondance dynamique strict
  map_dynamique = {
      id_dormant: (
          2,
          'Réserve Occasionnelle Dormante',
          'tunnel_defaut',
      ),
      id_debutant: (
          3,
          'L\'Académie des Débutants & Initiation',
          'tunnel_debutant',
      ),
      id_elite: (
          4,
          'Dojo Premium, Enseignants & Clubs Élite',
          'tunnel_elite_pro',
      ),
      id_kumite: (
          5,
          'Les Compétiteurs Combat & Passionnés Kumite',
          'tunnel_kumite',
      ),
  }

  # Application du mappage dynamique
  for c_temp, (c_id_final, nom_metier, nom_tunnel) in map_dynamique.items():
    mask_c = df_a_clusteriser['temp_cluster'] == c_temp
    df_a_clusteriser.loc[mask_c, 'Deep_Cluster'] = c_id_final
    df_a_clusteriser.loc[mask_c, 'Segment_Metier'] = nom_metier
    df_a_clusteriser.loc[mask_c, 'Tunnel_Marketing'] = nom_tunnel

  #
  cols_update = ['Segment_Metier', 'Tunnel_Marketing', 'Deep_Cluster']
  df_complet.loc[df_a_clusteriser.index, cols_update] = df_a_clusteriser[
      cols_update
  ]

# Nettoyage et formatage des colonnes RFM de sortie
df_complet['Montant_Clean'] = df_complet[col_montant].round(2)
df_complet['Frequence_Clean'] = df_complet[col_frequence]
df_complet['Recence_Clean'] = df_complet[col_recence]

# --- 9. EXPORTATION DES DONNÉES ---
print("Étape 9 : Préparation de l'exportation finale des données segmentées...")
df_complet = df_complet.reset_index(drop=True)
df_complet['Identifiant'] = [
    f'client_{i}' for i in range(1, len(df_complet) + 1)
]
df_complet.to_csv(chemin_sortie_profonde, index=False, float_format='%.2f')
print(
    '-> Succès ! Fichier d\'analyse profonde généré :'
    f' {chemin_sortie_profonde}'
)

# --- 10. RAPPORT SYNTHÉTIQUE ---
print('\n=== RECONSTRUCTION DES SEGMENTS METIERS HYBRIDES ===')
profils_synthese = (
    df_complet.groupby(['Deep_Cluster', 'Segment_Metier', 'Tunnel_Marketing'])
    .agg({
        'Identifiant': 'count',
        'Recence_Clean': 'mean',
        'Frequence_Clean': 'mean',
        'Montant_Clean': 'mean',
        'Part_Kumite': 'mean',
        'Part_Enfant': 'mean',
    })
    .rename(columns={'Identifiant': 'Nombre_Clients'})
)

print(profils_synthese.to_string())
