# Automatisation PDF - Étiquettes d'Expédition

## Description
Programme d'automatisation pour traiter des fichiers PDF contenant des étiquettes d'expédition et des factures.

## Fonctionnalités
- Extraction des numéros de commande des pages de factures
- Ajout des numéros de commande sur les étiquettes d'expédition
- Ajout d'une image "Caution" sur chaque étiquette
- Réorganisation des pages selon un fichier guide

## Installation
```bash
pip install -r requirements.txt
```

## Utilisation
```bash
python pdf_automation.py
```

## Structure des fichiers
- `data/4.pdf` : Fichier contenant les étiquettes et factures
- `data/Temu _ Manage orders (1).pdf` : Fichier guide avec la séquence des commandes
- `data/Caution (1).png` : Image à ajouter sur les étiquettes
- `data/output_final.pdf` : Fichier de sortie généré

## Configuration
Modifiez les chemins dans la fonction `main()` du fichier `pdf_automation.py` si nécessaire.
# pdf_sequences
