"""Cálculo e formatação dos resumos de gastos."""

from __future__ import annotations

from collections import defaultdict
from html import escape
from datetime import date, timedelta

from .sheets import Lancamento

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def brl(valor: float) -> str:
    s = f"{valor:,.2f}"  # 1,234.56
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def parse_mes(arg: str | None, hoje: date) -> tuple[int, int]:
    """Aceita '11', '11/2026', '2026-11' ou nada (mês atual). Retorna (ano, mês)."""
    if not arg:
        return hoje.year, hoje.month
    arg = arg.strip().lower()
    if arg in MESES:
        return hoje.year, MESES.index(arg) + 1
    if "-" in arg:
        a, m = arg.split("-", 1)
        return int(a), int(m)
    if "/" in arg:
        m, a = arg.split("/", 1)
        a_int = int(a)
        return (a_int + 2000 if a_int < 100 else a_int), int(m)
    return hoje.year, int(arg)


def do_mes(lancs: list[Lancamento], ano: int, mes: int) -> list[Lancamento]:
    prefixo = f"{ano:04d}-{mes:02d}"
    return [l for l in lancs if l.data.startswith(prefixo)]


def do_periodo(lancs: list[Lancamento], inicio: date, fim: date) -> list[Lancamento]:
    ini, fi = inicio.isoformat(), fim.isoformat()
    return [l for l in lancs if ini <= l.data[:10] <= fi]


def _bloco(lancs: list[Lancamento], titulo: str) -> str:
    if not lancs:
        return f"{titulo}\n\nNenhum gasto registrado."

    total = sum(l.valor for l in lancs)
    por_cat: dict[str, float] = defaultdict(float)
    por_local: dict[str, float] = defaultdict(float)
    for l in lancs:
        por_cat[l.categoria or "Outros"] += l.valor
        por_local[l.estabelecimento or "?"] += l.valor

    linhas = [titulo, "", f"<b>Total:</b> {brl(total)} em {len(lancs)} lançamento(s)", ""]
    for cat, v in sorted(por_cat.items(), key=lambda kv: -kv[1]):
        pct = v / total * 100 if total else 0
        barra = "█" * max(1, round(pct / 10)) if v else ""
        linhas.append(f"{barra} <b>{escape(cat)}</b>: {brl(v)} ({pct:.0f}%)")

    linhas += ["", "<b>Onde mais gastou:</b>"]
    for local, v in sorted(por_local.items(), key=lambda kv: -kv[1])[:5]:
        linhas.append(f"• {escape(local)}: {brl(v)}")
    return "\n".join(linhas)


def resumo_mes(lancs: list[Lancamento], ano: int, mes: int) -> str:
    return _bloco(do_mes(lancs, ano, mes), f"📊 <b>Gastos de {MESES[mes - 1]}/{ano}</b>")


def resumo_semana(lancs: list[Lancamento], hoje: date) -> str:
    inicio = hoje - timedelta(days=6)
    titulo = f"📅 <b>Últimos 7 dias</b> ({inicio:%d/%m} a {hoje:%d/%m})"
    return _bloco(do_periodo(lancs, inicio, hoje), titulo)
