import os
import platform
import subprocess
import json
import tempfile
from pathlib import Path
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
    valid_to: str
    friendly_name: str
    cert_path: Optional[str] = None  # Path to exported cert file
    password: Optional[str] = None  # Password for PKCS#12 certificate if loaded


class CertificateManager:
    """Manages X.509 certificates from Windows certificate store and local certificate files"""

    CERT_FILE_DIR = Path.home() / ".digisign" / "certs"

    @staticmethod
    def list_certificates() -> List[CertificateInfo]:
        """List available signing certificates from the local certificate directory and Windows certificate store."""
        certificates = []

        if platform.system() == "Windows":
            try:
                # Use PowerShell to get certificates from the Windows Personal store
                ps_command = r"""
$certs = Get-ChildItem -Path Cert:\CurrentUser\My -ErrorAction SilentlyContinue
$result = @()
foreach ($cert in $certs) {
    $result += @{
        FriendlyName = $cert.FriendlyName
        Subject = $cert.Subject
        Thumbprint = $cert.Thumbprint
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
                        if not isinstance(cert_data, list):
                            cert_data = [cert_data]

                        for cert_dict in cert_data:
                            if cert_dict.get('Thumbprint'):
                                friendly_name = cert_dict.get('FriendlyName', '').strip() or cert_dict.get('Subject', 'Unknown')
                                cert_info = CertificateInfo(
                                    subject=cert_dict.get('Subject', ''),
                                    issuer=cert_dict.get('Issuer', ''),
                                    thumbprint=cert_dict.get('Thumbprint', ''),
                                    valid_to=cert_dict.get('NotAfter', '').split('T')[0],
                                    friendly_name=friendly_name
                                )
                                certificates.append(cert_info)
                    except ValueError:
                        pass
            except Exception:
                pass

        try:
            cert_paths = CertificateManager._get_certificate_files()
            for cert_path in cert_paths:
                try:
                    ext = os.path.splitext(cert_path)[1].lower()
                    if ext in {'.pfx', '.p12'}:
                        continue
                    cert_info = CertificateManager.load_certificate_file(cert_path)
                    if cert_info and not any(c.thumbprint == cert_info.thumbprint for c in certificates):
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
            except Exception as pem_exc:
                # Try DER
                try:
                    cert = x509.load_der_x509_certificate(cert_data, default_backend())
                except Exception as der_exc:
                    print(f"Failed to load as PEM: {pem_exc}")
                    print(f"Failed to load as DER: {der_exc}")
                    return None

            subject = cert.subject.rfc4514_string()
            issuer = cert.issuer.rfc4514_string()

            # Calculate thumbprint (SHA-1 hash)
            thumbprint = cert.fingerprint(hashes.SHA1()).hex().upper()

            valid_to = cert.not_valid_after_utc.isoformat().split('T')[0]

            friendly_name = CertificateManager._extract_cn(subject)

            print(f"Successfully loaded PEM/DER certificate from {cert_path}")
            print(f"  Subject: {subject}")
            print(f"  Thumbprint: {thumbprint}")

            return CertificateInfo(
                subject=subject,
                issuer=issuer,
                thumbprint=thumbprint,
                valid_to=valid_to,
                friendly_name=friendly_name,
                cert_path=cert_path
            )

        except Exception as exc:
            print(f"Failed to load certificate file {cert_path}: {exc}")
            return None

    @staticmethod
    def load_certificate_file(cert_path: str, password: Optional[str] = None) -> Optional[CertificateInfo]:
        """Load a certificate from a file path, supporting PEM/DER and PKCS#12 files."""
        try:
            ext = os.path.splitext(cert_path)[1].lower()
            if ext in {'.pfx', '.p12'}:
                return CertificateManager._load_pkcs12_certificate(cert_path, password=password)
            return CertificateManager._load_certificate_from_file(cert_path)
        except Exception as exc:
            print(f"Error loading certificate file {cert_path}: {exc}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def _load_pkcs12_certificate(cert_path: str, password: Optional[str] = None) -> Optional[CertificateInfo]:
        """Load certificate metadata from a PKCS#12 file."""
        try:
            from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

            with open(cert_path, 'rb') as f:
                pfx_data = f.read()

            # Prepare password for PKCS#12 loading
            pfx_password = None
            if password:
                pfx_password = password.encode() if isinstance(password, str) else password

            # load_key_and_certificates returns (private_key, certificate, additional_certs)
            key, cert, additional = load_key_and_certificates(
                pfx_data,
                pfx_password,
                default_backend()
            )

            if cert is None:
                print(f"No certificate found in PKCS#12 file: {cert_path}")
                return None

            subject = cert.subject.rfc4514_string()
            issuer = cert.issuer.rfc4514_string()
            thumbprint = cert.fingerprint(hashes.SHA1()).hex().upper()
            valid_to = cert.not_valid_after_utc.isoformat().split('T')[0]
            friendly_name = CertificateManager._extract_cn(subject)

            print(f"Successfully loaded certificate from {cert_path}")
            print(f"  Subject: {subject}")
            print(f"  Thumbprint: {thumbprint}")

            return CertificateInfo(
                subject=subject,
                issuer=issuer,
                thumbprint=thumbprint,
                valid_to=valid_to,
                friendly_name=friendly_name,
                cert_path=cert_path
            )
        except Exception as exc:
            print(f"Failed to load PKCS#12 certificate {cert_path}: {exc}")
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
        """Get paths to certificate files from the local DigiSign certificate directory."""
        cert_paths = []

        try:
            CertificateManager.CERT_FILE_DIR.mkdir(parents=True, exist_ok=True)
            for filename in os.listdir(CertificateManager.CERT_FILE_DIR):
                if filename.lower().endswith(('.pfx', '.p12', '.pem', '.crt', '.cer')):
                    cert_paths.append(str(CertificateManager.CERT_FILE_DIR / filename))
        except Exception:
            pass

        return cert_paths

    @staticmethod
    def export_certificate_and_key(thumbprint: str, password: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Export certificate and private key from Windows store as PFX
        Returns tuple of (pfx_path, password) if successful
        """
        if platform.system() != "Windows":
            return None, None

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
                timeout=25
            )

            if result.returncode == 0 and "SUCCESS" in result.stdout:
                if os.path.exists(pfx_path) and os.path.getsize(pfx_path) > 0:
                    return pfx_path, password
            else:
                raise Exception(f"Certificate export failed: {result.stdout.strip()}")

            print(f"Export result: {result.stdout.strip()}")
            if result.stderr:
                print(f"PowerShell stderr: {result.stderr}")

        except Exception as exc:
            print(f"Export exception: {exc}")

        return None, None

    @staticmethod
    def _sign_pdf_with_pkcs12_file(
        pfx_path: str,
        password: Optional[str],
        pdf_path: str,
        output_path: str,
        signer_name: Optional[str] = None
    ) -> bool:
        """Sign a PDF using a local PKCS#12 certificate file."""
        try:
            from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
            from pyhanko.sign import signers
            from pyhanko.sign.signers import SimpleSigner

            signer = SimpleSigner.load_pkcs12(
                pfx_file=pfx_path,
                passphrase=password.encode() if password else None
            )

            with open(pdf_path, 'rb') as inf, open(output_path, 'wb') as outf:
                w = IncrementalPdfFileWriter(inf)
                sig_meta = signers.PdfSignatureMetadata(
                    field_name='Signature1',
                    name=signer_name,
                    reason=f'Signed by {signer_name or os.path.basename(pfx_path)}',
                )
                signers.sign_pdf(w, sig_meta, signer=signer, output=outf)

            return True
        except Exception as exc:
            print(f"pyHanko signing failed for PKCS#12 file: {exc}")
            return False

    @staticmethod
    def sign_pdf_with_certificate(
        pdf_path: str,
        thumbprint_or_path: str,
        output_path: str,
        password: Optional[str] = None,
        signer_name: Optional[str] = None
    ) -> bool:
        """
        Sign a PDF using a PKCS#12 certificate file or a Windows store certificate.
        Returns True if a cryptographic signature was successfully applied.
        """
        try:
            if thumbprint_or_path and os.path.exists(thumbprint_or_path) and thumbprint_or_path.lower().endswith(('.pfx', '.p12')):
                return CertificateManager._sign_pdf_with_pkcs12_file(
                    thumbprint_or_path,
                    password,
                    pdf_path,
                    output_path,
                    signer_name
                )

            if platform.system() != "Windows":
                print("No Windows certificate store available on this platform")
                return False

            # Export the certificate and private key from the Windows store
            pfx_path, pfx_password = CertificateManager.export_certificate_and_key(thumbprint_or_path, password)
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
                        reason=f'Signed by {signer_name or thumbprint_or_path[:16]}',
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

    @staticmethod
    def get_current_time_iso() -> str:
        """Get the current time in ISO format"""
        from datetime import datetime
        return datetime.now().replace(microsecond=0).isoformat()
