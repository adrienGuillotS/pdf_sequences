import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io
import re
from collections import Counter
import os

# ------------------ UTILITY FUNCTIONS (BUSINESS LOGIC) ------------------

def normalize_id(id_text):
    """ Cleans the ID. Keeps A-Z, 0-9, and hyphens. Uppercases. """
    if not id_text: return None
    return re.sub(r"[^A-Z0-9-]", "", id_text.upper())

def extract_ids_from_guide(text):
    if not text: return []
    # Broad search for numeric patterns in guide
    return re.findall(r"\d+[\d-]+\d+", text)

def extract_one_id_from_label_text(text):
    if not text: return None
    # 1. Standard PO | 2. Long Format
    pattern = r"(?i)PO[\s-]*\d+[\d-]*|\d{4}-\d{10,}"
    match = re.search(pattern, text)
    return match.group(0) if match else None

def create_overlay_page(width, height, image_path, text_id, count):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(width, height))
    
    # Image Calculations (Top-Right Positioning)
    try:
        img = ImageReader(image_path)
        img_width, img_height = img.getSize()
        scale = 0.07 
        
        # Image Position
        x_img = width - (img_width * scale) - 20
        y_img = height - (img_height * scale) - 20
        
        # Draw Image (with your specific -10 adjustment)
        can.drawImage(image_path, x_img, y_img - 10, width=img_width*scale, height=img_height*scale, mask='auto')
        
        # --- TEXT LOGIC AND POSITIONING ---
        # Add "ACV" if count > 1
        display_text = f"{text_id} ACV {count}" if count > 1 else f"{text_id}"
        
        can.setFont("Helvetica", 11)
        # Your specific text positioning
        can.drawString(15, y_img + 78, display_text)
        
    except Exception as e:
        print(f"⚠️ Image/Position Error: {e}")

    can.save()
    packet.seek(0)
    return PyPDF2.PdfReader(packet).pages[0]

# ------------------ PROCESSING ENGINE (ADAPTED FOR GUI) ------------------

def process_files(guide_path, input_pdf_path, image_path, output_path, log_callback):
    try:
        log_callback("🚀 STARTING PROCESS...")
        
        # --- STEP 1: ANALYZE GUIDE ---
        log_callback(f"📋 Reading Guide: {os.path.basename(guide_path)}")
        guide_sequence = [] 
        all_found_ids = []  
        
        with open(guide_path, "rb") as guide_file:
            g_reader = PyPDF2.PdfReader(guide_file)
            for page in g_reader.pages:
                text = page.extract_text() or ""
                found = extract_ids_from_guide(text)
                
                for raw_id in found:
                    clean = normalize_id(raw_id)
                    if clean and len(clean) > 5:
                        # Logic to add PO- prefix if missing
                        if not clean.startswith("PO"):
                            clean = "PO-" + clean
                        
                        all_found_ids.append(clean)
                        if clean not in guide_sequence:
                            guide_sequence.append(clean)

        guide_counts = Counter(all_found_ids)
        log_callback(f"ℹ️  Unique orders in guide: {len(guide_sequence)}")

        # --- STEP 2: ANALYZE SOURCE (RAM) ---
        log_callback(f"📦 Reading Labels: {os.path.basename(input_pdf_path)}")
        labels_db = {}
        
        # Load into RAM
        with open(input_pdf_path, "rb") as f:
            source_stream = io.BytesIO(f.read())
        
        reader = PyPDF2.PdfReader(source_stream)
        num_pages = len(reader.pages)
        i = 0
        
        while i < num_pages:
            current_page = reader.pages[i]
            text_current = current_page.extract_text() or ""
            
            # Broad detection (Temu / Evri / Fulfilment)
            is_label = "TEMU" in text_current or "Evri" in text_current or "Fulfilment" in text_current
            
            if is_label:
                label_page = current_page
                po_id = extract_one_id_from_label_text(text_current)
                
                # Try next page (Metadata)
                if not po_id and (i + 1 < num_pages):
                    next_page = reader.pages[i+1]
                    text_next = next_page.extract_text() or ""
                    po_id = extract_one_id_from_label_text(text_next)
                    if po_id: i += 1 
                
                if po_id:
                    clean_id = normalize_id(po_id)
                    labels_db.setdefault(clean_id, []).append(label_page)
                else:
                    log_callback(f"⚠️ Page {i+1}: Label detected but ID unreadable.")
            i += 1

        log_callback(f"ℹ️  Identified labels: {len(labels_db)}")

        # --- STEP 3: GENERATE FINAL PDF ---
        log_callback("💾 Generating final PDF...")
        writer = PyPDF2.PdfWriter()
        processed_ids = set()
        missing_orders = []

        # A. Guide Sequence
        for order_id in guide_sequence:
            count = guide_counts[order_id]
            if order_id in labels_db:
                log_callback(f"✅ MATCH: {order_id}")
                for p in labels_db[order_id]:
                    w = float(p.mediabox[2])
                    h = float(p.mediabox[3])
                    # Call overlay function
                    overlay = create_overlay_page(w, h, image_path, order_id, count)
                    p.merge_page(overlay)
                    writer.add_page(p)
                processed_ids.add(order_id)
            else:
                missing_orders.append(order_id)
                log_callback(f"❌ MISSING: {order_id}")

        # B. Extras
        for label_id, pages in labels_db.items():
            if label_id not in processed_ids:
                log_callback(f"➕ EXTRA Added: {label_id}")
                for p in pages:
                    w = float(p.mediabox[2])
                    h = float(p.mediabox[3])
                    # For extras, count = 1
                    overlay = create_overlay_page(w, h, image_path, label_id, 1)
                    p.merge_page(overlay)
                    writer.add_page(p)

        with open(output_path, "wb") as f_out:
            writer.write(f_out)

        # --- FINAL REPORT ---
        log_callback("-" * 30)
        if missing_orders:
            log_callback(f"🚩 {len(missing_orders)} orders MISSING.")
        else:
            log_callback("✨ TOTAL SUCCESS: All orders found.")
        
        messagebox.showinfo("Success", f"File generated successfully:\n{output_path}")

    except Exception as e:
        log_callback(f"🚨 CRITICAL ERROR: {str(e)}")
        messagebox.showerror("Error", str(e))

# ------------------ GUI (TKINTER) ------------------

class PDFApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Label Sorter - Client Version")
        self.root.geometry("650x600")

        # Variables
        self.path_guide = tk.StringVar()
        self.path_source = tk.StringVar()
        self.path_image = tk.StringVar()

        # UI Construction
        tk.Label(root, text="PDF Label Sorting Tool", font=("Arial", 16, "bold")).pack(pady=10)

        self.create_file_selector("1. Guide File (PDF)", self.path_guide, [("PDF Files", "*.pdf")])
        self.create_file_selector("2. Source Labels (PDF)", self.path_source, [("PDF Files", "*.pdf")])
        self.create_file_selector("3. Caution Image (PNG/JPG)", self.path_image, [("Images", "*.png;*.jpg;*.jpeg")])

        # Action Button
        btn_run = tk.Button(root, text="START PROCESSING", command=self.start_thread, 
                            bg="#007AFF", fg="white", font=("Arial", 12, "bold"), height=2)
        btn_run.pack(pady=20, fill="x", padx=40)

        # Log Area
        tk.Label(root, text="Execution Log:").pack(anchor="w", padx=20)
        self.log_area = scrolledtext.ScrolledText(root, height=15, state='disabled')
        self.log_area.pack(padx=20, pady=(0, 20), fill="both", expand=True)

    def create_file_selector(self, label_text, var, file_types):
        frame = tk.Frame(self.root)
        frame.pack(fill="x", padx=20, pady=5)
        tk.Label(frame, text=label_text, width=25, anchor="w", font=("Arial", 10)).pack(side="left")
        entry = tk.Entry(frame, textvariable=var)
        entry.pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(frame, text="Browse...", command=lambda: self.browse_file(var, file_types)).pack(side="right")

    def browse_file(self, var, file_types):
        filename = filedialog.askopenfilename(filetypes=file_types)
        if filename:
            var.set(filename)

    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def start_thread(self):
        # Validation
        if not all([self.path_guide.get(), self.path_source.get(), self.path_image.get()]):
            messagebox.showwarning("Warning", "Please select all 3 required files.")
            return
        
        # Save As Dialog
        output_file = filedialog.asksaveasfilename(
            defaultextension=".pdf", 
            filetypes=[("PDF Files", "*.pdf")], 
            initialfile="Sorted_Labels.pdf",
            title="Save output file as..."
        )
        if not output_file: return

        # Clear Logs and Start Thread
        self.log_area.config(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state='disabled')
        
        threading.Thread(target=process_files, args=(
            self.path_guide.get(),
            self.path_source.get(),
            self.path_image.get(),
            output_file,
            self.log
        )).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = PDFApp(root)
    root.mainloop()