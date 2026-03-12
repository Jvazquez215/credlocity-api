"""
Data Encryption for Attorney Marketplace

Sensitive fields to encrypt:
- bank_account_info (in credit_repair_companies)
- tax_id
- bar_number (in attorney_profiles)
- ssn (if collected)
- client_ssn (in case documents)
- client_dob

Encryption approach:
- AES-256-GCM encryption
- Separate encryption keys per company (optional)
- Key rotation policy: annually
"""

import os
import base64
import hashlib
from typing import Optional, Dict, Any
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import secrets


class EncryptionService:
    """
    AES-256-GCM encryption service for sensitive data
    """
    
    # Master encryption key from environment (should be 32 bytes base64 encoded)
    MASTER_KEY_ENV = "ENCRYPTION_MASTER_KEY"
    
    # Default key for development (NEVER use in production)
    DEFAULT_DEV_KEY = "Y3JlZGxvY2l0eS1kZXYta2V5LTIwMjUtc2VjdXJl"  # base64
    
    @classmethod
    def _get_master_key(cls) -> bytes:
        """Get the master encryption key"""
        key_b64 = os.environ.get(cls.MASTER_KEY_ENV, cls.DEFAULT_DEV_KEY)
        try:
            key = base64.b64decode(key_b64)
            # Ensure 32 bytes for AES-256
            if len(key) < 32:
                # Derive a 32-byte key using PBKDF2
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=b"credlocity-salt-v1",
                    iterations=100000,
                    backend=default_backend()
                )
                key = kdf.derive(key)
            return key[:32]
        except Exception:
            # Fallback: derive from string
            return hashlib.sha256(key_b64.encode()).digest()
    
    @classmethod
    def _derive_company_key(cls, company_id: str) -> bytes:
        """
        Derive a company-specific key from master key
        This allows per-company key isolation
        """
        master_key = cls._get_master_key()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=company_id.encode()[:16].ljust(16, b'\0'),
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(master_key)
    
    @classmethod
    def encrypt(
        cls,
        plaintext: str,
        company_id: Optional[str] = None
    ) -> str:
        """
        Encrypt a string value
        
        Args:
            plaintext: String to encrypt
            company_id: Optional company ID for company-specific key
        
        Returns:
            Base64-encoded encrypted string with nonce prefix
        """
        if not plaintext:
            return ""
        
        # Get appropriate key
        if company_id:
            key = cls._derive_company_key(company_id)
        else:
            key = cls._get_master_key()
        
        # Generate random nonce (12 bytes for GCM)
        nonce = secrets.token_bytes(12)
        
        # Encrypt
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        
        # Combine nonce + ciphertext and base64 encode
        encrypted = base64.b64encode(nonce + ciphertext).decode('utf-8')
        
        # Prefix with version for future key rotation
        return f"v1:{encrypted}"
    
    @classmethod
    def decrypt(
        cls,
        encrypted_value: str,
        company_id: Optional[str] = None
    ) -> str:
        """
        Decrypt an encrypted string
        
        Args:
            encrypted_value: Base64-encoded encrypted string
            company_id: Optional company ID for company-specific key
        
        Returns:
            Decrypted string
        """
        if not encrypted_value:
            return ""
        
        # Parse version
        if encrypted_value.startswith("v1:"):
            encrypted_value = encrypted_value[3:]
        
        # Get appropriate key
        if company_id:
            key = cls._derive_company_key(company_id)
        else:
            key = cls._get_master_key()
        
        # Decode
        encrypted_bytes = base64.b64decode(encrypted_value)
        
        # Extract nonce (first 12 bytes) and ciphertext
        nonce = encrypted_bytes[:12]
        ciphertext = encrypted_bytes[12:]
        
        # Decrypt
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        
        return plaintext.decode('utf-8')
    
    @classmethod
    def encrypt_dict_fields(
        cls,
        data: Dict[str, Any],
        fields_to_encrypt: list,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Encrypt specific fields in a dictionary
        
        Args:
            data: Dictionary with data
            fields_to_encrypt: List of field names to encrypt
            company_id: Optional company ID
        
        Returns:
            Dictionary with encrypted fields
        """
        result = data.copy()
        for field in fields_to_encrypt:
            if field in result and result[field]:
                result[field] = cls.encrypt(str(result[field]), company_id)
                result[f"_{field}_encrypted"] = True
        return result
    
    @classmethod
    def decrypt_dict_fields(
        cls,
        data: Dict[str, Any],
        fields_to_decrypt: list,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Decrypt specific fields in a dictionary
        
        Args:
            data: Dictionary with encrypted data
            fields_to_decrypt: List of field names to decrypt
            company_id: Optional company ID
        
        Returns:
            Dictionary with decrypted fields
        """
        result = data.copy()
        for field in fields_to_decrypt:
            if field in result and result.get(f"_{field}_encrypted"):
                try:
                    result[field] = cls.decrypt(result[field], company_id)
                except Exception:
                    # If decryption fails, leave as-is
                    pass
        return result
    
    @classmethod
    def hash_for_search(cls, value: str) -> str:
        """
        Create a searchable hash of a value
        Used when you need to search encrypted fields
        
        Note: This is deterministic, so same value = same hash
        """
        if not value:
            return ""
        
        salt = os.environ.get("HASH_SALT", "credlocity-hash-salt-v1")
        combined = f"{salt}:{value}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    @classmethod
    def mask_sensitive(cls, value: str, visible_chars: int = 4) -> str:
        """
        Mask a sensitive value for display
        
        Examples:
            SSN: "***-**-1234"
            Bank: "****4567"
        """
        if not value:
            return ""
        
        if len(value) <= visible_chars:
            return "*" * len(value)
        
        return "*" * (len(value) - visible_chars) + value[-visible_chars:]
    
    @classmethod
    def generate_key(cls) -> str:
        """
        Generate a new encryption key
        Use this to create keys for key rotation
        """
        key = secrets.token_bytes(32)
        return base64.b64encode(key).decode('utf-8')


# Sensitive field definitions by collection
SENSITIVE_FIELDS = {
    "credit_repair_companies": [
        "bank_account_info",
        "bank_routing_number",
        "bank_account_number",
        "tax_id"
    ],
    "attorney_profiles": [
        "bar_number",
        "ssn",
        "bank_account_info"
    ],
    "cases": [
        "client_ssn",
        "client_dob"
    ],
    "case_documents": [
        "content_encrypted"  # If storing encrypted document content
    ]
}


def encrypt_sensitive_fields(collection: str, data: Dict, company_id: Optional[str] = None) -> Dict:
    """
    Encrypt sensitive fields for a specific collection
    """
    fields = SENSITIVE_FIELDS.get(collection, [])
    return EncryptionService.encrypt_dict_fields(data, fields, company_id)


def decrypt_sensitive_fields(collection: str, data: Dict, company_id: Optional[str] = None) -> Dict:
    """
    Decrypt sensitive fields for a specific collection
    """
    fields = SENSITIVE_FIELDS.get(collection, [])
    return EncryptionService.decrypt_dict_fields(data, fields, company_id)
