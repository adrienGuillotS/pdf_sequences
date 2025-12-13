import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io
import re

# ------------------ PATHS ------------------
input_pdf_path = "data/Temu _ Manage orders (1).pdf"
image_path = "data/Caution (1).png"
guide_pdf_path = "data/4.pdf"
sorted_output_path = "data/output_sorted.pdf"

# ------------------ FUNCTIONS ------------------
def extract_all_ids_from_text(text):
    """ Extrait TOUS les IDs (pour le guide). """
    if not text: return []
    matches = re.findall(r"\d+[\d-]+\d+", text)
    return matches

def extract_one_id_from_text(text):
    """ Extrait le premier ID trouvé (pour le PDF source). """
    if not text: return None
    match = re.search(r"\d+[\d-]+\d+", text)
    return match.group(0) if match else None

def normalize_id(id_text):
    """ Nettoie l'ID. """
    if not id_text: return None
    return re.sub(r"[^0-9-]", "", id_text)

# ------------------ MAIN PROCESS ------------------

# 1. ANALYSE DU GUIDE
print(f"📋 Lecture du guide complet : {guide_pdf_path}")
guide_order = []

with open(guide_pdf_path, "rb") as guide_file:
    guide_reader = PyPDF2.PdfReader(guide_file)
    for g_page in guide_reader.pages:
        g_text = g_page.extract_text() or ""
        raw_ids = extract_all_ids_from_text(g_text)
        if raw_ids:
            for raw_id in raw_ids:
                clean_id = normalize_id(raw_id)
                if len(clean_id) > 10 and clean_id not in guide_order:
                    guide_order.append(clean_id)

print(f"ℹ  Total IDs à chercher : {len(guide_order)}")


# 2. TRAITEMENT DU PDF SOURCE
print("⏳ Traitement du PDF source...")

pages_by_id = {}
remaining_pages = []

with open(input_pdf_path, "rb") as pdf_file:
    reader = PyPDF2.PdfReader(pdf_file)
    num_pages = len(reader.pages)
    page_num = 0
    
    while page_num < num_pages:
        current_page = reader.pages[page_num]
        text_current = current_page.extract_text() or ""
        
        po_id_raw = None
        po_id_clean = None
        pages_group = [] 
        
        # Si c'est une page d'étiquette
        if "TEMU-Fulfilment" in text_current:
            # On ajoute SEULEMENT la page d'étiquette
            pages_group.append(current_page)
            
            # On regarde la page suivante JUSTE pour lire l'ID
            if page_num + 1 < num_pages:
                next_page = reader.pages[page_num + 1]
                text_next = next_page.extract_text() or ""
                po_id_raw = extract_one_id_from_text(text_next)
                
                # Fallback : Si pas trouvé page suivante, chercher page actuelle
                if not po_id_raw:
                    po_id_raw = extract_one_id_from_text(text_current)
                
                if po_id_raw:
                    po_id_clean = normalize_id(po_id_raw)
                    
                    # --- MODIFICATION ICI ---
                    # Avant : pages_group.append(next_page)
                    # Maintenant : On ne fait rien, on IGNORE la page suivante pour le PDF final
                    
                    # On saute quand même l'index car on a "consommé" la page suivante
                    page_num += 2 
                else:
                    remaining_pages.append(current_page)
                    page_num += 1
                    continue
            else:
                remaining_pages.append(current_page)
                page_num += 1
                continue

            # --- Overlay Image + ID sur l'étiquette ---
            page_to_modify = pages_group[0]
            page_width = float(page_to_modify.mediabox[2])
            page_height = float(page_to_modify.mediabox[3])
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(page_width, page_height))

            try:
                img = ImageReader(image_path)
                img_width, img_height = img.getSize()
                scale = 0.07
                can.drawImage(image_path,
                              page_width - img_width*scale - 15,
                              page_height - img_height*scale - 30,
                              width=img_width*scale,
                              height=img_height*scale)
            except:
                pass 

            if po_id_raw:
                can.setFont("Helvetica-Bold", 14)
                can.drawString(10, page_height - 30, po_id_raw)

            can.save()
            packet.seek(0)
            overlay_pdf = PyPDF2.PdfReader(packet)
            page_to_modify.merge_page(overlay_pdf.pages[0])

            # Stockage
            if po_id_clean:
                pages_by_id.setdefault(po_id_clean, []).extend(pages_group)
            else:
                remaining_pages.extend(pages_group)

        else:
            remaining_pages.append(current_page)
            page_num += 1

    # 3. GÉNÉRATION PDF FINAL
    print("🚀 GÉNÉRATION DU PDF FINAL...")
    writer = PyPDF2.PdfWriter()
    count_matches = 0

    # A. Guide
    for clean_id in guide_order:
        if clean_id in pages_by_id:
            print(f"✅ MATCH ! ID trouvé : {clean_id}")
            for p in pages_by_id[clean_id]:
                writer.add_page(p)
                count_matches += 1
            del pages_by_id[clean_id]
        else:
            print(f"❌ MANQUANT : {clean_id}")

    # B. Hors Guide
    if pages_by_id:
        print("⚠️ HORS GUIDE (Ajoutés à la fin) :")
        for clean_id, pages in pages_by_id.items():
            print(f"   ➡ {clean_id}")
            for p in pages:
                writer.add_page(p)

    # C. Reste
    for p in remaining_pages:
        writer.add_page(p)

    with open(sorted_output_path, "wb") as f_out:
        writer.write(f_out)

print("-" * 40)
print(f"🎉 Terminé ! {count_matches} pages correspondantes (étiquettes seules).")
print(f"📁 Fichier : {sorted_output_path}")