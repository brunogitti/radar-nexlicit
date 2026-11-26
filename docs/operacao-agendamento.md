# Operação do agendamento da captura

Este documento explica **quem dispara** o workflow "Captura diaria", por que foi montado assim, e o passo a passo para configurar, testar, renovar e desligar o disparo externo. Nenhum token entra neste arquivo nem em qualquer arquivo do repositório.

## Por que existe

O agendamento do próprio GitHub (gatilho `schedule`) atrasava a captura de 4,5 a 10,5 horas e podia descartar execuções. Medido de 09/11 a 22/11: 28 execuções em 14 dias, nenhuma descartada, mas todas atrasadas, e o "e-mail das 7h" chegava entre 14h e 19h (Brasília). Já o disparo manual (`workflow_dispatch`) começa em segundos.

## Como funciona (A + B)

| | Quem | Quando | Trava? |
|---|---|---|---|
| **A** | Agendador gratuito externo (cron-job.org) chama a API do GitHub e dispara a "Captura diaria" | 7h07 e 13h07 de Brasília | **Não.** Sempre roda. |
| **B** | Workflow "Agendador da captura" (`.github/workflows/agendador.yml`) | De 2 em 2 horas (minuto 37 das horas pares em UTC) | **Sim.** Só dispara se não houver captura rodando ou na fila e se o banco não foi publicado nas últimas 5 horas. |

- **A** é o que dá pontualidade. **B** é a rede de segurança: se o agendador externo ou o token falhar, o B garante uma captura a cada poucas horas (dentro do atraso normal do GitHub).
- **Repescagem:** o cron-job.org também chama o B às 9h37 e 15h37 de Brasília, para que uma captura perdida (como a das 13h07 de 25/11/2026, que recebeu HTTP 500 durante um incidente do GitHub) seja refeita no mesmo dia. Detalhes no passo 6.
- A trava do B lê a hora do último commit da branch `data`. Cada publicação bem-sucedida do banco cria um commit novo lá, então essa hora é a da última publicação. A lógica está em `.github/scripts/decidir_agendamento.sh`.
- Se o B não conseguir descobrir alguma informação (API fora, resposta estranha), ele **dispara mesmo assim**: uma captura a mais é inofensiva (o banco é blindado e a captura tem fila própria), mas pular por causa de erro na conferência seria pior.
- O B fica num arquivo separado da captura de propósito. A captura tem uma fila (`concurrency`) para nunca rodar duas vezes juntas; se a trava morasse lá dentro, uma rodada que só pula poderia tirar da fila um disparo externo que estivesse esperando.
- A "Captura diaria" não tem mais `schedule` próprio. Ela só roda por `workflow_dispatch`: disparo externo (A), Agendador (B) ou manual.
- Custo: repositório público não paga minutos de Actions. Se o repositório virar privado, o B gasta cerca de 1 minuto por rodada (12 por dia).
- Uma restauração manual do banco (veja `docs/operacao-banco.md`) cria um commit novo na `data`, então a trava do B enxerga "publicado agora" e pula por até 5 horas. É esperado.

## Passo a passo do disparo externo (A)

Tudo isto é feito por você, no navegador e no seu terminal. O token nunca deve passar por conversa, e-mail, anotação do repositório ou arquivo. Ele só existe em dois lugares: no site do GitHub (onde é gerado) e no campo de cabeçalho do agendador.

### 1. Criar o token no GitHub

1. GitHub, foto do perfil, **Settings**, **Developer settings**, **Personal access tokens**, **Fine-grained tokens**, **Generate new token**.
2. **Token name:** `radar-nexlicit-agendador`.
3. **Expiration:** escolha **1 ano** (365 dias, ou a data personalizada equivalente). Anote a data de vencimento.
4. **Resource owner:** a sua conta.
5. **Repository access:** **Only select repositories**, e marque **somente** `radar-nexlicit`.
6. **Permissions, Repository permissions:** **Actions: Read and write**. Deixe todas as outras em "No access". (O GitHub adiciona "Metadata: Read-only" sozinho, é obrigatório e inofensivo.)
7. **Generate token** e copie o valor que aparece. Ele só é mostrado uma vez. Não cole em lugar nenhum além do passo 3.

### 2. Testar o token no seu terminal (sem deixar rastro)

Isto dispara **uma captura de verdade** (igual a um disparo manual). No Git Bash:

```
read -rs -p "Cole o token e tecle Enter (nada aparece na tela): " TOKEN; echo
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  https://api.github.com/repos/brunogitti/radar-nexlicit/actions/workflows/captura-diaria.yml/dispatches \
  -d '{"ref":"master"}'
unset TOKEN
```

- Resposta esperada: **HTTP 204** (ou 200). Qualquer 2xx quer dizer que o GitHub aceitou.
- Em seguida confira: `gh run list --workflow captura-diaria.yml --limit 2`. Deve aparecer um run `workflow_dispatch` começando em segundos.
- O `read -rs` não mostra o que você cola, e `unset` apaga a variável. O token não fica no histórico do terminal.
- Se der **401 ou 403**: token errado ou permissão "Actions" não marcada. Se der **404**: o token não enxerga o repositório (passo 5 acima) ou o nome do repositório está errado.

### 3. Configurar o agendador (cron-job.org)

Crie uma conta gratuita em cron-job.org e um job por horário (um às 7h07 e outro às 13h07). Campos de cada job:

- **URL:** `https://api.github.com/repos/brunogitti/radar-nexlicit/actions/workflows/captura-diaria.yml/dispatches`
- **Método:** `POST`
- **Corpo (body):** `{"ref":"master"}`
- **Cabeçalhos (headers) que a API do GitHub exige ou recomenda:**

| Cabeçalho | Valor | Para quê |
|---|---|---|
| `User-Agent` | um nome qualquer, ex.: `radar-nexlicit-agendador` | **Obrigatório.** A API do GitHub recusa (403) pedido sem `User-Agent`. |
| `Accept` | `application/vnd.github+json` | Pede a resposta no formato oficial da API. |
| `X-GitHub-Api-Version` | `2022-11-28` | Fixa a versão da API, para uma mudança futura não quebrar o job. |
| `Authorization` | `Bearer <cole o token aqui, só neste campo>` | Prova quem está chamando. É o único lugar onde o token fica. |
| `Content-Type` | `application/json` | Avisa que o corpo é JSON. |

- **Resposta esperada:** **HTTP 204** (sem corpo). Qualquer 2xx quer dizer que o GitHub aceitou e uma captura vai começar em segundos. 401/403 = token errado, vencido ou sem a permissão Actions (ou faltou o `User-Agent`). 404 = o token não enxerga o repositório. 422 = o `ref` do corpo não existe (confira `master`).
- **Horário:** 07:07 e 13:07, fuso **America/Sao_Paulo**.
- **Notificação de falha por e-mail:** ligue no próprio agendador o aviso por e-mail para qualquer resposta fora de 2xx (no cron-job.org: opção de notificar quando o job falhar; confira o nome exato da opção na tela). Sem isso, um token vencido só seria percebido pela falta do e-mail "Radar ativo" ou de captura.

**Confira no agendador antes de confiar nele** (não consegui verificar na página oficial do serviço, só em fontes de terceiros):

1. O plano **gratuito** aceita método **POST** com **cabeçalho personalizado** e **corpo JSON**?
2. O fuso **America/Sao_Paulo** existe nas opções e os horários aparecem como 07:07 e 13:07? (O Brasil não tem horário de verão desde 2019, então se o fuso não existir, dá para usar 10:07 e 16:07 em UTC.)
3. O agendador deixa você definir o cabeçalho `User-Agent`? A API do GitHub exige um. Se o agendador mandar o dele no lugar do seu, tudo bem; se o teste do passo 4 devolver 403, é por aqui que se investiga.
4. Existe limite de execuções ou de tamanho de resposta no plano gratuito que atrapalhe 2 chamadas por dia?

### 4. Testar pelo agendador

1. Use o botão de teste do job (ou crie um job temporário para daqui a 5 minutos). A resposta registrada deve ser 2xx.
2. Confira com `gh run list --workflow captura-diaria.yml --limit 3`: run `workflow_dispatch` perto do horário.
3. Depois da primeira semana, meça o atraso real (veja "Como medir" abaixo).

### 5. Aviso de renovação do token

O token vence na data escolhida (1 ano). Três proteções:

1. O GitHub costuma avisar por e-mail antes de um token vencer. Confirme em Settings, Notifications que e-mails de segurança estão ligados, mas **não dependa só disso**.
2. **Lembrete no calendário** 30 dias antes do vencimento: "Renovar token do agendador do Radar". Crie assim que tiver a data.
3. A rede de segurança B continua rodando de 2 em 2 horas. Se o token vencer, o disparo externo falha (e o agendador avisa por e-mail), mas o Radar continua capturando. O que se perde é só a pontualidade das 7h07 e 13h07.

**Renovar:** gere um token novo com as mesmas configurações (ou use "Regenerate token" na página do token), troque o valor do cabeçalho `Authorization` nos **quatro** jobs (os dois de captura e os dois de repescagem, abaixo), teste (passo 4) e só então revogue o token antigo. Anote a nova data de vencimento e atualize o lembrete.

### 6. Repescagem (dois jobs a mais no cron-job.org)

**Por que existe.** Em 25/11/2026 o disparo das 13h07 recebeu **HTTP 500** do GitHub (incidente oficial do GitHub das 15:55 às 16:52 UTC, com "Actions" e "API Requests" degradados) e nenhuma captura começou. O B devia cobrir, mas o GitHub entrega só cerca de 2 dos 12 horários dele por dia, e horário perdido não é recuperado. O Radar ficou 7h30 sem capturar. A repescagem é uma segunda chance no mesmo dia, 2h30 depois de cada disparo.

**O que ela faz.** Ela **não** chama a captura. Ela chama o **Agendador (B)**, que confere a trava: se a captura das 7h07 (ou das 13h07) rodou, ele termina verde **sem disparar nada**; se não rodou, ele dispara a captura. Assim a repescagem nunca gera captura repetida.

**Criar no cron-job.org** dois jobs novos, iguais aos de captura em tudo, menos a URL e o horário:

| Campo | Valor |
|---|---|
| Título (sugestão) | `Radar repescagem 09h37` e `Radar repescagem 15h37` |
| **URL** | `https://api.github.com/repos/brunogitti/radar-nexlicit/actions/workflows/agendador.yml/dispatches` (atenção: **agendador.yml**, não captura-diaria.yml) |
| **Método** | `POST` |
| **Corpo** | `{"ref":"master"}` (sem `inputs`: o `ignorar_trava` fica desligado, que é o que se quer) |
| **Cabeçalhos** | os mesmos cinco da tabela do passo 3, com o mesmo token |
| **Horário** | 09:37 e 15:37, fuso America/Sao_Paulo (12:37 e 18:37 em UTC) |
| **Notificação de falha** | por e-mail, já na **primeira** falha |
| **Resposta esperada** | HTTP 204 |

O token atual serve: a permissão "Actions: Read and write" vale para qualquer workflow do repositório.

**Como fica um dia normal** (captura completa de cerca de 2h20 com os 389 municípios, medido na #271 de 26/11/2026):

| Horário | O que acontece |
|---|---|
| 07h07 | Captura (A). Publica o banco por volta das 09h30. |
| 09h37 | Repescagem: o banco foi publicado há menos de 5 h, o B **pula**. |
| 13h07 | Captura (A). Publica por volta das 15h30. |
| 15h37 | Repescagem: o banco foi publicado há menos de 5 h (ou a captura ainda está rodando), o B **pula**. |

**Quando a captura falha:** se a das 7h07 não rodou, às 09h37 a última publicação é da véspera e o B dispara. Se a das 13h07 não rodou, às 15h37 a última publicação é a da manhã (cerca de 6 h antes) e o B dispara. Isso depende de a captura da manhã publicar até 10h37: com o teto de 3 horas do workflow, a mais lenta possível publica por volta das 10h10. Caso raro que não é coberto: as **duas** do dia falharem e a repescagem das 09h37 ter publicado depois das 10h37. Às 15h37 ainda não terão passado 5 h e o B pula. O B de 2 em 2 horas e o e-mail semanal continuam cobrindo esse caso.

**Testar:** use o botão de teste de um dos jobs. A resposta deve ser 204. Em `gh run list --workflow agendador.yml --limit 3` aparece um run `workflow_dispatch` que termina verde com a linha "Decisao: ..." dizendo que pulou (porque houve captura recente). Nenhuma captura nova deve aparecer em `gh run list --workflow captura-diaria.yml --limit 3`.

**Limite:** a repescagem depende do mesmo cron-job.org que dispara a captura. Se o próprio cron-job.org parar, as duas param juntas. Um alarme independente (healthchecks.io) ficou para depois.

## Como medir o atraso

```
gh run list --workflow captura-diaria.yml --limit 30 --json createdAt,event -q '.[] | [.createdAt, .event] | @tsv'
```

- 7h07 de Brasília = 10:07 UTC, e 13h07 = 16:07 UTC. Compare o `createdAt` dos runs `workflow_dispatch` com esses horários.
- Para ver o que o Agendador (B) decidiu em cada rodada: `gh run list --workflow agendador.yml --limit 12` e abrir um run para ler a linha "Decisao: ...". Rodada que pulou termina verde sem disparar nada.

## Como desligar

- **Só o A:** pause ou apague os jobs no agendador e revogue o token (Settings, Developer settings, Fine-grained tokens, Delete). O B continua funcionando.
- **Só o B:** apague `.github/workflows/agendador.yml` (ou comente o bloco `schedule`). Nesse caso volte a depender só do A, ou devolva um `schedule` à "Captura diaria".
- **Segurança:** quem tiver o token consegue disparar a "Captura diaria" (e ligar seus inputs, como `permitir_reducao_do_banco`). A blindagem do banco limita o estrago (backup antes, banco vazio nunca é publicado). Se o token vazar, revogue na hora.

## Testar o Agendador (B) sem esperar

Depois que o `agendador.yml` estiver na `master`: `gh workflow run agendador.yml` roda a decisão com a trava normal (se houve captura há menos de 5 horas, termina pulando e nada é disparado). Com `-f ignorar_trava=true` ele dispara uma captura de verdade, útil para provar o caminho completo.

## Limite de horas do Agendador (B)

O limite (padrão 5 horas) fica numa variável do repositório chamada `HORAS_MINIMAS_ENTRE_CAPTURAS` (Settings, Secrets and variables, Actions, aba Variables). Mudar o valor lá vale na próxima rodada, sem editar código. Variável ausente ou vazia significa 5.

Quantas capturas por dia, com o disparo externo (A) às 7h07 e 13h07 e tudo no horário (estimativa, sem contar o atraso do próprio GitHub no agendamento do B, que existe):

| Limite do B | Capturas do A | Capturas extras do B | Total por dia | Maior pausa normal |
|---|---|---|---|---|
| 5 h | 2 | cerca de 2 (por volta de 19h37 e 1h37) | cerca de 4 | cerca de 6 h |
| 20 h | 2 | 0 enquanto o A funciona | 2 | cerca de 18 h (13h07 até 7h07) |

Com 5 h o B funciona como um segundo e terceiro horário "de graça", preenchendo a madrugada. Com 20 h ele só age se o A falhar (a espera máxima entre publicações com o A funcionando é de cerca de 18 h; o limite precisa ser maior que isso).
