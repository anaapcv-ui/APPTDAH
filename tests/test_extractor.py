import asyncio
import json
from datetime import date

import anthropic
import httpx2 as httpx

from gastos_bot.bot import montar_lancamento
from gastos_bot.extractor import Extractor, Gasto

RESPOSTA = {
    "eh_gasto": True,
    "motivo_rejeicao": None,
    "data": "2026-11-02",
    "estabelecimento": "Uber",
    "valor": 23.5,
    "categoria": "Transporte",
    "subcategoria": "Aplicativo",
    "forma_pagamento": "Cartão de crédito",
    "descricao": "Corrida de Uber",
}


def fake_client(captured):
    def handler(request: httpx.Request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5-5",
                "content": [{"type": "text", "text": json.dumps(RESPOSTA)}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 10},
            },
        )

    return anthropic.AsyncAnthropic(
        api_key="test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


def test_extrai_pdf_e_monta_requisicao():
    captured = []
    ex = Extractor("claude-opus-5-5", fake_client(captured))
    gasto = asyncio.run(ex.from_file(b"%PDF-1.4", "application/pdf", "uber", date(2026, 11, 3)))

    assert gasto.valor == 23.5 and gasto.categoria == "Transporte"
    body = captured[0]
    assert body["model"] == "claude-opus-5-5"
    assert body["messages"][0]["content"][0]["type"] == "document"
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert "Transporte" in json.dumps(fmt["schema"])
    assert body["output_config"]["effort"] == "low"
    assert body["fallbacks"] == "default"


def test_montar_lancamento_data_invalida_usa_hoje():
    g = Gasto(**{**RESPOSTA, "data": "02/11", "valor": -23.456})
    l = montar_lancamento(g, date(2026, 11, 3), "1", None, "")
    assert l.data == "2026-11-03"
    assert l.valor == 23.46
