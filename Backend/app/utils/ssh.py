from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


def generate_ssh_keypair(key_size=2048):
    """Generate SSH key pair"""
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )
    
    # Private key in PEM format
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # Public key in OpenSSH format
    public_key = private_key.public_key()
    openssh_public = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH
    )
    
    return {
        "private_key": pem_private.decode('utf-8'),
        "public_key": openssh_public.decode('utf-8')
    }


def validate_public_key(public_key: str) -> bool:
    """Validate SSH public key format"""
    try:
        parts = public_key.strip().split()
        return len(parts) >= 2 and parts[0] in ['ssh-rsa', 'ssh-ed25519']
    except:
        return False