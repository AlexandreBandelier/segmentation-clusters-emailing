# Pipeline de segmentation et synchronisation emailing (WooCommerce vers Brevo)

Ce dépôt contient le système automatisé de traitement des données clients récupérant les exports de la boutique (commandes et catalogue) avant d'appliquer la segmentation marketing (suivant des critères logiques fixes), puis de mettre à jour les fiches contacts dans Brevo avec leurs nouveaux attributs pour l'emailing.

---

## Fichiers du Projet

* **`02_segmentation_profonde.py`** : Script principal de traitement de la donnée. Il télécharge les fichiers sources depuis Google Drive (`donnees_boutique_propres_interne.csv`, `export_commandes.csv`, `export_produits_KGI.csv`), nettoie les données, applique les règles métier (RFM et spécialités/pratiques du client dans le sport en question) et génère le fichier local `donnees_segmentation_profonde.csv`.
* **`03_synchronisation__brevo.py`** : Script d'intégration API. Il lit le fichier `donnees_segmentation_profonde.csv` généré par le script précédent et pousse les valeurs `RFM_LABEL` et `SPECIALITE_PRODUIT` vers l'API Brevo pour chaque adresse email.
* **`.github/workflows/bravo-main2.yml`** : Fichier de configuration GitHub Actions qui orchestre l'exécution automatisée quotidienne des deux scripts Python.
* **`requirements.txt`** : Liste stricte des dépendances Python nécessaires à l'exécution du pipeline (pandas, numpy, scikit-learn, sib-api-v3-sdk, gdown, python-dotenv, openpyxl).
* **`.gitignore`** : Fichier excluant les données sensibles, les fichiers `.csv` locaux et les environnements virtuels du suivi de version Git.

---

## Logique de Segmentation

Le pipeline génère deux dimensions d'analyse indépendantes qui sont ensuite injectées dans Brevo.

### 1. Label RFM (Comportement et Valeur)
Chaque contact reçoit un label unique basé sur sa fréquence d'achat (F), le montant total dépensé (M) et la récence de son dernier achat (R). L'attribution suit cet ordre de priorité :

1. **Prospect Non Converti** : 0 commande validée.
2. **Nouveau Client Récent** : 1 commande unique effectuée il y a 90 jours ou moins.
3. **Client Occasionnel** : 1 commande unique effectuée entre 91 et 240 jours.
4. **Client VIP** : Au moins 3 commandes OU un total dépensé de 1000 euros ou plus, avec un dernier achat datant de 365 jours maximum.
5. **Client Régulier** : Au moins 2 commandes, total dépensé inférieur à 1000 euros, et dernier achat datant de 240 jours maximum.
6. **Inactif / Risque** : Tout client existant dont le dernier achat remonte à plus de 240 jours (ou plus de 365 jours s'il était VIP).

### 2. Spécialité Produit (Appétence)
Une spécialité unique est attribuée à chaque client en fonction de l'historique de ses achats. Le système vérifie en priorité absolue la classification officielle du catalogue (`product_cat` dans `export_produits_KGI.csv`), puis se rabat sur une analyse par mots-clés du nom du produit si nécessaire (si aucun mot-clé pertinent n'est identifié dans la catégorie du produit). Dans ce cas, la recherche de mot-clé se concentre sur la dénomination du produit. 

L'attribution suit cette hiérarchie stricte d'écrasement :

1. **Yoseikan Budo**
2. **Nanbudo**
3. **Kobudo**
4. **Enfant**
5. **Kumite**
6. **Kata**
7. **Débutant**
8. **Général** (Attribué par défaut ou si le panier ne contient que des articles neutres).

---

## Configuration et Prérequis

Pour que le pipeline fonctionne correctement via GitHub Actions ou en local, les variables d'environnement suivantes doivent impérativement être configurées (via un fichier `.env` local ou dans les **Secrets** de GitHub) :

| Variable | Description |
| :--- | :--- |
| **`DRIVE_ID_RFM`** | ID du fichier Google Drive contenant la base interne propre. |
| **`DRIVE_ID_TRANS`** | ID du fichier Google Drive contenant l'export brut des commandes. |
| **`DRIVE_ID_PROD`** | ID du fichier Google Drive contenant le catalogue produits complet. |
| **`BREVO_API_KEY`** | Clé API v3 de Brevo disposant des droits de modification des contacts. |

> **Note importante concernant Brevo :** Les attributs `RFM_LABEL` et `SPECIALITE_PRODUIT` doivent obligatoirement être créés manuellement en tant qu'attributs de type "Texte" dans les paramètres de contacts de Brevo pour que la synchronisation aboutisse.

---

## Automatisation (CI/CD)

Le workflow défini dans le fichier `bravo-main2.yml` est programmé pour s'exécuter de manière entièrement autonome. 

* **Déclencheur planifié (CRON) :** Tous les jours à 03h00 du matin (UTC).
* **Déclencheur manuel :** Le workflow inclut la directive `workflow_dispatch`, ce qui permet de le lancer manuellement à tout moment depuis l'onglet "Actions" de GitHub.
