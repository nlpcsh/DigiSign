import os
import subprocess
import json
import tempfile
from typing import List, Tuple, Optional
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


@dataclass
class CertificateInfo:
    """Information about an X.509 certificate"""
    subject: str
    issuer: str
    thumbprint: str
    valid_from: str
    valid_to: str
    friendly_name: str
    cert_path: Optional[str] = None  # Path to exported cert file


class CertificateManager:
    """Manages X.509 certificates from Windows certificate store"""

    @staticmethod
    def list_certificates() -> List[CertificateInfo]:
        """List all signing certificates from Windows certificate store"""
        certificates = []

        try:
            # Use PowerShell to get certificates - more reliable than certutil
            ps_command = """
$certs = Get-ChildItem -Path Cert:\\CurrentUser\\My -ErrorAction SilentlyContinue
$result = @()
foreach ($cert in $certs) {
    $result += @{
        FriendlyName = $cert.FriendlyName
        Subject = $cert.Subject
        Thumbprint = $cert.Thumbprint
        NotBefore = $cert.NotBefore.ToString('o')
        NotAfter = $cert.NotAfter.ToString('o')
        Issuer = $cert.Issuer
    }
}
$result | ConvertTo-Json -Depth 2
"""
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_command],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                try:
                    cert_data = json.loads(result.stdout.strip())
                    # Handle both single cert and multiple certs
                    if not isinstance(cert_data, list):
                        cert_data = [cert_data]

                    for cert_dict in cert_data:
                        if cert_dict.get('Thumbprint'):  # Only valid certs with thumbprints
                            friendly_name = cert_dict.get('FriendlyName', '').strip() or cert_dict.get('Subject', 'Unknown')
                            cert_info = CertificateInfo(
                                subject=cert_dict.get('Subject', ''),
                                issuer=cert_dict.get('Issuer', ''),
                                thumbprint=cert_dict.get('Thumbprint', ''),
                                valid_from=cert_dict.get('NotBefore', ''),
                                valid_to=cert_dict.get('NotAfter', ''),
                                friendly_name=friendly_name
                            )
                            certificates.append(cert_info)
                except (json.JSONDecodeError, ValueError):
                    # Fall back to file-based loading if JSON parsing fails
                    pass

        except Exception:
            pass

        # Also try to read from the certificate files directly as fallback
        try:
            cert_paths = CertificateManager._get_certificate_files()
            for cert_path in cert_paths:
                try:
                    cert_info = CertificateManager._load_certificate_from_file(cert_path)
                    if cert_info:
                        cert_info.cert_path = cert_path
                        # Avoid duplicates based on thumbprint
                        if not any(c.thumbprint == cert_info.thumbprint for c in certificates):
                            certificates.append(cert_info)
                except Exception:
                    continue
        except Exception:
            pass

        return certificates

    @staticmethod
    def _load_certificate_from_file(cert_path: str) -> Optional[CertificateInfo]:
        """Load certificate from PEM/DER file"""
        try:
            with open(cert_path, 'rb') as f:
                cert_data = f.read()

            # Try PEM first
            try:
                cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            except Exception:
                # Try DER
                cert = x509.load_der_x509_certificate(cert_data, default_backend())

            subject = cert.subject.rfc4514_string()
            issuer = cert.issuer.rfc4514_string()

            # Calculate thumbprint (SHA-1 hash)
            thumbprint = cert.fingerprint(hashes.SHA1()).hex().upper()

            valid_from = cert.not_valid_before.isoformat()
            valid_to = cert.not_valid_after.isoformat()

            friendly_name = CertificateManager._extract_cn(subject)

            return CertificateInfo(
                subject=subject,
                issuer=issuer,
                thumbprint=thumbprint,
                valid_from=valid_from,
                valid_to=valid_to,
                friendly_name=friendly_name,
                cert_path=cert_path
            )

        except Exception:
            return None

    @staticmethod
    def _extract_cn(subject: str) -> str:
        """Extract Common Name (CN) from subject string"""
        parts = subject.split(',')
        for part in parts:
            part = part.strip()
            if part.startswith('CN='):
                return part[3:].strip()
        return subject[:50]  # Return first 50 chars if CN not found

    @staticmethod
    def _get_certificate_files() -> List[str]:
        """Get paths to certificate files from common Windows locations"""
        cert_paths = []

        # Windows certificate store location
        cert_store_path = os.path.expandvars(r'%APPDATA%\Microsoft\SystemCertificates\My\Certificates')

        if os.path.exists(cert_store_path):
            try:
                for filename in os.listdir(cert_store_path):
                    cert_paths.append(os.path.join(cert_store_path, filename))
            except Exception:
                pass

        return cert_paths

    @staticmethod
    def export_certificate_and_key(thumbprint: str, password: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Export certificate and private key from Windows store as PFX
        Returns tuple of (pfx_path, password) if successful
        """
        try:
            temp_dir = tempfile.gettempdir()
            pfx_path = os.path.join(temp_dir, f'digisign_cert_{thumbprint[:8]}.pfx')

            # Use a random password if none provided
            if password is None:
                import secrets
                password = secrets.token_urlsafe(12)

            ps_command = f"""
$cert = Get-ChildItem -Path Cert:\\CurrentUser\\My -ErrorAction SilentlyContinue | Where-Object {{$_.Thumbprint -eq '{thumbprint}'}}
if ($cert) {{
    try {{
        $pfxPassword = ConvertTo-SecureString -String '{password}' -AsPlainText -Force
        Export-PfxCertificate -Cert $cert -FilePath "{pfx_path}" -Password $pfxPassword -ChainOption BuildChain -ErrorAction Stop | Out-Null
        Write-Output "SUCCESS"
    }}
    catch {{
        Write-Output "FAILED: $($_.Exception.Message)"
    }}
}}
else {{
    Write-Output "NOT_FOUND"
}}
"""
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_command],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0 and "SUCCESS" in result.stdout:
                if os.path.exists(pfx_path) and os.path.getsize(pfx_path) > 0:
                    return pfx_path, password

            print(f"Export result: {result.stdout.strip()}")
            if result.stderr:
                print(f"PowerShell stderr: {result.stderr}")

        except Exception as exc:
            print(f"Export exception: {exc}")

        return None, None

    @staticmethod
    def sign_pdf_with_certificate(
        pdf_path: str,
        thumbprint: str,
        output_path: str,
        password: Optional[str] = None,
        signer_name: Optional[str] = None
    ) -> bool:
        """
        Sign a PDF using a certificate from the Windows store.
        Returns True if a cryptographic signature was successfully applied.
        """
        try:
            # Export the certificate and private key from the Windows store
            pfx_path, pfx_password = CertificateManager.export_certificate_and_key(thumbprint, password)
            if not pfx_path:
                print("Certificate export failed")
                return False

            try:
                from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
                from pyhanko.sign import signers
                from pyhanko.sign.signers import SimpleSigner

                signer = SimpleSigner.load_pkcs12(
                    pfx_file=pfx_path,
                    passphrase=pfx_password.encode() if pfx_password else None
                )

                with open(pdf_path, 'rb') as inf, open(output_path, 'wb') as outf:
                    w = IncrementalPdfFileWriter(inf)
                    sig_meta = signers.PdfSignatureMetadata(
                        field_name='Signature1',
                        name=signer_name,
                        reason=f'Signed by {signer_name or thumbprint[:16]}',
                    )
                    signers.sign_pdf(w, sig_meta, signer=signer, output=outf)

                return True
            except Exception as exc:
                print(f"pyHanko signing failed: {exc}")
                return False
            finally:
                try:
                    os.remove(pfx_path)
                except Exception:
                    pass

        except Exception as exc:
            print(f"sign_pdf_with_certificate failed: {exc}")
            return False

    @staticmethod
    def sign_pdf_with_metadata(
        pdf_path: str,
        output_path: str,
        certificate: 'CertificateInfo',
        signer_name: Optional[str] = None
    ) -> bool:
        """
        Add digital signature metadata to PDF
        This provides signature information in the PDF properties without requiring private key access
        """
        try:
            from PyPDF2 import PdfReader, PdfWriter
            from datetime import datetime

            reader = PdfReader(pdf_path)
            writer = PdfWriter()

            # Copy all pages
            for page in reader.pages:
                writer.add_page(page)

            # Add comprehensive metadata
            timestamp = datetime.now().isoformat()
            writer.add_metadata({
                '/Producer': 'DigiSign PDF Signer v1.0',
                '/Title': 'Digitally Signed Document',
                '/Subject': f'Digitally signed by {signer_name or certificate.friendly_name}',
                '/Creator': f'{signer_name or certificate.friendly_name}',
                '/CreationDate': timestamp,
                '/ModDate': timestamp,
                '/Keywords': f'Digital Signature, Certificate: {certificate.thumbprint[:16]}...',
                '/Author': signer_name or certificate.friendly_name,
            })

            # Write to temp then move to final
            with open(output_path, 'wb') as out_file:
                writer.write(out_file)

            return True

        except Exception as exc:
            print(f"Metadata signing error: {exc}")
            return False
