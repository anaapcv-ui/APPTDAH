# 💸 Bot de Gastos (Telegram + Claude + Google Sheets)

Um contato no Telegram para onde você manda **comprovantes de gastos** (foto, print de Pix, PDF do banco ou um texto como `uber 23,50`). O bot lê o comprovante com o Claude, categoriza o gasto e grava uma linha numa planilha do Google Sheets. Assim você vê com facilidade para onde vai o seu dinheiro.

```
Você ──foto/PDF/texto──▶ Bot no Telegram ──▶ Claude lê e categoriza ──▶ Google Sheets
                              ◀── "✅ R$ 52,90 · Mercado"  [✔️ Ok] [✏️ Categoria] [🗑 Apagar]
```

## O que ele faz

- Lê **fotos** (cupom fiscal, nota, print de Pix), **PDFs** (comprovante bancário, boleto pago) e **texto livre**.
- Extrai data, estabelecimento, valor, categoria, subcategoria, forma de pagamento e uma descrição.
- Usa **15 categorias fixas** (editáveis em `gastos_bot/config.py`).
- Tem botões para **corrigir a categoria** ou **apagar** o lançamento com um toque.
- **Detecta comprovante repetido**: o mesmo arquivo enviado duas vezes não é lançado em dobro.
- Comandos:
  - `/resumo`: total do mês por categoria e os lugares onde você mais gastou. Aceita `/resumo 10` ou `/resumo 10/2026`.
  - `/semana`: últimos 7 dias.
  - `/desfazer`: apaga o último lançamento.
  - `/planilha`: link da planilha.
- Só responde aos IDs do Telegram que você autorizar.

## Configuração (uns 20 minutos, uma vez só)

### 1. Criar o bot no Telegram
1. No Telegram, abra o **@BotFather** e envie `/newbot`.
2. Escolha um nome (ex.: *Meus Gastos*) e um usuário terminado em `bot` (ex.: `meus_gastos_ana_bot`).
3. Guarde o **token** que ele devolver (algo como `123456:ABC-...`).

### 2. Chave da API do Claude
1. Acesse <https://console.anthropic.com>, crie uma conta e adicione créditos.
2. Em **API Keys**, crie uma chave e guarde-a.

### 3. Google Sheets
1. Em <https://console.cloud.google.com>, crie um projeto (ex.: `bot-gastos`).
2. Em **APIs e serviços → Biblioteca**, ative a **Google Sheets API**.
3. Em **APIs e serviços → Credenciais → Criar credenciais → Conta de serviço**, crie uma conta de serviço (não precisa dar nenhum papel).
4. Abra a conta de serviço criada, vá em **Chaves → Adicionar chave → JSON** e salve o arquivo como `service_account.json` na pasta do projeto.
5. Crie uma planilha nova no Google Sheets e **compartilhe-a como Editor** com o e-mail da conta de serviço (algo como `bot-gastos@seu-projeto.iam.gserviceaccount.com`).
6. Copie o **ID da planilha**: é o trecho da URL entre `/d/` e `/edit`.

O bot cria sozinho a aba **"Lançamentos"** com o cabeçalho na primeira execução.

### 4. Rodar
```bash
python3 -m venv .venv
source .venv/bin/activate        # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # preencha o token, a chave e o ID da planilha
python -m gastos_bot
```

Envie `/start` ao seu bot. Ele mostra o seu **ID do Telegram**. Coloque esse número em `ALLOWED_USER_IDS` no `.env` e reinicie o bot. Pronto: é só mandar comprovantes.

> O bot usa *polling*, então não precisa de domínio nem de HTTPS. Ele funciona enquanto o processo estiver rodando.

## Deixar rodando 24h

Qualquer serviço que rode um processo contínuo serve, por exemplo **Railway**, **Render** (Background Worker), **Fly.io** ou uma VPS. O projeto já vem com `Dockerfile` e `Procfile` (`worker: python -m gastos_bot`).

Nesses serviços, em vez de subir o `service_account.json`, cole **o conteúdo inteiro** do JSON na variável `GOOGLE_CREDENTIALS_JSON` e configure as outras variáveis do `.env.example` no painel.

## Visualizando os gastos na planilha

A aba **Lançamentos** tem as colunas: ID, Data, Estabelecimento, Valor, Categoria, Subcategoria, Forma de pagamento, Descrição, Registrado em, Usuário e Hash do arquivo.

Para um painel visual:
1. Selecione as colunas da aba e use **Inserir → Tabela dinâmica** (em uma nova aba "Resumo").
2. Em Linhas, coloque **Categoria**. Em Valores, coloque **Valor (SOMA)**. Em Filtros, coloque **Data** (filtre pelo mês).
3. Use **Inserir → Gráfico → Pizza** sobre a tabela dinâmica.

## Custos

- Telegram: grátis.
- Google Sheets: grátis.
- Claude: cobra por uso. Cada comprovante custa uma fração de centavo de dólar com o modelo padrão (`claude-opus-5-5`, com esforço baixo). Para gastar ainda menos, troque `CLAUDE_MODEL` no `.env` por `claude-sonnet-5-5` ou `claude-haiku-5-5`.

## Estrutura do código

| Arquivo | Função |
|---|---|
| `gastos_bot/bot.py` | Handlers do Telegram (fotos, PDFs, texto, comandos e botões) |
| `gastos_bot/extractor.py` | Leitura do comprovante com o Claude, com saída estruturada validada por Pydantic |
| `gastos_bot/sheets.py` | Gravação, edição e leitura na planilha (gspread) |
| `gastos_bot/resumo.py` | Cálculo e formatação dos resumos |
| `gastos_bot/config.py` | Variáveis de ambiente, categorias e formas de pagamento |

Testes: `pip install pytest && python -m pytest`.

## Próximas ideias

- Orçamento por categoria, com alertas do tipo "você já usou 80% de Delivery".
- Salvar o arquivo do comprovante no Google Drive e colocar o link na planilha.
- Resumo automático toda segunda-feira e no fim do mês.
- Gráfico de pizza enviado direto no chat.
