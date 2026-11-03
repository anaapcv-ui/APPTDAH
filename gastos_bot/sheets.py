"""Gravação e leitura dos lançamentos no Google Sheets."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import gspread

ABA_LANCAMENTOS = "Lançamentos"
CABECALHO = [
    "ID",
    "Data",
    "Estabelecimento",
    "Valor",
    "Categoria",
    "Subcategoria",
    "Forma de pagamento",
    "Descrição",
    "Registrado em",
    "Usuário",
    "Hash do arquivo",
]
COL = {nome: i + 1 for i, nome in enumerate(CABECALHO)}  # índice 1-based


@dataclass
class Lancamento:
    id: str
    data: str  # AAAA-MM-DD
    estabelecimento: str
    valor: float
    categoria: str
    subcategoria: str
    forma_pagamento: str
    descricao: str
    registrado_em: str
    usuario: str
    hash_arquivo: str = ""

    def to_row(self) -> list:
        return [
            self.id,
            self.data,
            self.estabelecimento,
            self.valor,
            self.categoria,
            self.subcategoria,
            self.forma_pagamento,
            self.descricao,
            self.registrado_em,
            self.usuario,
            self.hash_arquivo,
        ]

    @classmethod
    def from_record(cls, r: dict) -> "Lancamento":
        return cls(
            id=str(r.get("ID", "")),
            data=_to_iso(r.get("Data", ""), "%Y-%m-%d"),
            estabelecimento=str(r.get("Estabelecimento", "")),
            valor=_to_float(r.get("Valor", 0)),
            categoria=str(r.get("Categoria", "")),
            subcategoria=str(r.get("Subcategoria", "")),
            forma_pagamento=str(r.get("Forma de pagamento", "")),
            descricao=str(r.get("Descrição", "")),
            registrado_em=_to_iso(r.get("Registrado em", ""), "%Y-%m-%d %H:%M"),
            usuario=str(r.get("Usuário", "")),
            hash_arquivo=str(r.get("Hash do arquivo", "")),
        )


_EPOCA_SHEETS = datetime(1899, 12, 30)


def _to_iso(v, fmt: str) -> str:
    """Datas lidas sem formatação chegam como número serial do Sheets; converte para texto ISO."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (_EPOCA_SHEETS + timedelta(days=float(v))).strftime(fmt)
    return str(v)


def _to_float(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("R$", "").strip()
    if "," in s:  # formato brasileiro 1.234,56
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def novo_id() -> str:
    return secrets.token_hex(4)


class Planilha:
    def __init__(self, spreadsheet_id: str, credentials_file: str = "", credentials_json: str = ""):
        if credentials_json:
            gc = gspread.service_account_from_dict(json.loads(credentials_json))
        else:
            gc = gspread.service_account(filename=credentials_file)
        self.doc = gc.open_by_key(spreadsheet_id)
        self.ws = self._garantir_aba()

    def _garantir_aba(self) -> gspread.Worksheet:
        try:
            ws = self.doc.worksheet(ABA_LANCAMENTOS)
        except gspread.WorksheetNotFound:
            ws = self.doc.add_worksheet(ABA_LANCAMENTOS, rows=1000, cols=len(CABECALHO))
        if ws.row_values(1) != CABECALHO:
            ws.update([CABECALHO], "A1")
            ws.format("A1:K1", {"textFormat": {"bold": True}})
            ws.freeze(rows=1)
            # Coluna Valor em formato de moeda
            ws.format("D:D", {"numberFormat": {"type": "CURRENCY", "pattern": '"R$" #,##0.00'}})
        return ws

    # --- escrita -------------------------------------------------------------

    def adicionar(self, lanc: Lancamento) -> None:
        self.ws.append_row(lanc.to_row(), value_input_option="USER_ENTERED", table_range="A1")

    def _linha_do_id(self, lanc_id: str) -> int | None:
        ids = self.ws.col_values(COL["ID"])
        for i in range(len(ids) - 1, 0, -1):  # de baixo para cima, pulando o cabeçalho
            if ids[i] == lanc_id:
                return i + 1
        return None

    def atualizar_categoria(self, lanc_id: str, categoria: str) -> bool:
        linha = self._linha_do_id(lanc_id)
        if linha is None:
            return False
        self.ws.update_cell(linha, COL["Categoria"], categoria)
        return True

    def remover(self, lanc_id: str) -> bool:
        linha = self._linha_do_id(lanc_id)
        if linha is None:
            return False
        self.ws.delete_rows(linha)
        return True

    # --- leitura -------------------------------------------------------------

    def todos(self) -> list[Lancamento]:
        registros = self.ws.get_all_records(
            expected_headers=CABECALHO, value_render_option="UNFORMATTED_VALUE"
        )
        return [Lancamento.from_record(r) for r in registros if r.get("ID")]

    def ultimo_do_usuario(self, usuario: str) -> Lancamento | None:
        for lanc in reversed(self.todos()):
            if lanc.usuario == usuario:
                return lanc
        return None

    def existe_hash(self, hash_arquivo: str) -> Lancamento | None:
        if not hash_arquivo:
            return None
        for lanc in self.todos():
            if lanc.hash_arquivo == hash_arquivo:
                return lanc
        return None


def agora_str(tz) -> str:
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M")
