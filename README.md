# Painel de Chamados TI - Open Source

Projeto Flask com padrao MVC para exibir, sincronizar e analisar chamados de TI registrados em uma planilha do Google Sheets (alimentada por Google Forms), com persistencia em banco local SQLite.

## Estrutura

- `app/models`: entidades de dominio
- `app/controllers`: rotas e controle de fluxo
- `app/services`: integracao com API externa
- `app/templates`: camada de visualizacao
- `app/static`: arquivos CSS

## Requisitos

- Python 3.11+
- Projeto no Google Cloud com Google Sheets API habilitada
- Conta de servico (Service Account) com JSON de credenciais

## Padrao da planilha (obrigatorio)

Para integrar com o painel, siga este formato de colunas na aba configurada em `GOOGLE_SHEETS_RANGE`:

- Coluna A: Data e hora
- Coluna B: Local
- Coluna C: Problema
- Coluna D: Solicitante
- Coluna E: Status (`EM ANDAMENTO`, `CONCLUÍDO` ou vazio)

Os `Locais` sao definidos por quem cria o Form/planilha (listas pre-gravadas no Google Forms ou digitacao livre), e o sistema computa automaticamente esses valores para analytics por local.

## Configuracao

1. Crie e ative um ambiente virtual (voce ja possui `env/`).
2. Instale dependencias:

```bash
pip install -r requirements.txt
```

3. Crie o arquivo `.env` na raiz do projeto (voce pode copiar de `.env.example`):

```bash
copy .env.example .env
```

Se preferir, crie manualmente com apenas os campos necessarios.

Modelo minimo sugerido:

```env
GOOGLE_SERVICE_ACCOUNT_FILE=credenciais/service-account.json
GOOGLE_SHEETS_ID=id-da-planilha
GOOGLE_SHEETS_RANGE=Respostas ao formulario 1!A:E
SECRET_KEY=sua-chave-secreta
DATABASE_PATH=data/chamados.db
APP_BOOTSTRAP_ADMIN_USER=admin
APP_BOOTSTRAP_ADMIN_PASS=admin123
```

Campos opcionais de personalizacao (somente se quiser):

- `APP_BRAND_SHORT`
- `APP_BRAND_NAME`
- `APP_ORG_NAME`
- `APP_TICKETS_TITLE`
- `APP_DASHBOARD_TITLE`
- `APP_TICKETS_SUBTITLE`
- `APP_THEME_PALETTE`
- `APP_LOCAL_COLORS_JSON`

Preencha principalmente:

- `GOOGLE_SERVICE_ACCOUNT_FILE`: caminho para o JSON da conta de servico
- `GOOGLE_SHEETS_ID`: ID da planilha
- `GOOGLE_SHEETS_RANGE`: aba e intervalo (ex.: `Respostas ao formulario 1!A:E`)
- `DATABASE_PATH`: caminho do banco local SQLite (ex.: `data/chamados.db`)
- `SYNC_INTERVAL_SECONDS`: intervalo de sincronizacao planilha -> banco (padrao: `20`)

Exemplo de caminho no Windows:

```env
GOOGLE_SERVICE_ACCOUNT_FILE=credenciais/service-account.json
```

4. Compartilhe a planilha com o e-mail da conta de servico (como Leitor ou Editor).

5. Inicie o sistema e acesse `Configuracoes` para:

- validar conexao,
- cadastrar motivos de conclusao (ex.: `Formatacao`, `Reinicio`, `Troca de equipamento`),
- personalizar textos da interface.

6. (Recomendado) Crie/gerencie contas administrativas via terminal:

```bash
python manage_admin.py
```

Menu disponivel no script:

- `1` listar contas
- `2` criar conta / redefinir senha
- `3` alterar login
- `4` alterar senha
- `5` remover conta (mantendo ao menos 1 admin)
- `0` sair

### Personalizacao de textos (menu e titulos)

Voce pode personalizar os textos principais no `.env` e tambem na tela `Configuracoes`:

- `APP_BRAND_SHORT`: nome curto no menu lateral (ex.: `SEMSAU`)
- `APP_BRAND_NAME`: nome principal no menu lateral (ex.: `Painel de Chamados`)
- `APP_ORG_NAME`: titulo institucional (ex.: `Secretaria Municipal de Saude`)
- `APP_TICKETS_TITLE`: titulo da pagina de chamados
- `APP_DASHBOARD_TITLE`: titulo da pagina dashboard
- `APP_TICKETS_SUBTITLE`: subtitulo da pagina de chamados

Esses campos podem ser alterados sem mexer no codigo.

## Executar

```bash
python run.py
```

Acesse `http://127.0.0.1:5000`.

## Docker

### Estrutura de persistencia

Para nao perder configuracoes ao reiniciar o container, o compose monta volumes para:

- `./data` -> banco local SQLite (`/app/data`)
- `./credenciais` -> credenciais Google (`/app/credenciais`)
- `./.env` -> configuracoes locais (`/app/.env`)

### Subir com Docker Compose

1. Garanta que o `.env` exista na raiz (pode copiar de `.env.example`).
2. Garanta que `credenciais/service-account.json` exista.
3. Suba o app:

```bash
docker compose up --build -d
```

4. Acesse:

```text
http://localhost:5000
```

### Parar

```bash
docker compose down
```

### Gerenciar contas admin via script no container

```bash
docker compose exec chamados-app python manage_admin.py
```

Ao abrir, o sistema redireciona para a tela de login administrativo.

## Login administrativo

- Todas as telas do painel exigem autenticacao.
- O logout fica no canto inferior esquerdo da barra lateral.


Importante: altere essas credenciais padrao antes de uso em producao/rede interna.

## Recursos da interface

- Ordenacao automatica: chamados mais novos primeiro.
- Sincronizacao automatica incremental: novos chamados entram sem reload da pagina.
- Atualizacao de status no painel: altere para `Em aberto`, `Em andamento` ou `Concluido`; o valor e escrito na coluna E da planilha.
- Armazenamento local para analise: os chamados sao salvos em banco SQLite para historico e relatorios futuros.
- Motivo de conclusao independente de status: pode ser ajustado no chamado e fica salvo no banco local.
- Notificacoes flutuantes: feedback no canto superior direito para sucesso, alertas e erros.
- Aba `Analytics`: analises por local e por motivo de conclusao com filtros.

## Como criar a planilha para integrar

1. Crie um Google Form com os campos desejados.
2. Na aba `Respostas`, clique em `Vincular ao Planilhas` para gerar a planilha automaticamente.
3. Garanta a estrutura minima de colunas:
   - A: Data e hora
   - B: Local
   - C: Problema
   - D: Solicitante
   - E: Status (pode iniciar vazio)
4. Copie o ID da planilha pela URL e configure `GOOGLE_SHEETS_ID`.
5. Configure `GOOGLE_SHEETS_RANGE` com a aba e intervalo (ex.: `Respostas ao formulario 1!A:E`).
6. Compartilhe a planilha com o e-mail da Service Account.

Importante: mesmo se um chamado for removido da planilha, ele permanece no banco local para historico analitico.

Pronto: o painel passa a ler e sincronizar os chamados automaticamente.

## Como mapear colunas

No servico `app/services/sheets_service.py`, o mapeamento atual considera:

- Coluna A: Data e hora
- Coluna B: Local
- Coluna C: Problema
- Coluna D: Solicitante
- Coluna E: Status (`CONCLUIDO`, `EM ANDAMENTO` ou vazio)

Se sua planilha tiver outra ordem, ajuste os indices no metodo `fetch_tickets`.

Quando o status vier vazio, o sistema exibe `Em aberto`.

## Banco local para analise

O sistema mantem os chamados em banco SQLite (`DATABASE_PATH`) para uso analitico futuro. Isso permite tratar os dados independente da planilha.

Fluxo de performance:

- A interface le diretamente do banco local (mais rapido).
- A sincronizacao com Google Sheets ocorre em background pelo intervalo configurado em `SYNC_INTERVAL_SECONDS`.
- Alteracoes feitas no painel persistem primeiro no banco e sincronizam a planilha de forma assincrona.

Tabelas principais:

- `tickets`: snapshot local dos chamados, incluindo `resolution_reason`.
- `resolution_reasons`: motivos de conclusao pre-cadastrados no Settings.

Analises disponiveis na aba `Analytics`:

- Ranking de locais com mais chamados.
- Ranking de motivos de conclusao mais frequentes.
- Filtros por status e por local.

Fluxo:

1. Chamados sao lidos da planilha.
2. Dados sao sincronizados no banco local.
3. Alteracoes de status atualizam planilha e banco.
4. Se status for `Concluido`, motivo e obrigatorio.

Valores de status sao normalizados automaticamente para exibicao:

- `concluido` -> `Concluido`
- `em andamento` -> `Em andamento`
- vazio -> `Em aberto`

## Solucao de problemas

- Erro `Google Sheets API (403)`: confirme se a planilha foi compartilhada com o e-mail da conta de servico.
- Erro de arquivo de credenciais: valide o caminho em `GOOGLE_SERVICE_ACCOUNT_FILE`.
- Aba nao encontrada: confira `GOOGLE_SHEETS_RANGE` com o nome exato da aba.
