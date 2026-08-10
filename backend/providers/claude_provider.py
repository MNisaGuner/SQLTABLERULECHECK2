"""
Anthropic Claude API tabanli ModelProvider implementasyonu.

Guvenilir JSON cikti icin structured outputs (output_config.format) kullanilir;
boylece serbest metin ayristirma (parsing) riskine girilmez.
"""

import json
import os
from typing import Any

from anthropic import AsyncAnthropic, APIStatusError, APIConnectionError

from providers.base import ModelProvider, ModelProviderError

_ROW_CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "karar": {"type": "string", "enum": ["ONAY", "IADE"]},
        "gerekce": {"type": "string"},
    },
    "required": ["karar", "gerekce"],
    "additionalProperties": False,
}

_TERM_MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "durum": {"type": "string", "enum": ["eslesti", "eslesmedi"]},
        "terim": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "oneriler": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["durum", "terim", "oneriler"],
    "additionalProperties": False,
}

_ROW_CHECK_SYSTEM_PROMPT = """Sen bir veri kalitesi / uyumluluk denetim asistanisin.
Sana bir MSSQL sorgu satirinin verileri ve bir kural listesi verilecek.
Gorevin: satirin kurallara UYUP UYMADIGINI degerlendirmek.

Kurallar:
{rules}

Talimatlar:
- Satir herhangi bir kurala aykirıysa karar = "IADE" olmali; gerekce alaninda
  hangi kurala aykiri oldugunu acikca belirt.
- Satir tum kurallara uyuyorsa karar = "ONAY" olmali; gerekce alaninda kisaca
  neden uygun gorduğunu belirt.
- gerekce Turkce ve kisa (1-3 cumle) olmali.
- Sadece verilen kurallara ve satir verisine dayan, varsayimda bulunma."""

_TERM_MATCH_SYSTEM_PROMPT = """Sen bir veri katalogu / is terimi eslestirme asistanisin.
Sana bir kolon adi ve kurumun daha once eslestirilmis kolon-terim referans
listesi verilecek. Gorevin bu kolon adinin referans listedeki hangi is terimine
karsilik geldigini degerlendirmek.

Talimatlar:
- Net bir eslesme varsa durum = "eslesti", terim = eslesen TerimAdi degeri,
  oneriler = bos liste.
- Net bir eslesme yoksa durum = "eslesmedi", terim = null, oneriler = en yakin
  2-3 terim adayi, en olasidan en az olasiya siralanmis sekilde (yalnizca
  referans listede gecen TerimAdi degerlerinden secilmeli).
- Sadece verilen referans listesine dayan, referans listede olmayan bir terim
  uydurma."""


class ClaudeProvider(ModelProvider):
    def __init__(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ModelProviderError(
                "ANTHROPIC_API_KEY tanimli degil. Lutfen .env dosyasini kontrol edin."
            )
        self._model = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")
        self._effort = os.getenv("ANTHROPIC_EFFORT", "low")
        self._client = AsyncAnthropic(api_key=api_key)

    async def _create_structured(
        self, system_text: str, user_content: str, schema: dict
    ) -> dict[str, Any]:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": system_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                output_config={
                    "effort": self._effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                messages=[{"role": "user", "content": user_content}],
            )
        except APIConnectionError as exc:
            raise ModelProviderError(f"Claude API baglanti hatasi: {exc}") from exc
        except APIStatusError as exc:
            raise ModelProviderError(f"Claude API hatasi ({exc.status_code}): {exc.message}") from exc

        if response.stop_reason == "refusal":
            raise ModelProviderError("Claude istegi reddetti (guvenlik politikasi).")

        text_block = next((b for b in response.content if b.type == "text"), None)
        if text_block is None:
            raise ModelProviderError("Claude yanitinda metin bloğu bulunamadi.")

        try:
            return json.loads(text_block.text)
        except json.JSONDecodeError as exc:
            raise ModelProviderError(f"Claude yaniti JSON olarak ayristirilamadi: {exc}") from exc

    async def check_row(self, row_data: dict[str, Any], rules_text: str) -> dict[str, Any]:
        system_text = _ROW_CHECK_SYSTEM_PROMPT.format(rules=rules_text)
        user_content = "Denetlenecek satir verisi (JSON):\n" + json.dumps(
            row_data, ensure_ascii=False, default=str
        )
        result = await self._create_structured(system_text, user_content, _ROW_CHECK_SCHEMA)
        if result.get("karar") not in ("ONAY", "IADE"):
            raise ModelProviderError(f"Gecersiz karar degeri: {result.get('karar')!r}")
        return result

    async def check_term_match(
        self, column_name: str, reference_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        user_content = (
            f'Degerlendirilecek kolon adi: "{column_name}"\n\n'
            "Referans kolon-terim listesi (JSON):\n"
            + json.dumps(reference_data, ensure_ascii=False, default=str)
        )
        result = await self._create_structured(
            _TERM_MATCH_SYSTEM_PROMPT, user_content, _TERM_MATCH_SCHEMA
        )
        if result.get("durum") not in ("eslesti", "eslesmedi"):
            raise ModelProviderError(f"Gecersiz durum degeri: {result.get('durum')!r}")
        return result
