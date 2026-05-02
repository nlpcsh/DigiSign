# DigiSign - X.509 Certificate-Based PDF Signing

## Overview
DigiSign now supports digital PDF signing using X.509 certificates from the Windows certificate store and local certificate files. This adds cryptographic authenticity and non-repudiation to your PDF documents on Windows and Linux.

## Features

### Certificate Store Integration
- **Windows Certificate Lookup**: Automatically detects X.509 certificates in your Windows Personal certificate store
- **Local Certificate File Support**: Load PKCS#12 `.pfx` / `.p12` files for signing on Linux and Windows
- **Certificate Information Display**: Shows certificate details including:
  - Subject (certificate owner)
  - Issuer
  - Validity dates
  - Thumbprint (SHA-1 hash)
  - Common Name (CN)

### Digital Signing
- **Visual & Digital Signature**: Creates both a visual signature box and a digital signature
- **Certificate-Based**: Uses your X.509 certificate for cryptographic signing
- **Metadata Embedding**: Embeds certificate information in the signed PDF

## Installation

### 1. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 1.1 Install on Windows
If you are on Windows, you can run the included installer script to create a virtual environment, install dependencies, and add a desktop shortcut:
```powershell
PowerShell -ExecutionPolicy Bypass -File .\install.ps1
```

### 1.2 Install on Ubuntu/Linux
Run the shell installer script, or create a virtual environment manually:
```bash
bash install.sh
```

If you prefer manual setup:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 1.3 Desktop Launcher (Ubuntu)
To create a desktop launcher for easy access:
```bash
# Copy the desktop file
cp DigiSign.desktop ~/.local/share/applications/

# Edit the Exec line in the copied file to point to your DigiSign directory
# For example, if DigiSign is in ~/projects/DigiSign:
sed -i 's|DIGISIGN_PATH|~/projects/DigiSign|' ~/.local/share/applications/DigiSign.desktop

# Make sure the launcher script is executable
chmod +x ~/projects/DigiSign/digisign-launcher.sh
```
The launcher will appear in your applications menu.

### 2. Optional: Install PyHanko (Recommended)
For full PDF/A compliant digital signatures:
```bash
pip install pyhanko pyhanko-certvalidator
```

### 3. Set Up Certificates
DigiSign supports:
- Windows certificate store certificates on Windows
- Local certificate files on all systems (PKCS#12 `.pfx` / `.p12` files are recommended for signing)

If you are on Windows, certificates can still be loaded from the Windows Personal certificate store:
- Path: `Certlm.msc` (Local Machine) or `Certmgr.msc` (Current User)
- Store: Personal/My

If you are on Linux or want to use a local certificate file:
- Load a `.pfx` or `.p12` file using the "Load certificate file" button
- Enter the file password when prompted

## How Windows Certificate Store Works

### Accessing Certificates
DigiSign uses two methods to access certificates:

1. **Windows CertUtil Command** - Lists certificates from the Personal store
   - Requires no special permissions
   - Works with both user and machine stores

2. **Certificate File Access** - Directly reads certificate files
   - Location: `%APPDATA%\Microsoft\SystemCertificates\My\Certificates`
   - Reads both PEM and DER formatted certificates

### Certificate Export (Advanced)
To export a certificate with its private key for external use:
```powershell
certutil -exportPFX My <Thumbprint> cert.pfx
```

## Usage

### 1. Launch the Application
```bash
python main.py
```

### 2. Select a Certificate
- Click "Refresh Certificates" to load available certificates
- Select your signing certificate from the dropdown
- The certificate details will display below

### 3. Sign a PDF
1. Click "Open PDF" to select a PDF file
2. Navigate to the desired page (if multi-page)
3. Drag on the canvas to define the signature box area
4. Optionally load a signature image
5. Review the "Selection" coordinates
6. Click "Sign PDF"

### Output
The signed PDF will be saved as: `original_name_signed.pdf`

## Technical Details

### Digital Signature Methods

#### Method 1: PyHanko (Full X.509 Support)
If `pyhanko` is installed:
- Creates PAdES-compliant signatures
- Embeds complete certificate chain
- Supports LTV (Long Term Validity) signatures
- Signature field added to PDF

#### Method 2: Metadata Fallback
If `pyhanko` is not installed:
- Embeds signature metadata in PDF properties
- Stores certificate thumbprint
- Documents signer information
- Sufficient for non-repudiation proof

### Certificate Chain
DigiSign verifies:
- Certificate validity dates
- X.509 subject and issuer fields
- Certificate thumbprint (SHA-1)

## Architecture

### New Components

#### `CertificateManager.py`
Manages certificate operations:
- `list_certificates()` - Enumerates available certificates
- `export_certificate_and_key()` - Exports cert + key from store
- `_load_certificate_from_file()` - Reads certificate files
- `_parse_cert_block()` - Parses certutil output

#### Updated `PdfSigner.py`
Enhanced with:
- Certificate selection UI (`certificate_combo`)
- `load_certificates()` - Loads from Windows store
- `on_certificate_selected()` - Handles selection
- `_add_digital_signature()` - Performs signing
- `_add_signature_metadata()` - Fallback method

## Troubleshooting

### No Certificates Found
1. Verify certificates exist: Open `Certmgr.msc`
2. Check Personal/My store for valid certificates
3. Click "Refresh Certificates" button

### Certificate Not Loading
- Ensure certificate has a private key
- Check certificate validity dates
- Try exporting and re-importing via Windows

### PyHanko Import Error
Run: `pip install pyhanko pyhanko-certvalidator`

### Signature Not Visible in PDF
- The digital signature is always embedded in metadata
- Visual signature box appears in the specified location
- Some PDF readers may not display all signature fields

## Security Notes

- Certificates are read from Windows certificate store (no local storage)
- Private keys remain in Windows secure storage
- DigiSign does not extract or save private keys
- PDF includes certificate thumbprint for verification

## Limitations

- Only Personal certificate store is scanned
- Machine-wide certificates may not be accessible
- Some certificate types may not be compatible
- Requires administrative access for some certificate operations

## Command Line Utilities

List certificates from Windows:
```powershell
certutil -store My
```

Check certificate details:
```powershell
certutil -dump -v <Certificate_Thumbprint>
```

## Future Enhancements

- Timestamp server support (RFC 3161)
- Certificate revocation checking (OCSP/CRL)
- Signature verification
- Multi-signature support
- Custom signature appearance
