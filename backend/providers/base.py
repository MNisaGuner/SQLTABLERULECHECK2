"""
Soyut ModelProvider arayuzu.

Yeni bir saglayici eklemek icin (orn. yerel model / Ollama) bu siniftan
turetip iki metodu implemente etmek yeterlidir:
  - check_row: satir bazli ONAY/IADE kural denetimi
  - check_term_match: kolon adi -> is terimi eslestirme denetimi

Boylece ONAY/IADE denetimi ile terim eslestirme birbirinden bagimsiz
gelistirilip test edilebilir, ama ayni saglayici (provider) uzerinden calisir.
"""

from abc import ABC, abstractmethod
from typing import Any


class ModelProviderError(Exception):
    """Model saglayicisi cagrisinda olusan hatalari sarmalar."""


class ModelProvider(ABC):
    @abstractmethod
    async def check_row(self, row_data: dict[str, Any], rules_text: str) -> dict[str, Any]:
        """
        Bir satiri rules_text'teki kurallara gore denetler.

        Donus: {"karar": "ONAY" | "IADE", "gerekce": str}
        """
        raise NotImplementedError

    @abstractmethod
    async def check_term_match(
        self, column_name: str, reference_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Bir kolon adinin referans terim sozlugundeki hangi terime karsilik
        geldigini degerlendirir.

        Donus:
          Eslesme varsa: {"durum": "eslesti", "terim": str, "oneriler": []}
          Eslesme yoksa: {"durum": "eslesmedi", "terim": None, "oneriler": [str, ...]}
        """
        raise NotImplementedError
