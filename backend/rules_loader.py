"""rules.txt dosyasini her cagriyla taze okur (cache yok)."""

import os

from config import RULES_FILE_PATH


class RulesFileNotFoundError(Exception):
    pass


def load_rules() -> str:
    if not os.path.exists(RULES_FILE_PATH):
        raise RulesFileNotFoundError(
            f"Kural dosyasi bulunamadi: {RULES_FILE_PATH}. "
            "Lutfen proje kok dizininde bir 'rules.txt' dosyasi olusturun."
        )
    with open(RULES_FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        raise RulesFileNotFoundError(
            f"Kural dosyasi bos: {RULES_FILE_PATH}. Lutfen en az bir kural ekleyin."
        )
    return content
