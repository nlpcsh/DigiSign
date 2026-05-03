from dataclasses import dataclass
from typing import Optional

@dataclass
class SignaturePlacement:
    page_number: int
    x: float
    y: float
    width: float
    height: float

@dataclass
class CertificateInfo:
    """Information about an X.509 certificate"""
    subject: str
    issuer: str
    thumbprint: str
    valid_to: str
    friendly_name: str
    cert_path: Optional[str] = None  # Path to exported cert file
    password: Optional[str] = None  # Password for PKCS#12 certificate if loaded
