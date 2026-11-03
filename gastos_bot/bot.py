"""Bot do Telegram que recebe comprovantes e registra os gastos no Google Sheets."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
from datetime import date, datetime
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import CATEGORIAS, Config, load_config
from .extractor import IMAGE_TYPES, PDF_TYPE, ExtractionError, Extractor, Gasto
from .resumo import brl, parse_mes, resumo_mes, resumo_semana
from .sheets import Lancamento, Planilha, agora_str, novo_id

log = logging.getLogger(__name__)

LIMITE_ARQUIVO = 20 * 1024 * 1024  # limite de download de bots do Telegram

AJUDA = """👋 <b>Eu organizo seus gastos.</b>

Envie para mim:
• 📸 <b>foto</b> de cupom, nota ou print de Pix
• 📄 <b>PDF</b> de comprovante (pode encaminhar direto do app do banco)
• ✍️ <b>texto</b>, ex.: <code>uber 23,50</code> ou <code>almoço 45 no débito</code>

Eu leio, categorizo e salvo na planilha. Se eu errar a categoria, é só tocar em ✏️.

<b>Comandos</b>
/resumo — gastos do mês atual por categoria
/resumo 10 — mês 10 (ou <code>/resumo 10/2026</code>)
/semana — últimos 7 dias
/desfazer — apaga o último lançamento
/planilha — link da planilha
/ajuda — esta mensagem"""


# --- utilidades -------------------------------------------------------------------


def cfg(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.application.bot_data["config"]


def planilha(context: ContextTypes.DEFAULT_TYPE) -> Planilha:
    return context.application.bot_data["planilha"]


def extractor(context: ContextTypes.DEFAULT_TYPE) -> Extractor:
    return context.application.bot_data["extractor"]


def hoje(context: ContextTypes.DEFAULT_TYPE) -> date:
    return datetime.now(cfg(context).timezone).date()


def autorizado(handler):
    """Só deixa passar usuários listados em ALLOWED_USER_IDS (se a lista não estiver vazia)."""

    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        permitidos = cfg(context).allowed_user_ids
        if permitidos and (user is None or user.id not in permitidos):
            uid = user.id if user else "?"
            if update.callback_query:
                await update.callback_query.answer("Acesso não autorizado.")
            elif update.effective_message:
                await update.effective_message.reply_text(
                    f"⛔ Acesso não autorizado.\nSeu ID do Telegram é <code>{uid}</code>.",
                    parse_mode=ParseMode.HTML,
                )
            log.warning("Acesso negado para o usuário %s", uid)
            return
        return await handler(update, context)

    return wrapper


def teclado_lancamento(lanc_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✔️ Ok", callback_data=f"ok:{lanc_id}"),
            InlineKeyboardButton("✏️ Categoria", callback_data=f"cat:{lanc_id}"),
            InlineKeyboardButton("🗑 Apagar", callback_data=f"del:{lanc_id}"),
        ]]
    )


def teclado_categorias(lanc_id: str) -> InlineKeyboardMarkup:
    botoes = [
        InlineKeyboardButton(c, callback_data=f"set:{lanc_id}:{i}") for i, c in enumerate(CATEGORIAS)
    ]
    linhas = [botoes[i : i + 2] for i in range(0, len(botoes), 2)]
    linhas.append([InlineKeyboardButton("↩️ Voltar", callback_data=f"back:{lanc_id}")])
    return InlineKeyboardMarkup(linhas)


def texto_lancamento(l: Lancamento, prefixo: str = "✅ Registrado") -> str:
    try:
        data_fmt = date.fromisoformat(l.data).strftime("%d/%m/%Y")
    except ValueError:
        data_fmt = l.data
    return (
        f"{prefixo}\n\n"
        f"💰 <b>{brl(l.valor)}</b>\n"
        f"🏪 {escape(l.estabelecimento)}\n"
        f"🏷 {escape(l.categoria)} · {escape(l.subcategoria)}\n"
        f"💳 {escape(l.forma_pagamento)}\n"
        f"📅 {data_fmt}\n"
        f"📝 {escape(l.descricao)}"
    )


def montar_lancamento(gasto: Gasto, dia_padrao: date, usuario: str, tz, hash_arquivo: str) -> Lancamento:
    data = dia_padrao.isoformat()
    if gasto.data:
        try:
            data = date.fromisoformat(gasto.data).isoformat()
        except ValueError:
            pass
    return Lancamento(
        id=novo_id(),
        data=data,
        estabelecimento=gasto.estabelecimento.strip() or "Não identificado",
        valor=round(abs(gasto.valor), 2),
        categoria=gasto.categoria,
        subcategoria=gasto.subcategoria.strip(),
        forma_pagamento=gasto.forma_pagamento,
        descricao=gasto.descricao.strip(),
        registrado_em=agora_str(tz),
        usuario=usuario,
        hash_arquivo=hash_arquivo,
    )


# --- fluxo principal ----------------------------------------------------------------


async def _processar(update: Update, context: ContextTypes.DEFAULT_TYPE, ler, hash_arquivo: str = "") -> None:
    msg = update.effective_message
    status = await msg.reply_text("⏳ Lendo...")

    if hash_arquivo:
        dup = await asyncio.to_thread(planilha(context).existe_hash, hash_arquivo)
        if dup:
            await status.edit_text(
                texto_lancamento(dup, "⚠️ Esse comprovante já foi registrado:"),
                parse_mode=ParseMode.HTML,
            )
            return

    try:
        gasto: Gasto = await ler()
    except ExtractionError as e:
        await status.edit_text(f"❌ {e}")
        return

    if not gasto.eh_gasto or gasto.valor <= 0:
        motivo = gasto.motivo_rejeicao or "não encontrei um valor pago."
        await status.edit_text(f"🤔 Não parece um comprovante de gasto: {motivo}")
        return

    c = cfg(context)
    lanc = montar_lancamento(gasto, hoje(context), str(update.effective_user.id), c.timezone, hash_arquivo)
    try:
        await asyncio.to_thread(planilha(context).adicionar, lanc)
    except Exception:
        log.exception("Falha ao gravar na planilha")
        await status.edit_text("❌ Li o comprovante, mas não consegui gravar na planilha. Tente de novo.")
        return

    await status.edit_text(
        texto_lancamento(lanc), parse_mode=ParseMode.HTML, reply_markup=teclado_lancamento(lanc.id)
    )


@autorizado
async def on_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    foto = msg.photo[-1]  # maior resolução
    arquivo = await foto.get_file()
    dados = bytes(await arquivo.download_as_bytearray())
    h = hashlib.sha256(dados).hexdigest()[:16]
    await _processar(
        update,
        context,
        lambda: extractor(context).from_file(dados, "image/jpeg", msg.caption, hoje(context)),
        h,
    )


@autorizado
async def on_documento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    doc = msg.document
    mime = (doc.mime_type or "").lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in IMAGE_TYPES and mime != PDF_TYPE:
        await msg.reply_text("Formato não suportado. Envie foto (JPG/PNG) ou PDF.")
        return
    if doc.file_size and doc.file_size > LIMITE_ARQUIVO:
        await msg.reply_text("Arquivo muito grande (limite de 20 MB).")
        return
    arquivo = await doc.get_file()
    dados = bytes(await arquivo.download_as_bytearray())
    h = hashlib.sha256(dados).hexdigest()[:16]
    await _processar(
        update,
        context,
        lambda: extractor(context).from_file(dados, mime, msg.caption, hoje(context)),
        h,
    )


@autorizado
async def on_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = update.effective_message.text.strip()
    if len(texto) < 3:
        await update.effective_message.reply_text("Descreva o gasto, ex.: uber 23,50")
        return
    await _processar(update, context, lambda: extractor(context).from_text(texto, hoje(context)))


# --- comandos ---------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    texto = AJUDA
    permitidos = cfg(context).allowed_user_ids
    if not permitidos or user.id not in permitidos:
        texto += f"\n\nSeu ID do Telegram: <code>{user.id}</code>"
    await update.effective_message.reply_text(texto, parse_mode=ParseMode.HTML)


@autorizado
async def cmd_resumo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        ano, mes = parse_mes(" ".join(context.args) if context.args else None, hoje(context))
        if not 1 <= mes <= 12:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text("Use /resumo, /resumo 10 ou /resumo 10/2026")
        return
    lancs = await asyncio.to_thread(planilha(context).todos)
    await update.effective_message.reply_text(resumo_mes(lancs, ano, mes), parse_mode=ParseMode.HTML)


@autorizado
async def cmd_semana(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lancs = await asyncio.to_thread(planilha(context).todos)
    await update.effective_message.reply_text(resumo_semana(lancs, hoje(context)), parse_mode=ParseMode.HTML)


@autorizado
async def cmd_desfazer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    p = planilha(context)
    ultimo = await asyncio.to_thread(p.ultimo_do_usuario, str(update.effective_user.id))
    if not ultimo:
        await update.effective_message.reply_text("Não há lançamentos para desfazer.")
        return
    await asyncio.to_thread(p.remover, ultimo.id)
    await update.effective_message.reply_text(
        texto_lancamento(ultimo, "🗑 Lançamento apagado:"), parse_mode=ParseMode.HTML
    )


@autorizado
async def cmd_planilha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = f"https://docs.google.com/spreadsheets/d/{cfg(context).spreadsheet_id}"
    await update.effective_message.reply_text(f"📗 Sua planilha: {url}")


# --- botões -----------------------------------------------------------------------


@autorizado
async def on_botao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    acao, _, resto = q.data.partition(":")
    p = planilha(context)

    if acao == "ok":
        await q.answer("Salvo 👍")
        await q.edit_message_reply_markup(reply_markup=None)
    elif acao == "cat":
        await q.answer()
        await q.edit_message_reply_markup(reply_markup=teclado_categorias(resto))
    elif acao == "back":
        await q.answer()
        await q.edit_message_reply_markup(reply_markup=teclado_lancamento(resto))
    elif acao == "set":
        lanc_id, _, idx = resto.partition(":")
        categoria = CATEGORIAS[int(idx)]
        ok = await asyncio.to_thread(p.atualizar_categoria, lanc_id, categoria)
        if not ok:
            await q.answer("Lançamento não encontrado na planilha.", show_alert=True)
            return
        await q.answer(f"Categoria: {categoria}")
        texto = q.message.text_html or ""
        linhas = texto.split("\n")
        for i, linha in enumerate(linhas):
            if linha.startswith("🏷"):
                sub = linha.split("·", 1)[1].strip() if "·" in linha else ""
                linhas[i] = f"🏷 {escape(categoria)} · {sub}"
        await q.edit_message_text("\n".join(linhas), parse_mode=ParseMode.HTML, reply_markup=None)
    elif acao == "del":
        ok = await asyncio.to_thread(p.remover, resto)
        await q.answer("Apagado" if ok else "Já não estava na planilha")
        await q.edit_message_text("🗑 Lançamento apagado.", reply_markup=None)
    else:
        await q.answer()


async def on_erro(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Erro não tratado", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("❌ Algo deu errado. Tente novamente.")
        except Exception:
            pass


# --- inicialização ----------------------------------------------------------------


def build_app(config: Config) -> Application:
    app = Application.builder().token(config.telegram_token).build()
    app.bot_data["config"] = config
    app.bot_data["planilha"] = Planilha(
        config.spreadsheet_id, config.google_credentials_file, config.google_credentials_json
    )
    app.bot_data["extractor"] = Extractor(config.claude_model)

    app.add_handler(CommandHandler(["start", "ajuda", "help"], cmd_start))
    app.add_handler(CommandHandler("resumo", cmd_resumo))
    app.add_handler(CommandHandler("semana", cmd_semana))
    app.add_handler(CommandHandler("desfazer", cmd_desfazer))
    app.add_handler(CommandHandler("planilha", cmd_planilha))
    app.add_handler(MessageHandler(filters.PHOTO, on_foto))
    app.add_handler(MessageHandler(filters.Document.ALL, on_documento))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_texto))
    app.add_handler(CallbackQueryHandler(on_botao))
    app.add_error_handler(on_erro)
    return app


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = load_config()
    app = build_app(config)
    log.info("Bot iniciado. Aguardando mensagens...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
