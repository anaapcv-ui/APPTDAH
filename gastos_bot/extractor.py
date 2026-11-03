"""Leitura de comprovantes (imagem, PDF ou texto) com o Claude."""

from __future__ import annotations

import base64
import logging
from datetime import date
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from .config import CATEGORIAS, FORMAS_PAGAMENTO

log = logging.getLogger(__name__)

Categoria = Literal[tuple(CATEGORIAS)]  # type: ignore[valid-type]
FormaPagamento = Literal[tuple(FORMAS_PAGAMENTO)]  # type: ignore[valid-type]

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
PDF_TYPE = "application/pdf"


class Gasto(BaseModel):
    eh_gasto: bool = Field(
        description="true se o conteúdo é um comprovante/registro de gasto; false caso contrário"
    )
    motivo_rejeicao: Optional[str] = Field(
        description="Se eh_gasto=false, explique em uma frase curta por quê; senão null"
    )
    data: Optional[str] = Field(
        description="Data da compra/pagamento no formato AAAA-MM-DD, ou null se não aparecer"
    )
    estabelecimento: str = Field(
        description="Nome do estabelecimento ou do recebedor, curto e legível (ex.: 'Pão de Açúcar', 'Uber', 'João Silva')"
    )
    valor: float = Field(description="Valor total pago em reais, positivo, com centavos (ex.: 52.9)")
    categoria: Categoria = Field(description="Categoria que melhor descreve o gasto")  # type: ignore[valid-type]
    subcategoria: str = Field(
        description="Detalhe curto da categoria (ex.: 'Supermercado', 'Combustível', 'Farmácia', 'Streaming')"
    )
    forma_pagamento: FormaPagamento = Field(  # type: ignore[valid-type]
        description="Meio de pagamento; use 'Outro' se não for possível identificar"
    )
    descricao: str = Field(description="Resumo de uma linha do que foi comprado/pago")


SYSTEM_PROMPT = f"""Você organiza os gastos pessoais de uma pessoa no Brasil. Ela envia comprovantes \
(fotos de cupom fiscal, notas, prints de Pix, PDFs de comprovante bancário, faturas, boletos pagos) \
ou descreve um gasto em texto livre (ex.: "uber 23,50", "almoço 45 no débito").

Extraia um único lançamento de gasto:
- valor: o total efetivamente pago (não subtotais, nem troco, nem valor de parcelas futuras). \
Valores brasileiros usam vírgula decimal: "1.234,56" = 1234.56.
- data: a data do pagamento. Se não houver data e for texto livre, use null.
- estabelecimento: o nome comercial, não a razão social completa quando houver um nome mais conhecido. \
Para Pix/transferência, use o nome de quem recebeu.
- categoria: escolha uma de: {", ".join(CATEGORIAS)}. \
"Mercado" é supermercado/feira/padaria; "Restaurantes e Delivery" é refeição pronta; \
"Contas da casa" é luz, água, gás, internet, telefone, condomínio; "Moradia" é aluguel, financiamento, reformas; \
"Assinaturas" são serviços recorrentes (streaming, apps, academia).
- Se o conteúdo não for um gasto (selfie, meme, extrato inteiro com muitos lançamentos, conversa), \
marque eh_gasto=false, explique em motivo_rejeicao e preencha os demais campos com valores neutros \
(valor 0, categoria "Outros", forma_pagamento "Outro", textos vazios)."""


class ExtractionError(Exception):
    """Falha ao ler o comprovante (mensagem pronta para mostrar ao usuário)."""


class Extractor:
    def __init__(self, model: str, client: anthropic.AsyncAnthropic | None = None):
        self.model = model
        self.client = client or anthropic.AsyncAnthropic()

    async def from_file(self, data: bytes, mime_type: str, caption: str | None, hoje: date) -> Gasto:
        b64 = base64.standard_b64encode(data).decode("ascii")
        if mime_type in IMAGE_TYPES:
            block = {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}}
        elif mime_type == PDF_TYPE:
            block = {"type": "document", "source": {"type": "base64", "media_type": PDF_TYPE, "data": b64}}
        else:
            raise ExtractionError("Formato não suportado. Envie foto (JPG/PNG) ou PDF.")

        texto = f"Hoje é {hoje.isoformat()}. Extraia o gasto deste comprovante."
        if caption:
            texto += f'\nObservação de quem enviou: "{caption}"'
        return await self._extract([block, {"type": "text", "text": texto}])

    async def from_text(self, text: str, hoje: date) -> Gasto:
        prompt = (
            f"Hoje é {hoje.isoformat()}. Registre este gasto descrito em texto "
            f"(se não houver data, use a de hoje):\n\n{text}"
        )
        return await self._extract([{"type": "text", "text": prompt}])

    async def _extract(self, content: list[dict]) -> Gasto:
        try:
            response = await self.client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_format=Gasto,
                output_config={"effort": "low"},
                # Se o modelo recusar por política, a API tenta outro modelo automaticamente.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError as e:
            raise ExtractionError("Muitas requisições agora. Tente de novo em um minuto.") from e
        except anthropic.APIConnectionError as e:
            raise ExtractionError("Não consegui falar com o serviço de leitura. Tente de novo.") from e
        except anthropic.APIStatusError as e:
            log.exception("Erro da API Anthropic")
            raise ExtractionError(f"Erro ao ler o comprovante ({e.status_code}).") from e

        if response.stop_reason == "refusal":
            raise ExtractionError("Não foi possível processar este conteúdo.")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise ExtractionError("Não consegui interpretar o comprovante. Tente uma foto mais nítida.")
        return response.parsed_output
