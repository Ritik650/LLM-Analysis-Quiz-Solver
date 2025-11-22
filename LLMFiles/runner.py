
import hashlib

key = "45697056"
blob = "8b1f4c3a2d"

combined_string = key + blob
sha256_hash = hashlib.sha256(combined_string.encode()).hexdigest()

answer = sha256_hash[:12]
print(answer)
