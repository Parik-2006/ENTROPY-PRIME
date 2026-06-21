from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import os

# Generate private key
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)

# Extract public key
public_key = private_key.public_key()

# Serialize keys to PEM
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

public_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

# Ensure certs directory exists
os.makedirs('certs', exist_ok=True)

# Write to files
with open('certs/jwt_private.pem', 'wb') as f:
    f.write(private_pem)

with open('certs/jwt_public.pem', 'wb') as f:
    f.write(public_pem)

print("Generated certs/jwt_private.pem and certs/jwt_public.pem")
