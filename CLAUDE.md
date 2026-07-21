# Radar NexLicit

Aplicação Python que captura editais com proposta em aberto no PNCP (Portal Nacional de Contratações Públicas) para 142 municípios de SP/MG/MS, filtra por palavra-chave configurável, tagueia por segmento de produto, deduplica via SQLite local, entrega por e-mail, automatiza via GitHub Actions, e expõe um painel público em Streamlit. Serve dois propósitos: uso operacional real pela NexLicit (consultoria em licitações) e peça de portfólio pública no GitHub.

Bruno (dono do projeto) é iniciante em programação e fundador da NexLicit. Prefere entender cada mudança, não só recebê-la pronta.

## Regras de colaboração (sempre valem, não são negociáveis por tarefa)

- Explicar cada mudança de código em linguagem simples antes ou durante a aplicação, assumindo zero bagagem de programação (decorators, list comprehensions, context managers, o que for, sempre explicar quando aparecer).
- Entregar uma coisa por vez (um arquivo ou uma função), esperar o Bruno rodar e confirmar entendimento antes de continuar.
- Perguntar quando faltar informação, nunca inventar ou assumir.
- Código simples e legível em vez de compacto/esperto ("sem código mágico").
- Identificadores de código (funções, variáveis, campos de banco/dataclass) em português, inclusive termos do domínio (numero_controle_pncp, orgao, municipio, banco, captura, entrega). Comentários e docstrings também em português.
- Nunca alucinar comportamento de API ou biblioteca: confirmar com documentação real ou chamada de teste real antes de afirmar algo. Já aconteceu de verdade neste projeto (situacaoCompraId vindo como número e não string; endpoint de itens/arquivos não documentado no Swagger oficial, só existe testando; limite do AppTest do Streamlit pra simular clique).
- Trabalhar por camada/etapa, não começar a próxima sem aprovação explícita.
- Nunca usar travessão (em-dash) em nenhum texto escrito pro Bruno (commits, mensagens, README): usar ponto ou vírgula.

## Convenções de teste

- `pytest`, um arquivo `tests/test_<modulo>.py` por módulo de `captura/`, `entrega/`.
- Helper `_<coisa>_de_teste()` local a cada arquivo de teste (ex. `_edital_de_teste()` em `test_banco.py`), não um módulo de fixtures compartilhado.
- Chamada externa real (HTTP, SMTP) sempre trocada por mock via `monkeypatch`, nunca bate em serviço de verdade dentro de um teste automatizado.
- Rodar tudo: `python -m pytest tests/ -v` (venv ativado). Suíte inteira roda em menos de 1 segundo, sempre rodar depois de qualquer mudança em `captura/`, `entrega/` ou `tests/`.
- Todo módulo em `captura/*.py` deveria ter teste. `pncp_client.py` ficou sem teste até ser mexido pela segunda vez (Tarefa A.2): se criar/alterar uma função ali, aproveitar pra cobrir com teste também, não só a parte nova.
- Scripts em `scripts/` (auxiliares, rodados sob demanda) e `main.py`/`painel/app.py` (orquestração) não seguem essa convenção de teste unitário; verificação deles é manual, contra dado real.

## Arquitetura, decisões não óbvias

- **`cnpj_orgao`/`ano_compra`/`sequencial_compra` não são colunas do banco** (só existem no objeto `Edital` em memória durante a captura). Qualquer coisa que precise deles depois de salvo (scripts de backfill, busca de documentos no painel) extrai de dentro do `link_pncp` já salvo, formato `.../editais/{cnpj}/{ano}/{sequencial}`, via `pncp_client.extrair_cnpj_ano_sequencial`.
- **Convenção `None` vs lista vazia** em campos tipo `beneficios_itens`, `itens`, documentos buscados ao vivo no painel: `None` significa "não foi possível buscar agora" (falha de rede/API), lista vazia significa "buscou com sucesso, não tem nada mesmo". Nunca confundir os dois na exibição.
- **Branch `data` no GitHub é a única fonte de persistência do `dados/radar.db`** entre execuções da captura automática, e é dela (não da `master`) que o Streamlit Community Cloud lê pra alimentar o painel público. Ela é reconstruída do zero a cada execução do workflow (código atual da `master` + banco atualizado, um commit só, `--force`, sem acumular histórico). Mudança em `master` só aparece no painel público depois que o workflow "Captura diaria" rodar de novo (agendado 7h/13h Brasília, ou manual via `gh workflow run captura-diaria.yml`).
- **`itens_edital`** é tabela filha de `editais` (chave composta `numero_controle_pncp` + `numero_item`, upsert). Documentos/anexos do edital **não são salvos em lugar nenhum**, busca sempre ao vivo na API do PNCP quando o card é aberto no painel (decisão explícita do Bruno, pra não criar schema novo só pra um link de download).
- Endpoints de itens e de arquivos do PNCP (`/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens` e `.../arquivos`) **não estão documentados no Swagger oficial** (`https://pncp.gov.br/api/consulta/v3/api-docs`), só existem testando contra a API de verdade. Não assumir que outro endpoint parecido existe sem testar.
- `scripts/` guarda ferramentas auxiliares rodadas sob demanda (backfill, ressincronização), nunca fazem parte do fluxo diário automatizado.

## Lições aprendidas com o Streamlit

- `st.container(key="algo")` gera a classe CSS `st-key-algo`, documentada e estável entre versões. CSS mirando isso é seguro. CSS mirando classe interna automática do Streamlit é frágil, evitar.
- `gap=None` num container tira o espaçamento automático entre os elementos dele: sem isso, o espaçamento "some" era o padrão do Streamlit (16px/"small") somado a qualquer margem própria escrita a mão, o que gerava inconsistência difícil de prever. Preferir `gap=None` + margem explícita quando o espaçamento precisa ser controlado com precisão.
- `st.expander` por padrão executa o conteúdo mesmo fechado. Pra carregamento preguiçoso de verdade (só busca dado quando o usuário abre), precisa de `on_change="rerun"` e checar a propriedade `.open` antes de fazer a busca.
- `AppTest` (ferramenta de teste automatizado do próprio Streamlit) não consegue simular abrir um expander com `on_change="rerun"`, nem tem um jeito nativo de verificar clique num `st.link_button`. Testar essas duas peças isoladas (chamando a função de renderização direto) dá confiança razoável, mas a confirmação final desses fluxos específicos depende de teste manual real.
- Depois de editar um módulo importado pelo `painel/app.py` (ex. `captura/banco.py`), **um processo `streamlit run` já rodando não pega a mudança sozinho**: o Streamlit re-executa o script principal a cada hot-reload, mas não reimporta módulos já carregados no mesmo processo Python. Sempre matar o processo antigo (`netstat -ano | grep :8501` pra achar o PID, `taskkill //F //PID <pid>`) antes de subir um novo depois de mexer em qualquer arquivo fora de `painel/app.py`. O mesmo tipo de cache pode acontecer no Streamlit Community Cloud; a correção lá é um reboot manual pelo "Manage app".

## Como rodar localmente

```
python main.py --dias 7                              # captura, sem enviar e-mail
python main.py --dias 7 --enviar-email seu@email.com  # captura + envia e-mail
python main.py --historico --dias 90                  # so consulta o banco local
streamlit run painel/app.py --server.port 8501        # painel local
python -m pytest tests/ -v                             # suite de testes
```
