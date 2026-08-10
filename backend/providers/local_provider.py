"""
Yerel Model saglayicisi (orn. Ollama, http://localhost:11434) icin iskelet.

Su an aktif degildir. Ileride Ollama (veya benzeri OpenAI-uyumsuz/uyumlu bir
yerel API) entegrasyonu bu sinif icinde tamamlanacak. Arayuz ModelProvider
soyut sinifiyla ayni oldugu icin, tamamlandiginda main.py'deki provider
secimine tek satirla eklenebilir.
"""

import os
from typing import Any

from providers.base import ModelProvider, ModelProviderError


class LocalProvider(ModelProvider):
    def __init__(self) -> None:
        self._endpoint = os.getenv("LOCAL_MODEL_ENDPOINT", "")
        if not self._endpoint:
            raise ModelProviderError(
                "LOCAL_MODEL_ENDPOINT tanimli degil. Yerel model henuz "
                "yapilandirilmamis (bkz. backend/providers/local_provider.py)."
            )

    async def check_row(self, row_data: dict[str, Any], rules_text: str) -> dict[str, Any]:
        raise ModelProviderError(
            "Yerel Model saglayicisi henuz implemente edilmedi. "
            "Bu, ileride Ollama gibi bir yerel model ile entegre edilecek "
            "sekilde tasarlanmis bir iskelettir."
        )

    async def check_term_match(
        self, column_name: str, reference_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        raise ModelProviderError(
            "Yerel Model saglayicisi henuz implemente edilmedi."
        )
