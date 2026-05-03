import os
import platform
import tempfile
from typing import Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

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
        self.certificate_validity_label: Optional[tk.Label] = None
        self.cert_password_checkbox: Optional[tk.Checkbutton] = None
        self.cert_password_var: tk.BooleanVar = tk.BooleanVar(value=False)
        self.selected_certificate_password: Optional[str] = None
        self.signer_name_label: Optional[tk.Label] = None
        self.signature_declaration_var: tk.StringVar = tk.StringVar(value="I'm the author")
        self.signature_declaration_combo: Optional[ttk.Combobox] = None
        self.visual_only_var: tk.BooleanVar = tk.BooleanVar(value=False)

        toolbar = tk.Frame(root)
        toolbar.pack(fill="x", padx=8, pady=8)

        tk.Button(toolbar, text="Open PDF", command=self.open_pdf).pack(side="left")
        if platform.system() != "Linux":
            tk.Button(toolbar, text="Refresh Certificates", command=self.load_certificates).pack(side="left", padx=(8, 0))
        if platform.system() != "Windows":
            tk.Button(toolbar, text="Load certificate file", command=self.load_certificate_file).pack(side="left", padx=(8, 0))

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
        if platform.system() != "Linux":
            tk.Label(sidebar, text="Digital Certificate:", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(0, 6))
            self.certificate_combo = ttk.Combobox(sidebar, state="readonly", width=25)
            self.certificate_combo.pack(fill="x", pady=(0, 6))
            self.certificate_combo.bind("<<ComboboxSelected>>", self._update_certificate_display)

            self.certificate_status_label = tk.Label(sidebar, text="No certificate selected", wraplength=160, justify="left", fg="#666")
            self.certificate_status_label.pack(anchor="w", pady=(0, 12))

        tk.Label(sidebar, text="Signer name:").pack(anchor="w")
        self.signer_name_label = tk.Label(sidebar, text="(From certificate)", wraplength=160, justify="left", fg="#666")
        self.signer_name_label.pack(anchor="w", pady=(0, 2))
        self.certificate_validity_label = tk.Label(sidebar, text="", wraplength=160, justify="left", fg="#666")
        self.certificate_validity_label.pack(anchor="w", pady=(0, 12))

        # Certificate password handling
        self.cert_password_checkbox = tk.Checkbutton(
            sidebar,
            text="Certificate requires password",
            variable=self.cert_password_var,
            onvalue=True,
            offvalue=False
        )
        self.cert_password_checkbox.pack(anchor="w", pady=(0, 12))
        tk.Label(sidebar, text="Password is set outside this app on certificate load or sign use.", font=("TkDefaultFont", 8), fg="#999").pack(anchor="w", pady=(0, 12))

        # Visual-only signing option
        self.visual_only_checkbox = tk.Checkbutton(
            sidebar,
            text="Visual signature only\n(no digital certificate)",
            variable=self.visual_only_var,
            onvalue=True,
            offvalue=False
        )
        self.visual_only_checkbox.pack(anchor="w", pady=(0, 12))
        tk.Label(sidebar, text="Sign with image only, even if certificate is unavailable.", font=("TkDefaultFont", 8), fg="#999").pack(anchor="w", pady=(0, 12))

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
        tk.Label(sidebar, text="1) Select a certificate or load a certificate file\n2) Open a PDF\n3) Drag to draw signature box\n4) Load signature image (optional)\n5) Click Sign PDF", justify="left", fg="#333333").pack(anchor="w")

        tk.Button(sidebar, text="Sign PDF", command=self.complete_signing, bg="white", fg="blue").pack(fill="x", pady=(12, 0))

        # Load certificates on startup
        self.load_certificates()
        # Load saved preferences
        self.load_preferences()

    def load_certificates(self) -> None:
        """Load available certificates from the local certificate directory and Windows store."""
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
                    if self.certificate_status_label:
                        self.certificate_status_label.config(
                            text="No certificates found",
                            fg="#d9534f"
                        )
        except Exception as exc:
            if self.certificate_status_label:
                self.certificate_status_label.config(
                    text=f"Error loading certificates:\n{str(exc)[:50]}",
                    fg="#d9534f"
                )

    def load_certificate_file(self) -> None:
        """Allow the user to select a local certificate file for signing."""
        path = filedialog.askopenfilename(
            title="Load certificate file",
            filetypes=[
                ("PKCS#12 files", "*.pfx;*.p12"),
                ("Certificate files", "*.pem;*.crt;*.cer"),
                ("All files", "*.*")
            ]
        )
        if not path:
            return

        password = None
        if path.lower().endswith(('.pfx', '.p12')):
            password = simpledialog.askstring(
                "Certificate Password",
                "Enter the password for the certificate file (leave blank if none):",
                show="*"
            )

        cert_info = CertificateManager.load_certificate_file(path, password=password)
        if not cert_info:
            messagebox.showerror(
                "Load certificate",
                f"Unable to load certificate file:\n{path}\n\n"
                f"Check:\n"
                f"- File format (must be .pfx/.p12 or PEM/DER)\n"
                f"- File password (if password-protected)\n"
                f"- File permissions and integrity\n\n"
                f"See the terminal/console for detailed error messages."
            )
            return

        cert_info.password = password
        self.available_certificates.append(cert_info)
        self.selected_certificate_password = password
        self.cert_password_var.set(bool(password))

        if self.certificate_combo:
            self.certificate_combo['values'] = [cert.friendly_name for cert in self.available_certificates]
            self.certificate_combo.current(len(self.available_certificates) - 1)
        self._update_certificate_display(cert_info)

    def _update_certificate_display(self, cert: Optional[CertificateInfo] = None) -> None:
        """Update the certificate display labels based on selected certificate"""
        if cert:
            self.selected_certificate = cert
        elif self.certificate_combo:
            index = self.certificate_combo.current()
            if 0 <= index < len(self.available_certificates):
                self.selected_certificate = self.available_certificates[index]
                cert = self.selected_certificate
            else:
                self.selected_certificate = None
                cert = None
        else:
            cert = self.selected_certificate

        if cert:
            # Update status label with certificate info
            status_text = f"Subject: {cert.friendly_name}\n"
            status_text += f"Valid to: {cert.valid_to}"
            if self.certificate_status_label:
                self.certificate_status_label.config(text=status_text, fg="#5cb85c")

            # Update external-password checkbox based on whether this certificate has a stored PKCS#12 password
            self.selected_certificate_password = cert.password
            self.cert_password_var.set(bool(cert.password))

            # Extract and display signer name from certificate
            signer_name = self._extract_signer_name_from_cert(cert)
            if self.signer_name_label:
                self.signer_name_label.config(text=signer_name if signer_name else "Unknown")
            if self.certificate_validity_label:
                valid_text = f"Valid to: {cert.valid_to}"
                if self._is_certificate_expired(cert):
                    self.certificate_validity_label.config(text=valid_text, fg="#d9534f")
                else:
                    self.certificate_validity_label.config(text=valid_text, fg="#5cb85c")
            # Save preference
            Preferences.set_selected_certificate_thumbprint(cert.thumbprint)
            Preferences.set_selected_certificate_friendly_name(cert.friendly_name)
            Preferences.set_selected_certificate_path(cert.cert_path)
        else:
            if self.certificate_status_label:
                self.certificate_status_label.config(
                    text="No certificate selected",
                    fg="#666"
                )
            if self.signer_name_label:
                self.signer_name_label.config(text="(From certificate)")
            if self.certificate_validity_label:
                self.certificate_validity_label.config(text="", fg="#666")
            # Clear preferences
            Preferences.set_selected_certificate_thumbprint(None)
            Preferences.set_selected_certificate_friendly_name(None)
            Preferences.set_selected_certificate_path(None)

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
            self.selected_certificate = self.available_certificates[selected_index]
            if self.certificate_combo:
                self.certificate_combo.current(selected_index)
            self._update_certificate_display(self.selected_certificate)
        elif self.available_certificates:
            # No saved preference found, select first certificate as default
            self.selected_certificate = self.available_certificates[0]
            if self.certificate_combo:
                self.certificate_combo.current(0)
            self._update_certificate_display(self.selected_certificate)
        else:
            # No certificates available
            self.selected_certificate = None
            if self.certificate_status_label:
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

        # Restore a saved certificate file path if needed
        cert_file_path = Preferences.get_selected_certificate_path()
        if cert_file_path and os.path.isfile(cert_file_path):
            cert_info = CertificateManager.load_certificate_file(cert_file_path)

            if not cert_info and cert_file_path.lower().endswith(('.pfx', '.p12')):
                while True:
                    password = simpledialog.askstring(
                        "Certificate Password",
                        "Enter the password for the saved certificate file:",
                        show="*"
                    )
                    if password is None:
                        break

                    cert_info = CertificateManager.load_certificate_file(cert_file_path, password=password)
                    if cert_info:
                        cert_info.password = password
                        self.selected_certificate_password = password
                        self.cert_password_var.set(True)
                        break

                    messagebox.showerror(
                        "Certificate Password",
                        "Invalid password for the saved certificate file. Please try again."
                    )

            if cert_info and not any(c.thumbprint == cert_info.thumbprint for c in self.available_certificates):
                self.available_certificates.append(cert_info)
                if self.certificate_combo:
                    self.certificate_combo['values'] = [cert.friendly_name for cert in self.available_certificates]
            elif not cert_info and cert_file_path.lower().endswith(('.pfx', '.p12')):
                if self.certificate_status_label:
                    self.certificate_status_label.config(
                        text="Saved certificate file could not be loaded. Load again manually.",
                        fg="#d9534f"
                    )

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
        disp_w = int(page_w * scale)
        disp_h = int(page_h * scale)
        x_offset = (CANVAS_WIDTH - disp_w) / 2
        y_offset = (CANVAS_HEIGHT - disp_h) / 2

        canvas_x = x * scale + x_offset
        canvas_y = CANVAS_HEIGHT - (y * scale) - y_offset
        return canvas_x, canvas_y

    def canvas_to_pdf_coords(self, x: float, y: float, page_size: Tuple[float, float]) -> Tuple[float, float]:
        page_w, page_h = page_size
        scale = min(CANVAS_WIDTH / page_w, CANVAS_HEIGHT / page_h)
        disp_w = int(page_w * scale)
        disp_h = int(page_h * scale)
        x_offset = (CANVAS_WIDTH - disp_w) / 2
        y_offset = (CANVAS_HEIGHT - disp_h) / 2

        pdf_x = (x - x_offset) / scale
        pdf_y = (CANVAS_HEIGHT - y - y_offset) / scale
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
        if not self.selected_certificate and not self.visual_only_var.get():
            messagebox.showwarning("Sign PDF", "Please select a digital certificate first or enable 'Visual signature only'.")
            return

        is_visual_only = self.visual_only_var.get()
        signer_name = "Visual Signature" if is_visual_only else self._extract_signer_name_from_cert(self.selected_certificate)
        cert_password = self.selected_certificate_password
        certificate_to_use = None if is_visual_only else self.selected_certificate

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
                visual_only=is_visual_only
            )
            output_pdf = os.path.splitext(self.pdf_path)[0] + "_signed.pdf"
            signing_succeeded = self.merge_overlay(
                self.pdf_path,
                overlay_path,
                self.selection,
                output_pdf,
                certificate=certificate_to_use,
                password=cert_password,
                signer_name=signer_name
            )

            # If visual_only is not checked and digital signing failed, don't proceed
            if not self.visual_only_var.get() and not signing_succeeded:
                if os.path.exists(output_pdf):
                    os.remove(output_pdf)
                messagebox.showerror("Sign PDF", "Digital signature failed. Please check your certificate or enable 'Visual signature only'.")
                return

            if is_visual_only:
                messagebox.showinfo(
                    "Sign PDF",
                    f"PDF signed with visual signature and saved:\n{output_pdf}\n\n"
                    f"Type: Visual Signature Only"
                )
            else:
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
        visual_only: bool = False,
    ) -> None:
        c = canvas.Canvas(output_path, pagesize=(page_width, page_height))

        if visual_only:
            if signature_image_path and os.path.isfile(signature_image_path):
                try:
                    image_reader = ImageReader(signature_image_path)
                    img_w, img_h = image_reader.getSize()
                    if img_w > 0 and img_h > 0:
                        scale = min(placement.width / img_w, placement.height / img_h, 1.0)
                        img_w = img_w * scale
                        img_h = img_h * scale
                        image_x = placement.x + (placement.width - img_w) / 2
                        image_y = placement.y + (placement.height - img_h) / 2
                        c.drawImage(image_reader, image_x, image_y, width=img_w, height=img_h, mask="auto")
                except Exception:
                    pass
            c.save()
            return

        c.setStrokeColorRGB(0.867, 0.894, 1.)
        c.setFillColorRGB(0, 0, 0)
        c.setLineWidth(1)
        c.rect(placement.x, placement.y, placement.width, placement.height)

        text_font_size = 6
        # Calculate text positioning - center vertically in the signature box
        text_lines = [
            ("Digitally signed by:", "Helvetica-Bold", text_font_size),
            (signer_name, "Helvetica", text_font_size),
            (f"Reason: {signature_type}", "Helvetica", text_font_size),
            (f"Date: {CertificateManager.get_current_time_iso()}", "Helvetica", text_font_size)
        ]

        # Calculate total text height
        total_text_height = 0
        line_spacing = 2  # points between lines
        for text, font_name, font_size in text_lines:
            total_text_height += font_size + line_spacing
        total_text_height -= line_spacing  # Remove extra spacing after last line
        line_height = text_font_size + line_spacing

        # Center text vertically in the signature box
        # Start from the top of the centered text block
        box_center_y = placement.y + placement.height / 2
        text_start_y = box_center_y + total_text_height / 2

        text_x_offset = 0.01 * inch
        text_x = placement.x + text_x_offset
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
                    text_x = image_x + img_w + text_x_offset
            except Exception:
                text_x = placement.x + text_x_offset

        # Draw text lines with proper vertical centering
        current_y = text_start_y
        for text, font_name, font_size in text_lines:
            c.setFont(font_name, font_size)
            c.drawString(text_x, current_y, text)
            current_y -= line_height
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
    ) -> bool:
        """Merge overlay with PDF and add digital signature

        Returns True if digital signing succeeded (or was not attempted), False if it failed
        """
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
            return PdfSigner._add_digital_signature(output_pdf, certificate, placement, password, signer_name)

        # No certificate provided, so visual-only signing is successful
        return True

    @staticmethod
    def _add_digital_signature(
        pdf_path: str,
        certificate: CertificateInfo,
        placement: SignaturePlacement,
        password: Optional[str] = None,
        signer_name: Optional[str] = None
    ) -> bool:
        """
        Add digital signature to PDF using X.509 certificate from Windows store

        Returns True if signing succeeded, False otherwise
        """
        try:
            temp_signed = pdf_path + ".temp"

            # Use CertificateManager to try real cryptographic signing first
            from classes.CertificateManager import CertificateManager
            success = CertificateManager.sign_pdf_with_certificate(
                pdf_path,
                certificate.cert_path if certificate.cert_path else certificate.thumbprint,
                temp_signed,
                password=password,
                signer_name=signer_name
            )

            if success and os.path.exists(temp_signed):
                os.replace(temp_signed, pdf_path)
                print("✓ Digital signature added successfully")
                return True

            return False

        except Exception as e:
            print(f"✗ Digital signature error: {e}")
            return False
