from dataclasses import dataclass

@dataclass
class SignaturePlacement:
    page_number: int
    x: float
    y: float
    width: float
    height: float