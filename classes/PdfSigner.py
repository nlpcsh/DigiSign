import os
import tempfile
from typing import Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from PIL import Image, ImageTk
import fitz
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

from classes.DataClasses import SignaturePlacement, CertificateInfo
from classes.CertificateManager import CertificateManager
from classes.Preferences import Preferences
from classes.UIBuilder import UIBuilder

DEFAULT_WIDTH = 3 * inch
DEFAULT_HEIGHT = 1 * inch

class PdfSigner:
    """
    Main PDF signer application.

    Manages PDF signing with digital certificates and visual signatures.
    Handles UI interactions, certificate management, and PDF operations.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("DigiSign PDF Signer")

        # Initialize state
        self._initialize_state()

        # Build UI
        self._build_ui()

        # Setup event handlers
        self._setup_event_handlers()

        # Load initial data
        self.load_certificates()
        self.load_preferences()

    def _initialize_state(self) -> None:
        """Initialize application state variables."""
        # Canvas dimensions from preferences
        self.canvas_width = Preferences.get_canvas_width()
        self.canvas_height = Preferences.get_canvas_height()

        # PDF state
        self.pdf_path: Optional[str] = None
        self.reader: Optional[PdfReader] = None
        self.page_size: Tuple[float, float] = (0.0, 0.0)
        self.selection: Optional[SignaturePlacement] = None
        self.drag_start: Optional[Tuple[float, float]] = None
        self.selection_rect_id: Optional[int] = None
        self.fitz_doc: Optional[fitz.Document] = None
        self.page_image_tk: Optional[ImageTk.PhotoImage] = None

        # Signature state
        self.signature_image_path: Optional[str] = None

        # Certificate state
        self.selected_certificate: Optional[CertificateInfo] = None
        self.available_certificates: list[CertificateInfo] = []
        self.selected_certificate_password: Optional[str] = None

        # Page navigation variables
        self.page_var = tk.IntVar(value=1)

    def _build_ui(self) -> None:
        """Build the user interface."""
        # Toolbar
        toolbar = UIBuilder.build_toolbar(self.root)
        self._toolbar_buttons = UIBuilder.build_buttons(toolbar, {
            "open_pdf": self.open_pdf,
            "load_certificates": self.load_certificates,
            "load_certificate_file": self.load_certificate_file,
        })

        # Page navigation
        self.page_frame, self.page_spin, self.page_var, self.info_label = UIBuilder.build_page_frame(self.root)
        self.page_spin.config(command=self.on_page_change)

        # Main content area
        content = tk.Frame(self.root)
        content.pack(fill="both", expand=True, padx=8, pady=8)

        # Canvas with dimensions from instance variables
        self.canvas = UIBuilder.build_canvas(content, self.canvas_width, self.canvas_height)

        # Sidebar
        _, sidebar_components = UIBuilder.build_sidebar(content, {
            "load_signature_image": self.load_signature_image,
            "complete_signing": self.complete_signing,
        })
        self._setup_sidebar_components(sidebar_components)

    def _setup_sidebar_components(self, components: dict) -> None:
        """Extract and store sidebar components."""
        # Certificate UI components
        self.certificate_combo = components.get("cert_combo")
        self.certificate_status_label = components.get("cert_status_label")
        self.signer_name_label = components.get("signer_name_label")
        self.certificate_validity_label = components.get("cert_validity_label")

        # Signature UI components
        self.visual_only_var = components.get("visual_only_var", tk.BooleanVar(value=False))
        self.signature_image_label = components.get("signature_image_label")
        self.selection_label = components.get("selection_label")

        # Signature declaration
        self.signature_declaration_var = components.get("signature_declaration_var", tk.StringVar(value="I'm the author"))
        self.signature_declaration_combo = components.get("signature_declaration_combo")

    def _setup_event_handlers(self) -> None:
        """Bind event handlers to UI components."""
        if self.certificate_combo:
            self.certificate_combo.bind("<<ComboboxSelected>>", self._update_certificate_display)

        if self.signature_declaration_combo:
            self.signature_declaration_combo.bind("<<ComboboxSelected>>", self.on_signature_declaration_selected)

        # Canvas events
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

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

                if not cert_names and self.certificate_status_label:
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

        if self.certificate_combo:
            self.certificate_combo['values'] = [cert.friendly_name for cert in self.available_certificates]
            self.certificate_combo.current(len(self.available_certificates) - 1)
        self._update_certificate_display(cert_info)

    def _update_certificate_display(self, cert: Optional[CertificateInfo] = None) -> None:
        """Update the certificate display labels based on selected certificate"""
        cert = self._resolve_certificate(cert)
        self.selected_certificate = cert

        if not cert:
            self._clear_certificate_display()
            self._clear_certificate_preferences()
            return

        self._update_certificate_labels(cert)
        self._update_certificate_preferences(cert)

    def _resolve_certificate(self, cert: Optional[CertificateInfo]) -> Optional[CertificateInfo]:
        if cert:
            return cert

        if not self.certificate_combo:
            return self.selected_certificate

        index = self.certificate_combo.current()
        if 0 <= index < len(self.available_certificates):
            return self.available_certificates[index]

        return None

    def _update_certificate_labels(self, cert: CertificateInfo) -> None:
        status_text = f"Subject: {cert.friendly_name}\nValid to: {cert.valid_to}"

        if self.certificate_status_label:
            self.certificate_status_label.config(text=status_text, fg="#5cb85c")

        self.selected_certificate_password = cert.password

        signer_name = self._extract_signer_name_from_cert(cert)
        if self.signer_name_label:
            self.signer_name_label.config(text=signer_name or "Unknown")

        if self.certificate_validity_label:
            valid_text = f"Valid to: {cert.valid_to}"
            color = "#d9534f" if self._is_certificate_expired(cert) else "#5cb85c"
            self.certificate_validity_label.config(text=valid_text, fg=color)

    def _clear_certificate_display(self) -> None:
        if self.certificate_status_label:
            self.certificate_status_label.config(text="No certificate selected", fg="#666")

        if self.signer_name_label:
            self.signer_name_label.config(text="(From certificate)")

        if self.certificate_validity_label:
            self.certificate_validity_label.config(text="", fg="#666")

    def _update_certificate_preferences(self, cert: CertificateInfo) -> None:
        Preferences.set_selected_certificate_thumbprint(cert.thumbprint)
        Preferences.set_selected_certificate_friendly_name(cert.friendly_name)
        Preferences.set_selected_certificate_path(cert.cert_path)

    def _clear_certificate_preferences(self) -> None:
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
        index = self._find_preferred_certificate_index()

        if index is None:
            self._handle_no_certificates()
            return

        self._select_certificate_by_index(index)


    def _find_preferred_certificate_index(self) -> Optional[int]:
        certs = self.available_certificates
        if not certs:
            return None

        thumbprint = Preferences.get_selected_certificate_thumbprint()
        name = Preferences.get_selected_certificate_friendly_name()

        for i, cert in enumerate(certs):
            if thumbprint and cert.thumbprint == thumbprint:
                return i
            if name and cert.friendly_name == name:
                return i

        return 0  # fallback to first certificate

    def _select_certificate_by_index(self, index: int) -> None:
        cert = self.available_certificates[index]
        self.selected_certificate = cert

        if self.certificate_combo:
            self.certificate_combo.current(index)

        self._update_certificate_display(cert)

    def _handle_no_certificates(self) -> None:
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
        self._load_signature_image()
        self._restore_certificate_from_preferences()
        self._apply_certificate_preferences()
        self._load_signature_declaration()

    def _load_signature_image(self) -> None:
        path = Preferences.get_signature_image_path()
        if path and os.path.isfile(path):
            self.signature_image_path = path
            self.update_signature_image_label()

    def _restore_certificate_from_preferences(self) -> None:
        path = Preferences.get_selected_certificate_path()
        if not path or not os.path.isfile(path):
            return

        cert = self._load_certificate_with_optional_password(path)

        if cert:
            self._add_certificate_if_missing(cert)
        elif path.lower().endswith(('.pfx', '.p12')):
            self._show_certificate_load_error()

    def _load_certificate_with_optional_password(self, path: str) -> Optional[CertificateInfo]:
        cert = CertificateManager.load_certificate_file(path)
        if cert or not path.lower().endswith(('.pfx', '.p12')):
            return cert

        return self._prompt_for_certificate_password(path)

    def _prompt_for_certificate_password(self, path: str) -> Optional[CertificateInfo]:
        while True:
            password = simpledialog.askstring(
                "Certificate Password",
                "Enter the password for the saved certificate file:",
                show="*"
            )
            if password is None:
                return None

            cert = CertificateManager.load_certificate_file(path, password=password)
            if cert:
                cert.password = password
                self.selected_certificate_password = password
                return cert

            messagebox.showerror(
                "Certificate Password",
                "Invalid password for the saved certificate file. Please try again."
            )

    def _add_certificate_if_missing(self, cert: CertificateInfo) -> None:
        if any(c.thumbprint == cert.thumbprint for c in self.available_certificates):
            return

        self.available_certificates.append(cert)

        if self.certificate_combo:
            self.certificate_combo['values'] = [
                c.friendly_name for c in self.available_certificates
            ]

    def _show_certificate_load_error(self) -> None:
        if self.certificate_status_label:
            self.certificate_status_label.config(
                text="Saved certificate file could not be loaded. Load again manually.",
                fg="#d9534f"
            )

    def _load_signature_declaration(self) -> None:
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
        scale = min(self.canvas_width / page_w, self.canvas_height / page_h)
        disp_w = int(page_w * scale)
        disp_h = int(page_h * scale)
        x_offset = (self.canvas_width - disp_w) / 2
        y_offset = (self.canvas_height - disp_h) / 2

        canvas_x = x * scale + x_offset
        canvas_y = self.canvas_height - (y * scale) - y_offset
        return canvas_x, canvas_y

    def canvas_to_pdf_coords(self, x: float, y: float, page_size: Tuple[float, float]) -> Tuple[float, float]:
        page_w, page_h = page_size
        scale = min(self.canvas_width / page_w, self.canvas_height / page_h)
        disp_w = int(page_w * scale)
        disp_h = int(page_h * scale)
        x_offset = (self.canvas_width - disp_w) / 2
        y_offset = (self.canvas_height - disp_h) / 2

        pdf_x = (x - x_offset) / scale
        pdf_y = (self.canvas_height - y - y_offset) / scale
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
            self.canvas.create_text(self.canvas_width / 2, self.canvas_height / 2, text="Open a PDF to start", fill="#666")
            return

        page_w, page_h = self.page_size
        scale = min(self.canvas_width / page_w, self.canvas_height / page_h)
        disp_w = int(page_w * scale)
        disp_h = int(page_h * scale)
        x0 = (self.canvas_width - disp_w) / 2
        y0 = (self.canvas_height - disp_h) / 2
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
            PdfSigner._draw_centered_image(c, placement, signature_image_path)
            c.save()
            return

        PdfSigner._draw_border(c, placement)

        text_lines = PdfSigner._build_text_lines(signer_name, signature_type)
        text_start_y, line_height = PdfSigner._calculate_text_layout(placement, text_lines)

        text_x = placement.x + 0.1 * inch
        text_x = PdfSigner._draw_image_and_adjust_text_x(
            c, placement, signature_image_path, text_x
        )

        PdfSigner._draw_text_lines(c, text_lines, text_x, text_start_y, line_height)
        c.save()

    @staticmethod
    def _draw_border(c, placement: SignaturePlacement) -> None:
        c.setStrokeColorRGB(0.867, 0.894, 1.0)
        c.setFillColorRGB(0, 0, 0)
        c.setLineWidth(1)
        c.rect(placement.x, placement.y, placement.width, placement.height)

    @staticmethod
    def _build_text_lines(signer_name: str, signature_type: str):
        size = 6
        return [
            ("Digitally signed by:", "Helvetica", size),
            (signer_name, "Helvetica-Bold", size),
            (f"Reason: {signature_type}", "Helvetica", size),
            (f"Date: {CertificateManager.get_current_time_iso()}", "Helvetica", size),
        ]

    @staticmethod
    def _calculate_text_layout(placement: SignaturePlacement, text_lines):
        line_spacing = 2
        total_height = sum(size + line_spacing for _, _, size in text_lines) - line_spacing
        line_height = text_lines[0][2] + line_spacing

        box_center_y = placement.y + placement.height / 2
        start_y = box_center_y + total_height / 2 - line_height / 2 - line_spacing / 2

        return start_y, line_height

    @staticmethod
    def _draw_centered_image(c, placement: SignaturePlacement, path: Optional[str]) -> None:
        if not path or not os.path.isfile(path):
            return

        try:
            reader = ImageReader(path)
            img_w, img_h = reader.getSize()
            if img_w <= 0 or img_h <= 0:
                return

            scale = min(placement.width / img_w, placement.height / img_h, 1.0)
            w, h = img_w * scale, img_h * scale

            x = placement.x + (placement.width - w) / 2
            y = placement.y + (placement.height - h) / 2

            c.drawImage(reader, x, y, width=w, height=h, mask="auto")
        except Exception:
            pass

    @staticmethod
    def _draw_image_and_adjust_text_x(c, placement, path, default_text_x):
        if not path or not os.path.isfile(path):
            return default_text_x

        try:
            reader = ImageReader(path)
            img_w, img_h = reader.getSize()
            if img_w <= 0 or img_h <= 0:
                return default_text_x

            margin = 0.08 * inch
            area_w = placement.width * 0.35
            area_h = placement.height - (margin * 2)

            scale = min(area_w / img_w, area_h / img_h, 1.0)
            w, h = img_w * scale, img_h * scale

            x = placement.x + margin
            y = placement.y + placement.height - h - margin

            c.drawImage(reader, x, y, width=w, height=h, mask="auto")
            return x + w + 0.1 * inch

        except Exception:
            return default_text_x

    @staticmethod
    def _draw_text_lines(c, text_lines, x, start_y, line_height):
        y = start_y
        for text, font, size in text_lines:
            c.setFont(font, size)
            c.drawString(x, y, text)
            y -= line_height

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
