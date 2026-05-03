"""
UI Builder for DigiSign PDF Signer
Separates UI construction logic from the main application logic.
"""
import platform
import tkinter as tk
from tkinter import ttk


class UIBuilder:
    """Builds and manages UI components for the PDF signer application."""

    @staticmethod
    def build_toolbar(root: tk.Tk) -> tk.Frame:
        """Create the top toolbar with PDF and certificate buttons."""
        toolbar = tk.Frame(root)
        toolbar.pack(fill="x", padx=8, pady=8)
        return toolbar

    @staticmethod
    def build_buttons(toolbar: tk.Frame, callbacks: dict) -> dict:
        """Create toolbar buttons with provided callbacks."""
        buttons = {}

        tk.Button(toolbar, text="Open PDF", command=callbacks["open_pdf"]).pack(side="left")

        if platform.system() != "Linux":
            buttons["refresh_certs"] = tk.Button(
                toolbar,
                text="Refresh Certificates",
                command=callbacks["load_certificates"]
            )
            buttons["refresh_certs"].pack(side="left", padx=(8, 0))

        if platform.system() != "Windows":
            buttons["load_cert_file"] = tk.Button(
                toolbar,
                text="Load certificate file",
                command=callbacks["load_certificate_file"]
            )
            buttons["load_cert_file"].pack(side="left", padx=(8, 0))

        return buttons

    @staticmethod
    def build_page_frame(root: tk.Tk) -> tuple[tk.Frame, tk.Label, tk.Spinbox, tk.IntVar, tk.Label]:
        """Create the page navigation frame."""
        page_frame = tk.Frame(root)
        page_frame.pack(fill="x", padx=8)

        tk.Label(page_frame, text="Page:").pack(side="left")
        page_var = tk.IntVar(value=1)
        page_spin = tk.Spinbox(
            page_frame,
            from_=1,
            to=1,
            width=5,
            textvariable=page_var
        )
        page_spin.pack(side="left", padx=(0, 12))

        info_label = tk.Label(page_frame, text="No file loaded")
        info_label.pack(side="left")

        return page_frame, page_spin, page_var, info_label

    @staticmethod
    def build_canvas(content: tk.Frame, width: int = 680, height: int = 900) -> tk.Canvas:
        """Create the PDF preview canvas."""
        canvas = tk.Canvas(content, width=width, height=height, bg="#f0f0f0")
        canvas.pack(side="left", fill="both", expand=True)
        return canvas

    @staticmethod
    def build_sidebar(content: tk.Frame, callbacks: dict = None) -> tuple[tk.Frame, dict]:
        """Create the right sidebar with certificate and signing options."""
        if callbacks is None:
            callbacks = {}

        sidebar = tk.Frame(content, padx=12)
        sidebar.pack(side="right", fill="y")

        components = {}

        # Certificate section (platform-specific)
        if platform.system() != "Linux":
            tk.Label(sidebar, text="Digital Certificate:", font=("TkDefaultFont", 10, "bold")).pack(
                anchor="w", pady=(0, 6)
            )
            components["cert_combo"] = ttk.Combobox(sidebar, state="readonly", width=25)
            components["cert_combo"].pack(fill="x", pady=(0, 6))

            components["cert_status_label"] = tk.Label(
                sidebar,
                text="No certificate selected",
                wraplength=160,
                justify="left",
                fg="#666"
            )
            components["cert_status_label"].pack(anchor="w", pady=(0, 12))

        # Signer name info
        tk.Label(sidebar, text="Signer name:").pack(anchor="w")
        components["signer_name_label"] = tk.Label(
            sidebar,
            text="(From certificate)",
            wraplength=160,
            justify="left",
            fg="#666"
        )
        components["signer_name_label"].pack(anchor="w", pady=(0, 2))

        components["cert_validity_label"] = tk.Label(
            sidebar,
            text="",
            wraplength=160,
            justify="left",
            fg="#666"
        )
        components["cert_validity_label"].pack(anchor="w", pady=(0, 12))

        # Password info
        tk.Label(
            sidebar,
            text="Password is set outside this app on certificate load or sign use.",
            font=("TkDefaultFont", 8),
            fg="#999"
        ).pack(anchor="w", pady=(0, 12))

        # Visual-only option
        components["visual_only_var"] = tk.BooleanVar(value=False)
        tk.Checkbutton(
            sidebar,
            text="Visual signature only\n(no digital certificate)",
            variable=components["visual_only_var"],
            onvalue=True,
            offvalue=False
        ).pack(anchor="w", pady=(0, 12))

        tk.Label(
            sidebar,
            text="Sign with image only, even if certificate is unavailable.",
            font=("TkDefaultFont", 8),
            fg="#999"
        ).pack(anchor="w", pady=(0, 12))

        # Signature declaration
        tk.Label(sidebar, text="Signature statement:").pack(anchor="w")
        components["signature_declaration_var"] = tk.StringVar(value="I'm the author")
        components["signature_declaration_combo"] = ttk.Combobox(
            sidebar,
            state="readonly",
            width=25,
            textvariable=components["signature_declaration_var"],
            values=["I'm the author", "I reviewed this document"]
        )
        components["signature_declaration_combo"].pack(fill="x", pady=(0, 12))
        components["signature_declaration_combo"].current(0)

        # Signature image
        load_sig_callback = callbacks.get("load_signature_image", lambda: None)
        tk.Button(sidebar, text="Load signature image", command=load_sig_callback).pack(fill="x")
        components["signature_image_label"] = tk.Label(
            sidebar,
            text="No signature image loaded",
            wraplength=160,
            justify="left"
        )
        components["signature_image_label"].pack(anchor="w", pady=(6, 12))

        # Selection display
        tk.Label(sidebar, text="Selection (PDF points):").pack(anchor="w")
        components["selection_label"] = tk.Label(
            sidebar,
            text="x=0.0 y=0.0 w=0.0 h=0.0",
            justify="left"
        )
        components["selection_label"].pack(anchor="w", pady=(0, 12))

        # Instructions
        tk.Label(sidebar, text="Instructions:").pack(anchor="w")
        tk.Label(
            sidebar,
            text="1) Select a certificate or load a certificate file\n2) Open a PDF\n3) Drag to draw signature box\n4) Load signature image (optional)\n5) Click Sign PDF",
            justify="left",
            fg="#333333"
        ).pack(anchor="w")

        # Sign button
        sign_callback = callbacks.get("complete_signing", lambda: None)
        tk.Button(sidebar, text="Sign PDF", command=sign_callback, bg="white", fg="blue").pack(
            fill="x", pady=(12, 0)
        )

        return sidebar, components
