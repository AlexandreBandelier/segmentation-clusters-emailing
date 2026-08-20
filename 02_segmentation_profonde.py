import os
import sys
import unicodedata
import pandas as pd
import numpy as np
import gdown
import re

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

# --- 2. DICTIONNAIRES ET MOTS-CLÉS ---
MAPPING_DOMAINES = {
    'karate-gi.fr': ('FR', 'fr'), '.be': ('BE', 'fr'),
    '.es': ('ES', 'es'), '.it': ('IT', 'it'),
    '.dk': ('DK', 'da'), '.de': ('DE', 'de'),
    '.eu': ('EU', 'en'), '.nl': ('NL', 'nl')
}

MOTS_CLUB = ['club', 'association', 'asso', 'comite', 'ligue', 'dojo', 'fédération', 'federation', 'section', 'bde', 'mairie']
MOTS_KUMITE = ['kumite', 'combat', 'combattant', 'protection', 'plastron', 'plastron femme', 'poitrine', 'buste', 'gant', 'gants', 'patte d\'ours', 'pattes d\'ours', 'bouclier', 'casque', 'masque', 'coque', 'coquille', 'pitaine', 'pitaines', 'mitaine', 'mitaines', 'protege dent', 'protege dents', 'protege-dent', 'protege-dents', 'protegedent', 'protege tibia', 'tibia', 'dents', 'protege-tibia', 'protegetibia', 'tibias-pieds', 'tibia-pied', 'protege pied', 'chevillere', 'karate gi kumite', 'red belt', 'blue belt', 'reversible', 'cible', 'cibles', 'pao', 'paos', 'frappe', 'sac de frappe', 'mannequin']
MOTS_KATA = ['master', 'grand master', 'expert', 'kata', 'competition', 'champion', 'premium', 'sensei', 'coach', 'instructeur', 'dan', 'sur-mesure', 'broderie', 'brode', 'tokyodo', 'hirota', 'seishin', 'tokaido', 'shureido', 'ceinture noire', 'ceinture rouge et blanche', 'ceinture rouge/blanche', 'soie', 'satin']
EXCLUSIONS_KATA = ['kodomo', 'shoshin', 'bicolore', 'jaune', 'orange', 'verte', 'standard', 'marron', 'junior', 'enfant', 'initiation', 'ceinture blanche', 'debutant', 'premier prix', 'eco', 'decouverte', 'entrainement', 'kids', 'baby', '100cm', '110cm', '120cm']
MOTS_DEBUTANT = ['shoshin', 'initiation', 'debutant', 'debutants', 'decouverte', 'premier prix', 'eco', 'economique', 'ceinture bicolore', 'blanche/jaune', 'jaune/orange', 'orange/verte', 'verte/bleue', 'bleue/marron']
EXCLUSIONS_DEBUTANT = ['ceinture noire', 'ceinture rouge et blanche', 'ceinture rouge/blanche', 'master', 'expert', 'competition', 'champion', 'premium', 'sensei', 'tokyodo', 'hirota', 'shureido']
MOTS_ENFANT = ['enfant', 'enfants', 'junior', 'kodomo', 'kids', 'baby', 'pupille', 'poussin', 'minime', 'taille enfant', 'kimono enfant', '100cm', '110cm', '120cm', '130cm', '140cm', '150cm']

def to_regex(liste):
    """Convertit une liste de mots en expression régulière rapide."""
    return r'(?:' + '|'.join(map(re.escape, liste)) + r')'

# --- 3. NETTOYAGE ET PRÉPARATION ---
def normaliser_texte(texte):
    if pd.isna(texte): return ""
    return unicodedata.normalize('NFD', str(texte).lower()).encode('ascii', 'ignore').decode('utf-8')

col_email_trans = "E-mail (Facturation)"
col_prod_trans = next((c for c in df_trans.columns if "Nom de l" in c), None)
col_qte_trans = next((c for c in df_trans.columns if "quantit" in c.lower() or "qty" in c.lower()), None)
col_url_trans = next((c for c in df_trans.columns if any(k in c.lower() for k in ["url", "site", "domaine", "origine"])), None)

df_trans['Email_Clean'] = df_trans[col_email_trans].astype(str).str.strip().str.lower()
df_trans['Produit_Clean'] = df_trans[col_prod_trans].apply(normaliser_texte) if col_prod_trans else ""
df_trans['Quantite'] = pd.to_numeric(df_trans[col_qte_trans], errors='coerce').fillna(1) if col_qte_trans else 1
df_trans['URL_Origine'] = df_trans[col_url_trans].astype(str).str.lower() if col_url_trans else "karate-gi.fr"

# Fusion Produit pour récupérer les catégories
if 'product_cat' in df_prod.columns and 'post_title' in df_prod.columns:
    df_prod_unique = df_prod[['post_title', 'product_cat']].dropna().copy()
    df_prod_unique['Produit_Match'] = df_prod_unique['post_title'].apply(normaliser_texte)
    df_prod_unique['Cat_Match'] = df_prod_unique['product_cat'].apply(normaliser_texte)
    df_prod_unique = df_prod_unique.drop_duplicates(subset=['Produit_Match'])
    
    df_trans = pd.merge(df_trans, df_prod_unique[['Produit_Match', 'Cat_Match']], left_on='Produit_Clean', right_on='Produit_Match', how='left')
    df_trans['Product_Cat_Clean'] = df_trans['Cat_Match'].fillna("")
else:
    df_trans['Product_Cat_Clean'] = ""

# OPTIMISATION 1 : Agrégation des textes et quantités par email
df_trans['Texte_Ligne'] = df_trans['Produit_Clean'] + " " + df_trans['Product_Cat_Clean']
df_grouped = df_trans.groupby('Email_Clean').agg({
    'Texte_Ligne': lambda x: ' '.join(x),
    'Quantite': 'sum',
    'URL_Origine': 'first'
}).reset_index()

# Détection PAYS / LANGUE
def detecter_pays_langue(url):
    for ext, (pays, langue) in MAPPING_DOMAINES.items():
        if ext in url:
            return pays, langue
    return 'FR', 'fr'

df_grouped[['Pays', 'Langue']] = pd.DataFrame(df_grouped['URL_Origine'].apply(detecter_pays_langue).tolist(), index=df_grouped.index)

# OPTIMISATION 2 : Détection des Spécialités via Regex Vectorisées
textes = df_grouped['Texte_Ligne']

df_grouped['has_club'] = textes.str.contains(to_regex(MOTS_CLUB), regex=True) | (df_grouped['Quantite'] >= 10)
df_grouped['has_enfant'] = textes.str.contains(to_regex(MOTS_ENFANT), regex=True)
df_grouped['has_kumite'] = textes.str.contains(to_regex(MOTS_KUMITE), regex=True)

df_grouped['has_kata'] = textes.str.contains(to_regex(MOTS_KATA), regex=True) & ~textes.str.contains(to_regex(EXCLUSIONS_KATA), regex=True)
df_grouped['has_debutant'] = textes.str.contains(to_regex(MOTS_DEBUTANT), regex=True) & ~textes.str.contains(to_regex(EXCLUSIONS_DEBUTANT), regex=True)

df_grouped['has_yoseikan'] = textes.str.contains('yoseikan')
df_grouped['has_nanbudo'] = textes.str.contains('nanbudo')
df_grouped['has_kobudo'] = textes.str.contains('kobudo')

# --- 4. FUSION AVEC LA BASE RFM ---
col_email_rfm = next((c for c in df_rfm.columns if 'email' in c.lower() or 'mail' in c.lower()), df_rfm.columns[0])
df_rfm['Email'] = df_rfm[col_email_rfm].astype(str).str.strip().str.lower()

df = pd.merge(df_rfm, df_grouped, left_on='Email', right_on='Email_Clean', how='left')

col_orders = next((c for c in df.columns if any(k in c.lower() for k in ['commandes', 'orders', 'frequence'])), None)
col_amount = next((c for c in df.columns if any(k in c.lower() for k in ['montant', 'total', 'ca', 'valeur'])), None)
col_recency = next((c for c in df.columns if any(k in c.lower() for k in ['recence', 'derniere', 'days'])), None)

df['Frequence_Clean'] = pd.to_numeric(df[col_orders], errors='coerce').fillna(0).astype(int) if col_orders else 0
df['Montant_Clean'] = pd.to_numeric(df[col_amount], errors='coerce').fillna(0.0).astype(float) if col_amount else 0.0
df['Recence_Clean'] = pd.to_numeric(df[col_recency], errors='coerce').fillna(999).astype(int) if col_recency else 999

# --- 5. ATTRIBUTION VECTORISÉE (OPTIMISATION 3) ---

# Conditions RFM
cond_rfm = [
    (df['Frequence_Clean'] == 0),
    (df['Frequence_Clean'] == 1) & (df['Recence_Clean'] <= 90),
    (df['Frequence_Clean'] == 1) & (df['Recence_Clean'] > 90) & (df['Recence_Clean'] <= 240),
    ((df['Frequence_Clean'] >= 3) | (df['Montant_Clean'] >= 1000)) & (df['Recence_Clean'] <= 365),
    (df['Frequence_Clean'] >= 2) & (df['Recence_Clean'] <= 240) & (df['Montant_Clean'] < 1000)
]
choix_rfm = ["Prospect Non Converti", "Nouveau Client Récent", "Client Occasionnel", "Client VIP", "Client Régulier"]
df['RFM_Label'] = np.select(cond_rfm, choix_rfm, default="Inactif / Risque")

# Conditions Spécialité (Hiérarchie : Club est prioritaire)
cond_spec = [
    (df['has_club'] == True),
    (df['has_yoseikan'] == True),
    (df['has_nanbudo'] == True),
    (df['has_kobudo'] == True),
    (df['has_enfant'] == True),
    (df['has_kumite'] == True),
    (df['has_kata'] == True),
    (df['has_debutant'] == True)
]
choix_spec = ["Club", "Yoseikan Budo", "Nanbudo", "Kobudo", "Enfant", "Kumite", "Kata", "Débutant"]
df['Specialite_Produit'] = np.select(cond_spec, choix_spec, default="Général")

# Sécuriser Pays et Langue pour les prospects sans commande
df['Pays'] = df['Pays'].fillna('FR')
df['Langue'] = df['Langue'].fillna('fr')

# --- 6. EXPORT FINAL ---
# Les 5 colonnes nécessaires pour le script Brevo !
df_export = df[['Email', 'RFM_Label', 'Specialite_Produit', 'Pays', 'Langue']]
df_export.to_csv(chemin_sortie, index=False, encoding='utf-8')

print(f"Fichier de segmentation mis à jour avec Pays/Langue et Clubs : {chemin_sortie}")
print("\n--- RÉPARTITION PAYS ---")
print(df_export['Pays'].value_counts())
print("\n--- RÉPARTITION SPÉCIALITÉS (Top 5) ---")
print(df_export['Specialite_Produit'].value_counts().head(5))
