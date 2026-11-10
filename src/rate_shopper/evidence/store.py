from hashlib import sha256
from pathlib import Path


class EvidenceStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, content: bytes) -> tuple[str, Path]:
        digest = sha256(content).hexdigest()
        path = self.root / f"{digest}.json"
        self.root.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError("Evidence integrity failure")
        else:
            with path.open("xb") as stream:
                stream.write(content)
        return digest, path
