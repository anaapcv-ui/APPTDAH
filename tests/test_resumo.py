from datetime import date

from gastos_bot.resumo import brl, parse_mes, resumo_mes, resumo_semana
from gastos_bot.sheets import Lancamento, _to_float, _to_iso


def lanc(data, valor, cat="Mercado", local="Pão de Açúcar"):
    return Lancamento("x", data, local, valor, cat, "", "Pix", "", "", "1")


HOJE = date(2026, 11, 3)


def test_brl():
    assert brl(1234.5) == "R$ 1.234,50"
    assert brl(0.9) == "R$ 0,90"


def test_parse_mes():
    assert parse_mes(None, HOJE) == (2026, 11)
    assert parse_mes("10", HOJE) == (2026, 10)
    assert parse_mes("10/25", HOJE) == (2025, 10)
    assert parse_mes("2025-03", HOJE) == (2025, 3)
    assert parse_mes("março", HOJE) == (2026, 3)


def test_resumo_mes_agrupa_e_filtra():
    lancs = [
        lanc("2026-11-01", 100),
        lanc("2026-11-02", 50, "Transporte", "Uber"),
        lanc("2026-10-30", 999),  # outro mês
    ]
    txt = resumo_mes(lancs, 2026, 11)
    assert "R$ 150,00" in txt
    assert "Mercado</b>: R$ 100,00 (67%)" in txt
    assert "999" not in txt


def test_resumo_vazio_e_escape():
    assert "Nenhum gasto" in resumo_mes([], 2026, 11)
    txt = resumo_semana([lanc("2026-11-03", 10, local="A<b>")], HOJE)
    assert "A&lt;b&gt;" in txt


def test_conversoes_planilha():
    assert _to_float("R$ 1.234,56") == 1234.56
    assert _to_float(12) == 12.0
    assert _to_iso(46329, "%Y-%m-%d") == "2026-11-03"
    assert _to_iso("2026-11-03", "%Y-%m-%d") == "2026-11-03"
