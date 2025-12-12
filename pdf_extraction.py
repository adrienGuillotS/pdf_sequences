import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io
import re
from collections import Counter

# ------------------ CHEMINS (PATHS) ------------------
input_pdf_path = "data/Temu _ Manage orders (1).pdf"
image_path = "data/Caution (1).png"
guide_pdf_path = "data/11.pdf"
sorted_output_path = "data/output_sorted_final.pdf"

# ------------------ FONCTIONS UTILITAIRES ------------------

def normalize_id(id_text):
    """ Nettoie l'ID. """
    if not id_text: return None
    # On garde chiffres, lettres majuscules et tirets
    return re.sub(r"[^A-Z0-9-]", "", id_text.upper()) 

def extract_ids_from_guide(text):
    if not text: return []
    # Recherche large de motifs ressemblant à des IDs
    return re.findall(r"\d+[\d-]+\d+|[A-Z0-9]{5,}", text)

def extract_one_id_from_label_text(text):
    if not text: return None
    # Recherche stricte pour l'étiquette
    match = re.search(r"\d+[\d-]+\d+", text)
    return match.group(0) if match else None

def create_overlay_page(width, height, image_path, text_id, count):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(width, height))
    
    try:
        img = ImageReader(image_path)
        img_width, img_height = img.getSize()
        scale = 0.07 
        x_img = width - (img_width * scale) - 20
        y_img = height - (img_height * scale) - 20
        can.drawImage(image_path, x_img, y_img, width=img_width*scale, height=img_height*scale, mask='auto')
    except Exception as e:
        print(f"⚠️ Image non chargée : {e}")

    display_text = f"{text_id} {count}" if count > 1 else f"{text_id}"
    can.setFont("Helvetica-Bold", 14)
    can.drawString(20, 30, display_text)
    
    can.save()
    packet.seek(0)
    return PyPDF2.PdfReader(packet).pages[0]

# ------------------ PROCESSUS PRINCIPAL ------------------

def main():
    print("="*60)
    print("   DÉBUT DU TRAITEMENT AVEC LOGS DÉTAILLÉS")
    print("="*60)

    # --- ÉTAPE 1 : ANALYSE DU GUIDE ---
    print(f"\n📋 [GUIDE] Lecture du fichier : {guide_pdf_path}")
    
    guide_sequence = [] 
    all_found_ids = []  
    
    with open(guide_pdf_path, "rb") as guide_file:
        g_reader = PyPDF2.PdfReader(guide_file)
        
        for i, page in enumerate(g_reader.pages):
            text = page.extract_text() or ""
            print(f"   📄 Page {i+1} : Analyse du texte ({len(text)} chars)...")
            
            found = extract_ids_from_guide(text)
            if not found:
                print("      ⚠️ Aucun ID détecté sur cette page.")
            
            for raw_id in found:
                clean = normalize_id(raw_id)
                if clean and len(clean) > 5:
                    print(f"      ✅ Trouvé : {clean}")
                    all_found_ids.append(clean)
                    if clean not in guide_sequence:
                        guide_sequence.append(clean)
                else:
                    print(f"      🗑️ Ignoré (trop court/bruit) : {raw_id}")

    guide_counts = Counter(all_found_ids)
    print(f"ℹ️  RÉSULTAT GUIDE : {len(guide_sequence)} commandes uniques trouvées.")
    print("-" * 60)


    # --- ÉTAPE 2 : INDEXATION DU PDF DES ÉTIQUETTES ---
    print("\n📦 [SOURCE] Analyse et découpage du PDF source...")
    
    labels_db = {}
    
    # Chargement en mémoire RAM (Correction du bug précédent)
    with open(input_pdf_path, "rb") as f:
        source_stream = io.BytesIO(f.read())
    
    reader = PyPDF2.PdfReader(source_stream)
    num_pages = len(reader.pages)
    i = 0
    
    while i < num_pages:
        current_page = reader.pages[i]
        text_current = current_page.extract_text() or ""
        
        # Log pour chaque page
        is_label = "TEMU-Fulfilment" in text_current
        status_msg = "Étiquette détectée" if is_label else "Page ignorée (Pas TEMU)"
        print(f"   📄 Page {i+1}/{num_pages} : {status_msg}")

        if is_label:
            label_page = current_page
            po_id = extract_one_id_from_label_text(text_current)
            
            if po_id:
                print(f"      🔍 ID trouvé directement : {po_id}")
            else:
                print("      ⚠️ Pas d'ID sur la page, tentative page suivante...")
                if i + 1 < num_pages:
                    next_page = reader.pages[i+1]
                    text_next = next_page.extract_text() or ""
                    po_id = extract_one_id_from_label_text(text_next)
                    if po_id:
                        print(f"      🔍 ID trouvé sur la page suivante (Métadonnées) : {po_id}")
                        i += 1 # On saute la page suivante
                    else:
                        print("      ❌ ECHEC : Aucun ID trouvé sur page suivante non plus.")
                else:
                    print("      ❌ ECHEC : Pas de page suivante pour chercher l'ID.")
            
            if po_id:
                clean_id = normalize_id(po_id)
                labels_db.setdefault(clean_id, []).append(label_page)
            else:
                print(f"      🚨 ATTENTION : Une étiquette à la page {i+1} n'a pas pu être identifiée.")
        
        i += 1

    print(f"ℹ️  RÉSULTAT SOURCE : {len(labels_db)} étiquettes identifiées.")
    print("-" * 60)

    # --- ÉTAPE 3 : CONSTRUCTION DU PDF FINAL ---
    print("\n🚀 [SORTIE] Génération du fichier final...")
    writer = PyPDF2.PdfWriter()
    
    missing_orders = [] 
    processed_ids = set()

    # A. Guide
    for order_id in guide_sequence:
        count_in_guide = guide_counts[order_id]
        if order_id in labels_db:
            # print(f"   OK -> Ajout {order_id}")  # Décommenter si trop bavard
            pages = labels_db[order_id]
            for p in pages:
                w = float(p.mediabox[2])
                h = float(p.mediabox[3])
                overlay = create_overlay_page(w, h, image_path, order_id, count_in_guide)
                p.merge_page(overlay)
                writer.add_page(p)
            processed_ids.add(order_id)
        else:
            print(f"   ❌ Manquant dans le source : {order_id}")
            missing_orders.append(order_id)

    # B. Extras
    extras_found = False
    for label_id, pages in labels_db.items():
        if label_id not in processed_ids:
            if not extras_found:
                print("   ⚠️  Ajout des EXTRA (Hors Guide)...")
                extras_found = True
            print(f"      + Extra ajouté : {label_id}")
            for p in pages:
                w = float(p.mediabox[2])
                h = float(p.mediabox[3])
                overlay = create_overlay_page(w, h, image_path, label_id, 1)
                p.merge_page(overlay)
                writer.add_page(p)

    with open(sorted_output_path, "wb") as f_out:
        writer.write(f_out)

    # --- ÉTAPE 4 : RAPPORT FINAL ---
    print("=" * 60)
    if missing_orders:
        print("🚩 RÉSUMÉ DES ERREURS (Commandes du guide introuvables) :")
        for m_id in missing_orders:
            print(f"   • {m_id} (x{guide_counts[m_id]})")
    else:
        print("✅ SUCCÈS TOTAL : Toutes les commandes du guide sont là.")
    print("=" * 60)
    print(f"📁 Fichier généré : {sorted_output_path}")

if __name__ == "__main__":
    main()