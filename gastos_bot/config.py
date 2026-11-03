"""Configuração lida de variáveis de ambiente (arquivo .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

CATEGORIAS: list[str] = [
    "Moradia",
    "Mercado",
    "Restaurantes e Delivery",
    "Transporte",
    "Saúde",
    "Educação",
    "Lazer",
    "Assinaturas",
    "Compras",
    "Contas da casa",
    "Pets",
    "Cuidados pessoais",
    "Presentes e Doações",
    "Impostos e Taxas",
    "Outros",
]

FORMAS_PAGAMENTO: list[str] = [
    "Pix",
    "Cartão de crédito",
    "Cartão de débito",
    "Dinheiro",
    "Boleto",
    "Transferência",
    "Outro",
]


@dataclass(frozen=True)
class Config:
    telegram_token: str
    allowed_user_ids: frozenset[int]
    claude_model: str
    spreadsheet_id: str
    google_credentials_file: str
    google_credentials_json: str
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("America/Sao_Paulo"))


def _parse_ids(raw: str) -> frozenset[int]:
    return frozenset(int(x) for x in raw.replace(" ", "").split(",") if x)


def load_config() -> Config:
    faltando = [
        nome
        for nome in ("TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "SPREADSHEET_ID")
        if not os.getenv(nome)
    ]
    if faltando:
        raise SystemExit(f"Variáveis ausentes no .env: {', '.join(faltando)}")

    return Config(
        telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
        allowed_user_ids=_parse_ids(os.getenv("ALLOWED_USER_IDS", "")),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5"),
        spreadsheet_id=os.environ["SPREADSHEET_ID"],
        google_credentials_file=os.getenv("GOOGLE_CREDENTIALS_FILE", "service_account.json"),
        google_credentials_json=os.getenv("GOOGLE_CREDENTIALS_JSON", ""),
        timezone=ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo")),
    )
