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
df_prod = charger_fichier(chemin_produits)

# --- 2. NETTOYAGE STRICT ET CROISEMENT AVEC EXPORT PRODUITS ---
def normaliser_texte(texte):
    if pd.isna(texte): return ""
    texte = str(texte).lower()
    texte = unicodedata.normalize('NFD', texte).encode('ascii', 'ignore').decode('utf-8')
    return texte

# Détection dynamique des colonnes Produit, Catégorie et Email dans df_trans
col_prod_trans = next((c for c in df_trans.columns if any(k in c.lower() for k in ['nom', 'produit', 'item', 'lineitem'])), df_trans.columns[0])
col_cat_trans = next((c for c in df_trans.columns if any(k in c.lower() for k in ['categorie', 'category', 'cat'])), None)
col_email_trans = next((c for c in df_trans.columns if 'email' in c.lower() or 'mail' in c.lower()), df_trans.columns[0])

df_trans['Email_Clean'] = df_trans[col_email_trans].astype(str).str.strip().str.lower()
df_trans['Produit_Clean'] = df_trans[col_prod_trans].apply(normaliser_texte)
df_trans['Categorie_Clean'] = df_trans[col_cat_trans].apply(normaliser_texte) if col_cat_trans else ""

# Détection et jointure de la colonne product_cat issue du fichier export_produits_KGI.csv
col_prod_cat_prod = next((c for c in df_prod.columns if 'product_cat' in c.lower() or 'cat' in c.lower()), None)
col_prod_name_prod = next((c for c in df_prod.columns if any(k in c.lower() for k in ['post_name', 'nom', 'produit', 'title', 'item', 'id'])), df_prod.columns[0])

if col_prod_cat_prod:
    df_prod['Produit_Clean_Match'] = df_prod[col_prod_name_prod].apply(normaliser_texte)
    df_prod['Product_Cat_Clean'] = df_prod[col_prod_cat_prod].apply(normaliser_texte)
    
    df_prod_unique = df_prod[['Produit_Clean_Match', 'Product_Cat_Clean']].drop_duplicates(subset=['Produit_Clean_Match'])
    df_trans = pd.merge(df_trans, df_prod_unique, left_on='Produit_Clean', right_on='Produit_Clean_Match', how='left')
    df_trans['Product_Cat_Clean'] = df_trans['Product_Cat_Clean'].fillna("")
else:
    df_trans['Product_Cat_Clean'] = ""

# --- 3. DÉTECTION DES PRODUITS ET CATÉGORIES (SANS ACCENTS) ---

# KUMITE / COMBAT
MOTS_KUMITE = [
    'kumite', 'combat', 'combattant', 'protection', 'plastron', 'plastron femme', 
    'poitrine', 'buste', 'gant', 'gants', 'patte d\'ours', 'pattes d\'ours', 
    'bouclier', 'casque', 'masque', 'coque', 'coquille', 'pitaine', 'pitaines', 
    'mitaine', 'mitaines', 'protege dent', 'protege dents', 'protege-dent', 
    'protege-dents', 'protegedent', 'protege tibia', 'tibia', 'dents', 'protege-tibia', 'protegetibia', 
    'tibias-pieds', 'tibia-pied', 'protege pied', 'chevillere', 'karate gi kumite', 
    'red belt', 'blue belt', 'reversible', 'cible', 'cibles', 'pao', 'paos', 
    'frappe', 'sac de frappe', 'mannequin'
]

# KATA / ÉLITE
EXCLUSIONS_KATA = [
    'kodomo', 'shoshin', 'bicolore', 'jaune', 'orange', 'verte', 'standard',
    'marron', 'junior', 'enfant', 'initiation', 'ceinture blanche', 'debutant', 
    'premier prix', 'eco', 'decouverte', 'entrainement', 'kids', 'baby', 
    '100cm', '110cm', '120cm'
]

MOTS_KATA = [
    'master', 'grand master', 'expert', 'kata', 'competition', 'champion', 
    'premium', 'sensei', 'coach', 'instructeur', 'dan', 'sur-mesure', 'broderie', 'brode',
    'tokyodo', 'hirota', 'seishin', 'tokaido', 'shureido',
    'ceinture noire', 'ceinture rouge et blanche', 'ceinture rouge/blanche', 'soie', 'satin'
]

# DÉBUTANT
EXCLUSIONS_DEBUTANT = [
    'ceinture noire', 'ceinture rouge et blanche', 'ceinture rouge/blanche', 
    'master', 'expert', 'competition', 'champion', 'premium', 'sensei', 
    'tokyodo', 'hirota', 'shureido'
]

MOTS_DEBUTANT = [
    'shoshin', 'initiation', 'debutant', 'debutants', 'decouverte', 
    'premier prix', 'eco', 'economique',
    'ceinture bicolore', 'blanche/jaune', 'jaune/orange', 'orange/verte', 
    'verte/bleue', 'bleue/marron'
]

# ENFANT
MOTS_ENFANT = [
    'enfant', 'enfants', 'junior', 'kodomo', 'kids', 'baby', 'pupille', 'poussin', 
    'minime', 'taille enfant', 'kimono enfant', '100cm', '110cm', '120cm', '130cm', '140cm', '150cm'
]

# Remplacer la logique d'analyse dans analyser_achats_client par :
def analyser_achats_client(df_group):
    is_yoseikan = False
    is_nanbudo = False
    is_kobudo = False
    is_enfant = False
    is_kumite = False
    is_kata = False
    is_debutant = False

    for _, row in df_group.iterrows():
        # 1. Extraction et nettoyage de tous les textes disponibles
        p_cat = str(row.get('Product_Cat_Clean', ''))
        p_name = str(row.get('Produit_Clean', ''))
        c_clean = str(row.get('Categorie_Clean', ''))

        # Découpage des catégories séparées par des virgules
        categories_decoupees = [cat.strip().lower() for cat in p_cat.split(',')]
        categories_secondaires = [cat.strip().lower() for cat in c_clean.split(',')]
        
        # On fusionne tout en un grand ensemble de mots/phrases nettoyés
        tous_les_textes = categories_decoupees + categories_secondaires + [p_name.lower()]
        texte_brut_combine = " ".join(tous_les_textes)

        # 2. VÉRIFICATION ENFANT (Priorité Mots-Clés + Tailles)
        if any(m in texte_brut_combine for m in MOTS_ENFANT):
            is_enfant = True

        # 3. VÉRIFICATION KUMITE / COMBAT
        if any(m in texte_brut_combine for m in MOTS_KUMITE):
            is_kumite = True

        # 4. VÉRIFICATION KATA (avec exclusions)
        if any(m in texte_brut_combine for m in MOTS_KATA):
            if not any(ex in texte_brut_combine for ex in EXCLUSIONS_KATA):
                is_kata = True

        # 5. VÉRIFICATION DÉBUTANT (avec exclusions)
        if any(m in texte_brut_combine for m in MOTS_DEBUTANT):
            if not any(ex in texte_brut_combine for ex in EXCLUSIONS_DEBUTANT):
                is_debutant = True

        # 6. DISCIPLINES SPÉCIFIQUES
        if 'yoseikan' in texte_brut_combine: is_yoseikan = True
        if 'nanbudo' in texte_brut_combine: is_nanbudo = True
        if 'kobudo' in texte_brut_combine: is_kobudo = True

    return pd.Series({
        'has_yoseikan': is_yoseikan,
        'has_nanbudo': is_nanbudo,
        'has_kobudo': is_kobudo,
        'has_enfant': is_enfant,
        'has_kumite': is_kumite,
        'has_kata': is_kata,
        'has_debutant': is_debutant
    })
achats_par_client = df_trans.groupby('Email_Clean').apply(analyser_achats_client)

# Ligne de diagnostic rapide
print("ÉCHANTILLON D'ANALYSE TEXTE :")
print(df_trans[['Produit_Clean', 'Product_Cat_Clean', 'Categorie_Clean']].head(10))

# --- 4. PREPARATION RFM ET FUSION ---
col_email_rfm = next((c for c in df_rfm.columns if 'email' in c.lower() or 'mail' in c.lower()), df_rfm.columns[0])
df_rfm['Email'] = df_rfm[col_email_rfm].astype(str).str.strip().str.lower()

# S'assurer que l'index de 'achats_par_client' est aussi propre
achats_par_client.index = achats_par_client.index.astype(str).str.strip().str.lower()

df = pd.merge(df_rfm, achats_par_client, left_on='Email', right_index=True, how='left')

for col in ['has_yoseikan', 'has_nanbudo', 'has_kobudo', 'has_enfant', 'has_kumite', 'has_kata', 'has_debutant']:
    df[col] = df[col].fillna(False)

col_orders = next((c for c in df.columns if any(k in c.lower() for k in ['commandes', 'orders', 'frequence'])), None)
col_amount = next((c for c in df.columns if any(k in c.lower() for k in ['montant', 'total', 'ca', 'valeur'])), None)
col_recency = next((c for c in df.columns if any(k in c.lower() for k in ['recence', 'derniere', 'days'])), None)

df['Frequence_Clean'] = pd.to_numeric(df[col_orders], errors='coerce').fillna(0).astype(int) if col_orders else 0
df['Montant_Clean'] = pd.to_numeric(df[col_amount], errors='coerce').fillna(0.0).astype(float) if col_amount else 0.0
df['Recence_Clean'] = pd.to_numeric(df[col_recency], errors='coerce').fillna(999).astype(int) if col_recency else 999

# --- 5. RÈGLES DE SEGMENTATION INDÉPENDANTES ET HIÉRARCHISATION ---
def attribuer_segmentation(row):
    freq = row['Frequence_Clean']
    montant = row['Montant_Clean']
    recence = row['Recence_Clean']

    # 1. CALCUL DU LABEL RFM (Strictement freq == 0 pour Prospect Non Converti)
    if freq == 0:
        rfm_label = "Prospect Non Converti"
    elif freq == 1 and recence <= 90:
        rfm_label = "Nouveau Client Récent"
    elif freq == 1 and 90 < recence <= 240:
        rfm_label = "Client Occasionnel"
    elif (freq >= 3 or montant >= 1000) and recence <= 365:
        rfm_label = "Client VIP"
    elif freq >= 2 and recence <= 240 and montant < 1000:
        rfm_label = "Client Régulier"
    else:
        rfm_label = "Inactif / Risque"

    # 2. CALCUL DE LA SPÉCIALITÉ UNIQUE (HIÉRARCHIE STRICTE - Général tout en bas)
    if row['has_yoseikan']:
        specialite = "Yoseikan Budo"
    elif row['has_nanbudo']:
        specialite = "Nanbudo"
    elif row['has_kobudo']:
        specialite = "Kobudo"
    elif row['has_enfant']:
        specialite = "Enfant"
    elif row['has_kumite']:
        specialite = "Kumite"
    elif row['has_kata']:
        specialite = "Kata"
    elif row['has_debutant']:
        specialite = "Débutant"
    else:
        specialite = "Général"

    return pd.Series({
        'RFM_Label': rfm_label,
        'Specialite_Produit': specialite
    })

res_seg = df.apply(attribuer_segmentation, axis=1)
df['RFM_Label'] = res_seg['RFM_Label']
df['Specialite_Produit'] = res_seg['Specialite_Produit']

# --- 6. SAUVEGARDE STRICTE DES COLONNES UTILES ---
df_export = df[['Email', 'RFM_Label', 'Specialite_Produit']]

df_export.to_csv(chemin_sortie, index=False, encoding='utf-8')

print(f"Fichier de segmentation mis à jour : {chemin_sortie}")
print("\n--- RÉPARTITION RFM ---")
print(df_export['RFM_Label'].value_counts())
print("\n--- RÉPARTITION SPÉCIALITÉS ---")
print(df_export['Specialite_Produit'].value_counts())
print("\n=== DIAGNOSTIC AVANT EXPORT ===")
print(df['Specialite_Produit'].value_counts())
