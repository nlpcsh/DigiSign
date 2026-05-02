import os
import tempfile
from typing import Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk
import fitz
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

from classes.SignaturePlacement import SignaturePlacement
from classes.CertificateManager import CertificateManager, CertificateInfo
from classes.Preferences import Preferences

CANVAS_WIDTH = 680
CANVAS_HEIGHT = 900
DEFAULT_WIDTH = 3 * inch
DEFAULT_HEIGHT = 1 * inch

class PdfSigner:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("DigiSign PDF Signer")

        self.pdf_path: Optional[str] = None
        self.reader: Optional[PdfReader] = None
        self.page_size: Tuple[float, float] = (0.0, 0.0)
        self.selection: Optional[SignaturePlacement] = None
        self.drag_start: Optional[Tuple[float, float]] = None
        self.selection_rect_id: Optional[int] = None
        self.signature_image_path: Optional[str] = None
        self.signature_image_label: Optional[tk.Label] = None
        self.fitz_doc: Optional[fitz.Document] = None
        self.page_image_tk: Optional[ImageTk.PhotoImage] = None

        # Certificate support
        self.selected_certificate: Optional[CertificateInfo] = None
        self.available_certificates: list[CertificateInfo] = []
        self.certificate_combo: Optional[ttk.Combobox] = None
        self.certificate_status_label: Optional[tk.Label] = None
        self.cert_password_entry: Optional[tk.Entry] = None
        self.cert_password_label: Optional[tk.Label] = None
        self.signer_name_label: Optional[tk.Label] = None
        self.signature_declaration_var: tk.StringVar = tk.StringVar(value="I'm the author")
        self.signature_declaration_combo: Optional[ttk.Combobox] = None

        toolbar = tk.Frame(root)
        toolbar.pack(fill="x", padx=8, pady=8)

        tk.Button(toolbar, text="Open PDF", command=self.open_pdf).pack(side="left")
        tk.Button(toolbar, text="Refresh Certificates", command=self.load_certificates).pack(side="left", padx=(8, 0))

        self.page_frame = tk.Frame(root)
        self.page_frame.pack(fill="x", padx=8)

        tk.Label(self.page_frame, text="Page:").pack(side="left")
        self.page_var = tk.IntVar(value=1)
        self.page_spin = tk.Spinbox(self.page_frame, from_=1, to=1, width=5, textvariable=self.page_var, command=self.on_page_change)
        self.page_spin.pack(side="left", padx=(0, 12))

        self.info_label = tk.Label(self.page_frame, text="No file loaded")
        self.info_label.pack(side="left")

        content = tk.Frame(root)
        content.pack(fill="both", expand=True, padx=8, pady=8)

        self.canvas = tk.Canvas(content, width=CANVAS_WIDTH, height=CANVAS_HEIGHT, bg="#f0f0f0")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        sidebar = tk.Frame(content, padx=12)
        sidebar.pack(side="right", fill="y")

        # Certificate selection section
        tk.Label(sidebar, text="Digital Certificate:", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(0, 6))
        self.certificate_combo = ttk.Combobox(sidebar, state="readonly", width=25)
        self.certificate_combo.pack(fill="x", pady=(0, 6))
        self.certificate_combo.bind("<<ComboboxSelected>>", self.on_certificate_selected)

        self.certificate_status_label = tk.Label(sidebar, text="No certificate selected", wraplength=160, justify="left", fg="#666")
        self.certificate_status_label.pack(anchor="w", pady=(0, 12))

        tk.Label(sidebar, text="Signer name:").pack(anchor="w")
        self.signer_name_label = tk.Label(sidebar, text="(From certificate)", wraplength=160, justify="left", fg="#666")
        self.signer_name_label.pack(anchor="w", pady=(0, 12))

        # Certificate password
        tk.Label(sidebar, text="Certificate Password:").pack(anchor="w")
        self.cert_password_entry = tk.Entry(sidebar, show="*")
        self.cert_password_entry.pack(fill="x", pady=(0, 12))
        self.cert_password_label = tk.Label(sidebar, text="(Leave blank if no password)", font=("TkDefaultFont", 8), fg="#999")
        self.cert_password_label.pack(anchor="w", pady=(0, 12))

        tk.Label(sidebar, text="Signature statement:").pack(anchor="w")
        self.signature_declaration_combo = ttk.Combobox(
            sidebar,
            state="readonly",
            width=25,
            textvariable=self.signature_declaration_var,
            values=["I'm the author", "I reviewed this document"]
        )
        self.signature_declaration_combo.pack(fill="x", pady=(0, 12))
        self.signature_declaration_combo.bind("<<ComboboxSelected>>", self.on_signature_declaration_selected)
        self.signature_declaration_combo.current(0)

        tk.Button(sidebar, text="Load signature image", command=self.load_signature_image).pack(fill="x")
        self.signature_image_label = tk.Label(sidebar, text="No signature image loaded", wraplength=160, justify="left")
        self.signature_image_label.pack(anchor="w", pady=(6, 12))

        tk.Label(sidebar, text="Selection (PDF points):").pack(anchor="w")
        self.selection_label = tk.Label(sidebar, text="x=0.0 y=0.0 w=0.0 h=0.0", justify="left")
        self.selection_label.pack(anchor="w", pady=(0, 12))

        tk.Label(sidebar, text="Instructions:").pack(anchor="w")
        tk.Label(sidebar, text="1) Select a certificate\n2) Open a PDF\n3) Drag to draw signature box\n4) Load signature image (optional)\n5) Click Sign PDF", justify="left", fg="#333333").pack(anchor="w")

        tk.Button(sidebar, text="Sign PDF", command=self.complete_signing, bg="white", fg="blue").pack(fill="x", pady=(12, 0))

        # Load certificates on startup
        self.load_certificates()
        # Load saved preferences
        self.load_preferences()

    def load_certificates(self) -> None:
        """Load available certificates from Windows certificate store"""
        try:
            all_certificates = CertificateManager.list_certificates()
            # Filter out expired certificates
            self.available_certificates = [cert for cert in all_certificates if not self._is_certificate_expired(cert)]
            cert_names = [cert.friendly_name for cert in self.available_certificates]

            if self.certificate_combo:
                self.certificate_combo['values'] = cert_names

                # Apply certificate preferences after loading
                self._apply_certificate_preferences()

                if not cert_names:
                    self.certificate_status_label.config(
                        text="No certificates found in store",
                        fg="#d9534f"
                    )
        except Exception as exc:
            self.certificate_status_label.config(
                text=f"Error loading certificates:\n{str(exc)[:50]}",
                fg="#d9534f"
            )

    def on_certificate_selected(self, event: Optional[tk.Event] = None) -> None:
        """Handle certificate selection from dropdown"""
        if not self.certificate_combo:
            return

        index = self.certificate_combo.current()
        if 0 <= index < len(self.available_certificates):
            self.selected_certificate = self.available_certificates[index]
            cert = self.selected_certificate

            # Update status label with certificate info
            status_text = f"Subject: {cert.friendly_name}\n"
            status_text += f"Valid: {cert.valid_from}\nto {cert.valid_to}"
            self.certificate_status_label.config(text=status_text, fg="#5cb85c")

            # Extract and display signer name from certificate
            signer_name = self._extract_signer_name_from_cert(cert)
            if self.signer_name_label:
                self.signer_name_label.config(text=signer_name if signer_name else "Unknown")
            # Save preference
            Preferences.set_selected_certificate_thumbprint(cert.thumbprint)
            Preferences.set_selected_certificate_friendly_name(cert.friendly_name)
        else:
            self.selected_certificate = None
            self.certificate_status_label.config(
                text="No certificate selected",
                fg="#666"
            )
            if self.signer_name_label:
                self.signer_name_label.config(text="(From certificate)")
            # Clear preferences
            Preferences.set_selected_certificate_thumbprint(None)
            Preferences.set_selected_certificate_friendly_name(None)

    def _extract_signer_name_from_cert(self, cert: Optional[CertificateInfo]) -> str:
        """Extract signer name from certificate subject"""
        if not cert:
            return "Signer"

        # Try to extract CN from subject
        subject = cert.subject
        parts = subject.split(',')
        for part in parts:
            part = part.strip()
            if part.startswith('CN='):
                name = part[3:].strip()
                # Remove quotes if present
                return name.strip('\'"')

        # Fallback to friendly name
        return cert.friendly_name.strip('\'"') if cert.friendly_name else "Signer"

    def _is_certificate_expired(self, cert: CertificateInfo) -> bool:
        """Check if a certificate has expired"""
        try:
            from datetime import datetime
            # Parse the valid_to date (ISO format with timezone)
            valid_to_str = cert.valid_to.split('.')[0]  # Remove microseconds and timezone
            valid_to = datetime.fromisoformat(valid_to_str)
            now = datetime.now()
            return now > valid_to
        except Exception:
            # If we can't parse, assume it's not expired
            return False


    def _apply_certificate_preferences(self) -> None:
        """Apply saved certificate preferences to the current certificate list"""
        # Load and select certificate by thumbprint (preferred) or friendly name
        cert_thumbprint = Preferences.get_selected_certificate_thumbprint()
        cert_friendly_name = Preferences.get_selected_certificate_friendly_name()

        selected_index = -1

        for idx, cert in enumerate(self.available_certificates):
            # Try to match by thumbprint first
            if cert_thumbprint and cert.thumbprint == cert_thumbprint:
                selected_index = idx
                break
            # Fallback to friendly name
            if cert_friendly_name and cert.friendly_name == cert_friendly_name:
                selected_index = idx
                break

        # Select the found certificate, or default to first certificate if none found
        if selected_index >= 0:
            self.certificate_combo.current(selected_index)
            self.on_certificate_selected()
        elif self.available_certificates:
            # No saved preference found, select first certificate as default
            self.certificate_combo.current(0)
            self.on_certificate_selected()
        else:
            # No certificates available
            self.selected_certificate = None
            self.certificate_status_label.config(
                text="No certificates available",
                fg="#666"
            )
            if self.signer_name_label:
                self.signer_name_label.config(text="(From certificate)")

    def load_preferences(self) -> None:
        """Load and apply saved preferences (signature image and certificate)."""
        # Load signature image path
        sig_image_path = Preferences.get_signature_image_path()
        if sig_image_path and os.path.isfile(sig_image_path):
            self.signature_image_path = sig_image_path
            self.update_signature_image_label()

        # Apply certificate preferences
        self._apply_certificate_preferences()

        # Load saved signature declaration preference
        declaration = Preferences.get_signature_declaration()
        if declaration in ["I'm the author", "I reviewed this document"]:
            self.signature_declaration_var.set(declaration)

    def on_signature_declaration_selected(self, event: Optional[tk.Event] = None) -> None:
        """Handle signature statement selection."""
        declaration = self.signature_declaration_var.get()
        Preferences.set_signature_declaration(declaration)

    def load_signature_image(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"), ("All files", "*.*")])
        if not path:
            return
        self.signature_image_path = path
        self.update_signature_image_label()
        # Save preference
        Preferences.set_signature_image_path(path)

    def update_signature_image_label(self) -> None:
        if self.signature_image_path:
            self.signature_image_label.config(text=os.path.basename(self.signature_image_path))
        else:
            self.signature_image_label.config(text="No signature image loaded")

    def open_pdf(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        try:
            reader = PdfReader(path)
        except Exception as exc:
            messagebox.showerror("Open PDF", f"Failed to open PDF:\n{exc}")
            return

        self.pdf_path = path
        self.reader = reader
        self.page_var.set(1)
        self.page_spin.config(to=len(reader.pages))

        if self.fitz_doc:
            try:
                self.fitz_doc.close()
            except Exception:
                pass
        try:
            self.fitz_doc = fitz.open(path)
        except Exception as exc:
            self.fitz_doc = None
            messagebox.showwarning("Open PDF", f"Preview unavailable:\n{exc}")

        self.load_page(0)

    def preview_pdf_file(self, pdf_path: str) -> None:
        try:
            reader = PdfReader(pdf_path)
        except Exception as exc:
            messagebox.showerror("Preview PDF", f"Unable to load signed PDF preview:\n{exc}")
            return

        self.pdf_path = pdf_path
        self.reader = reader
        self.page_var.set(1)
        self.page_spin.config(to=len(reader.pages))

        if self.fitz_doc:
            try:
                self.fitz_doc.close()
            except Exception:
                pass
        try:
            self.fitz_doc = fitz.open(pdf_path)
        except Exception as exc:
            self.fitz_doc = None
            messagebox.showwarning("Preview PDF", f"Signed PDF preview unavailable:\n{exc}")

        self.load_page(0)

    def on_page_change(self) -> None:
        if not self.reader:
            return
        page_index = max(1, min(len(self.reader.pages), self.page_var.get())) - 1
        self.load_page(page_index)

    def pdf_page_size(self, page) -> Tuple[float, float]:
        box = page.mediabox
        width = float(box.width)
        height = float(box.height)
        return width, height

    def pdf_to_canvas_coords(self,x: float, y: float, page_size: Tuple[float, float]) -> Tuple[float, float]:
        page_w, page_h = page_size
        scale = min(CANVAS_WIDTH / page_w, CANVAS_HEIGHT / page_h)
        canvas_x = x * scale
        canvas_y = CANVAS_HEIGHT - (y * scale)
        return canvas_x, canvas_y

    def canvas_to_pdf_coords(self, x: float, y: float, page_size: Tuple[float, float]) -> Tuple[float, float]:
        page_w, page_h = page_size
        scale = min(CANVAS_WIDTH / page_w, CANVAS_HEIGHT / page_h)
        pdf_x = x / scale
        pdf_y = (CANVAS_HEIGHT - y) / scale
        return pdf_x, pdf_y

    def load_page(self, page_index: int) -> None:
        if not self.reader:
            return
        page = self.reader.pages[page_index]
        self.page_size = self.pdf_page_size(page)
        self.selection = None
        self.drag_start = None
        self.selection_rect_id = None
        self.page_image_tk = None
        self.redraw_canvas()
        page_w, page_h = self.page_size
        self.info_label.config(text=f"{os.path.basename(self.pdf_path)} — page {page_index + 1}/{len(self.reader.pages)} — {page_w:.0f}x{page_h:.0f} pts")
        self.update_selection_label()
        self.update_signature_image_label()

    def get_page_preview_text(self, page) -> str:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if not text.strip():
            page_w, page_h = self.page_size
            return f"No text preview available for this page.\nPage size: {page_w:.0f} x {page_h:.0f} pts"

        lines = text.strip().splitlines()
        if len(lines) > 60:
            lines = lines[:60] + ["..."]
        return "\n".join(lines)

    def render_page_preview(self, page_index: int):
        if not self.fitz_doc:
            return None
        try:
            page = self.fitz_doc.load_page(page_index)
            pix = page.get_pixmap(alpha=False)
            return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        except Exception:
            return None

    def redraw_canvas(self) -> None:
        self.canvas.delete("all")
        if not self.pdf_path or not self.reader:
            self.canvas.create_text(CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2, text="Open a PDF to start", fill="#666")
            return

        page_w, page_h = self.page_size
        scale = min(CANVAS_WIDTH / page_w, CANVAS_HEIGHT / page_h)
        disp_w = int(page_w * scale)
        disp_h = int(page_h * scale)
        x0 = (CANVAS_WIDTH - disp_w) / 2
        y0 = (CANVAS_HEIGHT - disp_h) / 2
        x1 = x0 + disp_w
        y1 = y0 + disp_h

        self.canvas.create_rectangle(x0, y0, x1, y1, fill="white", outline="#444")
        preview_image = self.render_page_preview(self.page_var.get() - 1)
        if preview_image:
            preview_image = preview_image.resize((disp_w, disp_h), Image.LANCZOS)
            self.page_image_tk = ImageTk.PhotoImage(preview_image)
            self.canvas.create_image(x0, y0, anchor="nw", image=self.page_image_tk)
        else:
            preview_page = self.reader.pages[self.page_var.get() - 1]
            preview_text = self.get_page_preview_text(preview_page)
            self.canvas.create_text(
                x0 + 10,
                y0 + 10,
                text=preview_text,
                anchor="nw",
                fill="#222",
                font=("Courier", 9),
                width=disp_w - 20,
            )

        if self.selection:
            sel_x0, sel_y0 = self.pdf_to_canvas_coords(self.selection.x, self.selection.y + self.selection.height, self.page_size)
            sel_x1, sel_y1 = self.pdf_to_canvas_coords(self.selection.x + self.selection.width, self.selection.y, self.page_size)
            self.canvas.create_rectangle(sel_x0, sel_y0, sel_x1, sel_y1, outline="#007bff", width=2)

    def on_mouse_down(self, event: tk.Event) -> None:
        if not self.pdf_path:
            return
        self.drag_start = (event.x, event.y)
        if self.selection_rect_id is not None:
            self.canvas.delete(self.selection_rect_id)
            self.selection_rect_id = None

    def on_mouse_drag(self, event: tk.Event) -> None:
        if not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y
        if self.selection_rect_id is not None:
            self.canvas.delete(self.selection_rect_id)
        self.selection_rect_id = self.canvas.create_rectangle(x0, y0, x1, y1, outline="#007bff", width=2)

    def on_mouse_up(self, event: tk.Event) -> None:
        if not self.drag_start or not self.reader:
            return
        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y
        self.drag_start = None
        if abs(x1 - x0) < 10 or abs(y1 - y0) < 10:
            return

        left = min(x0, x1)
        right = max(x0, x1)
        top = min(y0, y1)
        bottom = max(y0, y1)

        pdf_x, pdf_top = self.canvas_to_pdf_coords(left, top, self.page_size)
        pdf_right, pdf_bottom = self.canvas_to_pdf_coords(right, bottom, self.page_size)
        width = abs(pdf_right - pdf_x)
        height = abs(pdf_top - pdf_bottom)
        y = min(pdf_top, pdf_bottom)

        page_index = self.page_var.get() - 1
        self.selection = SignaturePlacement(page_number=page_index, x=pdf_x, y=y, width=width, height=height)
        self.update_selection_label()
        self.redraw_canvas()

    def update_selection_label(self) -> None:
        if not self.selection:
            self.selection_label.config(text="x=0.0 y=0.0 w=0.0 h=0.0")
            return
        self.selection_label.config(text=f"x={self.selection.x:.1f} y={self.selection.y:.1f} w={self.selection.width:.1f} h={self.selection.height:.1f}")

    def complete_signing(self) -> None:
        if not self.pdf_path or not self.reader:
            messagebox.showwarning("Sign PDF", "No PDF is loaded.")
            return
        if not self.selection:
            messagebox.showwarning("Sign PDF", "Draw a signature box on the page first.")
            return
        if not self.selected_certificate:
            messagebox.showwarning("Sign PDF", "Please select a digital certificate first.")
            return

        signer_name = self._extract_signer_name_from_cert(self.selected_certificate)
        cert_password = self.cert_password_entry.get() if self.cert_password_entry else ""

        page = self.reader.pages[self.selection.page_number]
        page_w, page_h = self.pdf_page_size(page)

        overlay_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        overlay_path = overlay_pdf.name
        overlay_pdf.close()

        signature_declaration = self.signature_declaration_var.get()

        try:
            self.create_signature_overlay(
                self.selection,
                signer_name,
                signature_declaration,
                overlay_path,
                page_w,
                page_h,
                signature_image_path=self.signature_image_path,
            )
            output_pdf = os.path.splitext(self.pdf_path)[0] + "_signed.pdf"
            self.merge_overlay(
                self.pdf_path,
                overlay_path,
                self.selection,
                output_pdf,
                certificate=self.selected_certificate,
                password=cert_password,
                signer_name=signer_name
            )
            messagebox.showinfo(
                "Sign PDF",
                f"PDF digitally signed and saved:\n{output_pdf}\n\n"
                f"Certificate: {self.selected_certificate.friendly_name}\n"
                f"Signer: {signer_name}"
            )
            self.preview_pdf_file(output_pdf)
        except Exception as exc:
            messagebox.showerror("Sign PDF", f"Failed to sign PDF:\n{exc}")
        finally:
            try:
                os.remove(overlay_path)
            except OSError:
                pass

    @staticmethod
    def create_signature_overlay(
        placement: SignaturePlacement,
        signer_name: str,
        signature_type: str,
        output_path: str,
        page_width: float,
        page_height: float,
        signature_image_path: Optional[str] = None,
    ) -> None:
        c = canvas.Canvas(output_path, pagesize=(page_width, page_height))
        c.setStrokeColorRGB(0, 0, 0)
        c.setFillColorRGB(0, 0, 0)
        c.setLineWidth(1)
        c.rect(placement.x, placement.y, placement.width, placement.height)

        text_x = placement.x + 0.08 * inch
        text_y = placement.y + placement.height - 0.26 * inch
        image_margin = 0.08 * inch
        image_area_width = placement.width * 0.35
        image_area_height = placement.height - (image_margin * 2)

        if signature_image_path and os.path.isfile(signature_image_path):
            try:
                image_reader = ImageReader(signature_image_path)
                img_w, img_h = image_reader.getSize()
                if img_w > 0 and img_h > 0:
                    scale = min(image_area_width / img_w, image_area_height / img_h, 1.0)
                    img_w = img_w * scale
                    img_h = img_h * scale
                    image_x = placement.x + image_margin
                    image_y = placement.y + placement.height - img_h - image_margin
                    c.drawImage(image_reader, image_x, image_y, width=img_w, height=img_h, mask="auto")
                    text_x = image_x + img_w + 0.12 * inch
            except Exception:
                text_x = placement.x + 0.08 * inch

        c.setFont("Helvetica-Bold", 9)
        c.drawString(text_x, text_y, "Digitally signed by:")
        c.setFont("Helvetica", 8)
        c.drawString(text_x, text_y - 14, signer_name)
        c.drawString(text_x, text_y - 28, f"Reason: {signature_type}")
        c.drawString(text_x, text_y - 42, f"Date: {CertificateManager.get_current_time_iso()}")
        c.save()

    @staticmethod
    def merge_overlay(
        pdf_path: str,
        overlay_path: str,
        placement: SignaturePlacement,
        output_pdf: str,
        certificate: Optional[CertificateInfo] = None,
        password: Optional[str] = None,
        signer_name: Optional[str] = None
    ) -> None:
        """Merge overlay with PDF and add digital signature"""
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        overlay_reader = PdfReader(overlay_path)
        overlay_page = overlay_reader.pages[0]

        for index, page in enumerate(reader.pages):
            if index == placement.page_number:
                page.merge_page(overlay_page)
            writer.add_page(page)

        # Write the PDF with visual signature
        with open(output_pdf, "wb") as out_file:
            writer.write(out_file)

        # Add digital signature if certificate is provided
        if certificate:
            PdfSigner._add_digital_signature(output_pdf, certificate, placement, password, signer_name)

    @staticmethod
    def _add_digital_signature(
        pdf_path: str,
        certificate: CertificateInfo,
        placement: SignaturePlacement,
        password: Optional[str] = None,
        signer_name: Optional[str] = None
    ) -> None:
        """
        Add digital signature to PDF using X.509 certificate from Windows store
        """
        try:
            temp_signed = pdf_path + ".temp"

            # Use CertificateManager to try real cryptographic signing first
            from classes.CertificateManager import CertificateManager
            success = CertificateManager.sign_pdf_with_certificate(
                pdf_path,
                certificate.thumbprint,
                temp_signed,
                password=password,
                signer_name=signer_name
            )

            if success and os.path.exists(temp_signed):
                os.replace(temp_signed, pdf_path)
                print("✓ Digital signature added successfully")
                return

            # Fallback: add signature metadata if real signing is not available
            if os.path.exists(temp_signed):
                os.remove(temp_signed)
            temp_meta = pdf_path + ".meta"
            metadata_success = CertificateManager.sign_pdf_with_metadata(
                pdf_path,
                temp_meta,
                certificate,
                signer_name=signer_name
            )
            if metadata_success and os.path.exists(temp_meta):
                os.replace(temp_meta, pdf_path)
                print("✓ Metadata signature applied as fallback")
            elif os.path.exists(temp_meta):
                os.remove(temp_meta)

        except Exception as exc:
            print(f"Warning: Digital signing not available: {exc}")
            # This is not fatal - the PDF still has the visual signature
