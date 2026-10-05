"""QR link signing for the customer ordering page.

Why: the table number, zone and brand used to travel in the URL as plain text, so anyone could
edit ?table=5 into ?table=12 (or ?zone=...) and order for a different table / see a different menu.
Every QR we generate now carries an HMAC signature over (table, zone, brand). The server recomputes
the signature on every request, so editing any of those three values invalidates the link.
"""
import hashlib
import hmac
import unicodedata
from urllib.parse import quote

QR_SIGNATURE_LENGTH = 20  # hex chars (80 bits) - plenty, keeps the QR code small
TABLE_LABEL_MAX_LENGTH = 20
_FORBIDDEN_TABLE_CHARS = set("<>\"'&|\\`%")


def _norm(value):
    return unicodedata.normalize("NFC", str(value or "")).strip()


def is_safe_table_label(label):
    """Table label must be short, printable and free of HTML / separator characters."""
    label = _norm(label)
    if not label or len(label) > TABLE_LABEL_MAX_LENGTH:
        return False
    return not any(ch in _FORBIDDEN_TABLE_CHARS or ord(ch) < 32 for ch in label)


def sign_order_params(secret, table, zone="", brand="default"):
    message = "|".join([_norm(table), _norm(zone), _norm(brand) or "default"]).encode("utf-8")
    digest = hmac.new(str(secret).encode("utf-8"), message, hashlib.sha256).hexdigest()
    return digest[:QR_SIGNATURE_LENGTH]


def verify_order_params(secret, table, zone, brand, signature):
    if not secret or not signature:
        return False
    expected = sign_order_params(secret, table, zone, brand)
    return hmac.compare_digest(expected, str(signature).strip().lower())


def build_order_url(secret, base_url, table, zone="", brand="default"):
    table = _norm(table)
    zone = _norm(zone)
    brand = _norm(brand) or "default"
    signature = sign_order_params(secret, table, zone, brand)
    url = f"{base_url.rstrip('/')}/?page=order&table={quote(table, safe='')}"
    if zone:
        url += f"&zone={quote(zone, safe='')}"
    if brand != "default":
        url += f"&brand={quote(brand, safe='')}"
    url += f"&sig={signature}"
    url += "&embed=true"  # hides Streamlit Cloud toolbar (not part of the signature)
    return url
