#!/usr/bin/env bash
# Decide se o agendador (workflow "Agendador da captura") deve disparar uma
# captura agora ou pular esta rodada. Roda de 2 em 2 horas, mas so dispara de
# verdade se a ultima captura publicada foi ha mais de 5 horas.
#
# Regras, nesta ordem:
#   1. IGNORAR_TRAVA=true         -> dispara (so para teste manual).
#   2. Ja tem captura rodando ou na fila -> pula (evita duas capturas seguidas).
#   3. A branch "data" teve commit ha menos de HORAS_MINIMAS_ENTRE_CAPTURAS
#      horas -> pula. Cada publicacao bem-sucedida do banco cria um commit novo
#      na branch data, entao a hora desse commit e a hora da ultima publicacao.
#   4. Caso contrario -> dispara.
#
# Se nao for possivel descobrir alguma dessas informacoes (erro de rede, API
# fora do ar, resposta estranha), o script DISPARA mesmo assim. E de proposito:
# uma captura a mais e inofensiva (o banco e blindado e o workflow de captura
# tem trava propria contra duas execucoes juntas), mas deixar de capturar por
# causa de um erro na conferencia seria pior.
#
# A trava vale so para o gatilho "schedule". O disparo externo (agendador
# gratuito) chama a captura diretamente e nunca passa por aqui.
#
# O resultado sai em duas formas: uma frase na tela e, se a variavel
# GITHUB_OUTPUT existir (dentro do GitHub Actions), a linha executar=true ou
# executar=false, que o workflow le no passo seguinte.
#
# Variaveis de ambiente que ele le:
#   GH_REPO                        dono/repositorio (ex.: brunogitti/radar-nexlicit)
#   HORAS_MINIMAS_ENTRE_CAPTURAS   padrao: 5
#   IGNORAR_TRAVA                  "true" dispara sem conferir nada (padrao: false)
#   GH_BIN                         comando do gh (padrao: gh). So os testes mudam.
#   AGORA_EM_SEGUNDOS              "agora" em segundos desde 1970. So os testes mudam.

set -uo pipefail

GH_BIN="${GH_BIN:-gh}"
HORAS_MINIMAS_ENTRE_CAPTURAS="${HORAS_MINIMAS_ENTRE_CAPTURAS:-5}"
IGNORAR_TRAVA="${IGNORAR_TRAVA:-false}"
AGORA_EM_SEGUNDOS="${AGORA_EM_SEGUNDOS:-$(date -u +%s)}"
GH_REPO="${GH_REPO:-}"

decidir() {
  # Uso: decidir true|false "motivo". Escreve o resultado e termina o script.
  echo "Decisao: executar=$1. $2"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "executar=$1" >> "$GITHUB_OUTPUT"
  fi
  exit 0
}

if [ "$IGNORAR_TRAVA" = "true" ]; then
  decidir true "Trava ignorada a pedido (ignorar_trava ligado)."
fi

if [ -z "$GH_REPO" ]; then
  decidir true "Nao sei qual e o repositorio (GH_REPO vazio), nao deu pra conferir. Disparando por seguranca."
fi

# 2) Ja existe uma captura rodando ou esperando na fila?
for situacao in in_progress queued; do
  if ! quantidade=$("$GH_BIN" run list --repo "$GH_REPO" --workflow captura-diaria.yml \
    --status "$situacao" --json databaseId --jq 'length' 2> /dev/null) \
    || ! [[ "$quantidade" =~ ^[0-9]+$ ]]; then
    echo "Aviso: nao consegui listar as capturas com situacao '$situacao'. Sigo sem essa conferencia."
    continue
  fi
  if [ "$quantidade" -gt 0 ]; then
    decidir false "Ja existe ${quantidade} captura(s) com situacao '${situacao}'. Pulando esta rodada."
  fi
done

# 3) Quando foi a ultima publicacao do banco (ultimo commit da branch data)?
if ! data_do_ultimo_commit=$("$GH_BIN" api "repos/${GH_REPO}/branches/data" \
  --jq '.commit.commit.committer.date' 2> /dev/null) || [ -z "$data_do_ultimo_commit" ]; then
  decidir true "Nao consegui ler a data do ultimo commit da branch data. Disparando por seguranca."
fi

if ! momento_da_ultima_publicacao=$(date -u -d "$data_do_ultimo_commit" +%s 2> /dev/null) \
  || ! [[ "$momento_da_ultima_publicacao" =~ ^[0-9]+$ ]]; then
  decidir true "A data lida da branch data ('${data_do_ultimo_commit}') nao faz sentido. Disparando por seguranca."
fi

segundos_desde_a_publicacao=$(( AGORA_EM_SEGUNDOS - momento_da_ultima_publicacao ))
limite_em_segundos=$(( HORAS_MINIMAS_ENTRE_CAPTURAS * 3600 ))
minutos_desde_a_publicacao=$(( segundos_desde_a_publicacao / 60 ))

if [ "$segundos_desde_a_publicacao" -lt "$limite_em_segundos" ]; then
  decidir false "Ultima publicacao do banco: ${data_do_ultimo_commit} (ha ${minutos_desde_a_publicacao} min), menos de ${HORAS_MINIMAS_ENTRE_CAPTURAS} h. Pulando esta rodada."
fi

decidir true "Ultima publicacao do banco: ${data_do_ultimo_commit} (ha ${minutos_desde_a_publicacao} min), ${HORAS_MINIMAS_ENTRE_CAPTURAS} h ou mais. Disparando a captura."
