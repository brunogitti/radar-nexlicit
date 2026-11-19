#!/usr/bin/env bash
# Publica o banco atualizado na branch "data", com conferencias antes e
# backup antes. A ordem e de proposito:
#
#   1. Conferencias (o banco local esta inteiro? nao esta vazio? nao tem
#      MENOS editais que o banco remoto?). Qualquer problema bloqueia tudo.
#   2. Backup datado do banco remoto (o que esta prestes a ser sobrescrito)
#      na branch "backups", compactado com gzip, mantendo so os 7 mais
#      recentes. Se o backup falhar, o banco novo NAO e publicado.
#   3. Publicacao na branch "data".
#
# As duas publicacoes (backups e data) tentam de novo, com espera de 10, 30
# e 60 s, antes de desistir. O e-mail da captura ja saiu antes deste passo
# (isso nao muda); por isso as conferencias mais importantes tambem rodam
# no inicio do job, em restaurar_banco.sh.
#
# Variaveis de ambiente que ele le:
#   PERMITIR_INICIO_DO_ZERO     "true" permite publicar sem existir banco remoto
#   PERMITIR_REDUCAO_DO_BANCO   "true" permite publicar um banco com MENOS
#                               editais que o remoto (nunca libera banco vazio)
#   CARIMBO_BACKUP              data/hora do nome do backup (padrao: agora, em
#                               UTC, formato AAAAMMDD-HHMMSS). So os testes mudam.
#   GIT_NOME, GIT_EMAIL         identidade dos commits (padrao: github-actions[bot])
#   PYTHON_BIN, ESPERAS_ENTRE_TENTATIVAS   como em restaurar_banco.sh

set -uo pipefail
# shellcheck source=comum.sh
source "$(dirname "${BASH_SOURCE[0]}")/comum.sh"
cd "$RAIZ_DO_REPOSITORIO" || exit 1

PERMITIR_INICIO_DO_ZERO="${PERMITIR_INICIO_DO_ZERO:-false}"
PERMITIR_REDUCAO_DO_BANCO="${PERMITIR_REDUCAO_DO_BANCO:-false}"
QUANTIDADE_DE_BACKUPS=7
GIT_NOME="${GIT_NOME:-github-actions[bot]}"
GIT_EMAIL="${GIT_EMAIL:-github-actions[bot]@users.noreply.github.com}"

pasta_temporaria="$(mktemp -d)"
trap 'rm -rf "$pasta_temporaria"' EXIT


publicar_backup() {
  # Uso: publicar_backup arquivo_gz nome_do_arquivo_na_branch
  # Atualiza a branch backups: guarda os (QUANTIDADE_DE_BACKUPS - 1) arquivos
  # mais recentes que ja existiam, mais o novo. Devolve 0 se deu certo.
  #
  # Em vez de fazer checkout da branch backups (o que mexeria nos arquivos do
  # projeto), monta o conteudo direto no banco de objetos do git:
  #   git hash-object -w   guarda o arquivo novo e devolve o "endereco" dele
  #   git mktree           monta uma "pasta" a partir de uma lista de arquivos
  #   git commit-tree      cria um commit a partir dessa pasta
  # e depois empurra esse commit pra branch. Um commit so, sem historico:
  # o repositorio nao cresce a cada backup (mesmo padrao da branch data).
  local arquivo="$1"
  local nome="$2"
  local status entradas_antigas entradas_novas arvore commit

  consultar_branch backups
  status=$?
  if [ "$status" -eq 1 ]; then
    echo "Nao consegui perguntar ao GitHub sobre a branch backups." >&2
    return 1
  fi

  entradas_antigas=""
  if [ "$status" -eq 0 ]; then
    tentar_com_espera "baixar a branch backups" git fetch --quiet origin backups || return 1
    # cada linha do ls-tree: "100644 blob <endereco><TAB><nome do arquivo>".
    # Fica so com os arquivos de backup, ordenados do mais antigo pro mais
    # novo (o carimbo no nome faz a ordem alfabetica ser a ordem do tempo),
    # sem o que tiver o mesmo nome do novo.
    entradas_antigas=$(git ls-tree FETCH_HEAD \
      | awk -F'\t' -v novo="$nome" '$2 ~ /^radar-.*\.db\.gz$/ && $2 != novo {print}' \
      | sort -t$'\t' -k2 \
      | tail -n "$(( QUANTIDADE_DE_BACKUPS - 1 ))")
  fi

  local endereco_do_novo
  endereco_do_novo=$(git hash-object -w "$arquivo") || return 1

  entradas_novas=$(printf '%s\n%s\n' "$entradas_antigas" "100644 blob ${endereco_do_novo}"$'\t'"${nome}" | grep -v '^$')
  arvore=$(printf '%s\n' "$entradas_novas" | git mktree) || return 1
  commit=$(git commit-tree "$arvore" -m "Backup do banco (${nome}), mantem os ${QUANTIDADE_DE_BACKUPS} mais recentes") || return 1

  tentar_com_espera "enviar a branch backups" git push --quiet --force origin "${commit}:refs/heads/backups" || return 1
  echo "Backup enviado: ${nome} (a branch backups guarda os ${QUANTIDADE_DE_BACKUPS} mais recentes)."
  return 0
}


echo "== Conferencias antes de publicar =="

[ -f "$BANCO_LOCAL" ] || falhar "Publicacao BLOQUEADA: nao existe ${BANCO_LOCAL}. NAO publiquei nada."

"$PYTHON_BIN" "$VERIFICAR_BANCO" integridade "$BANCO_LOCAL" \
  || falhar "Publicacao BLOQUEADA: o banco local nao passou na verificacao de integridade. NAO publiquei nada."

quantidade_local=$("$PYTHON_BIN" "$VERIFICAR_BANCO" contar "$BANCO_LOCAL") \
  || falhar "Publicacao BLOQUEADA: nao consegui contar os editais do banco local. NAO publiquei nada."

argumentos=(pode-publicar --local "$quantidade_local")
if [ -f "$BANCO_REMOTO" ]; then
  tem_banco_remoto=true
  quantidade_remota=$("$PYTHON_BIN" "$VERIFICAR_BANCO" contar "$BANCO_REMOTO") \
    || falhar "Publicacao BLOQUEADA: nao consegui contar os editais da copia do banco remoto. NAO publiquei nada."
  argumentos+=(--remoto "$quantidade_remota")
  echo "Editais: ${quantidade_local} no banco local, ${quantidade_remota} no banco remoto."
else
  tem_banco_remoto=false
  echo "Editais: ${quantidade_local} no banco local, sem banco remoto (primeira publicacao)."
  [ "$PERMITIR_INICIO_DO_ZERO" = "true" ] \
    || falhar "Publicacao BLOQUEADA: nao ha banco remoto de referencia e o input permitir_inicio_do_zero esta desligado. NAO publiquei nada."
fi

if [ "$PERMITIR_REDUCAO_DO_BANCO" = "true" ]; then
  argumentos+=(--permitir-reducao)
fi

"$PYTHON_BIN" "$VERIFICAR_BANCO" "${argumentos[@]}" \
  || falhar "Publicacao BLOQUEADA pelas conferencias acima. NAO publiquei nada. Se a reducao for de proposito, rode manualmente com o input permitir_reducao_do_banco ligado."

git config user.name "$GIT_NOME"
git config user.email "$GIT_EMAIL"

if [ "$tem_banco_remoto" = true ]; then
  echo "== Backup do banco que sera sobrescrito =="
  carimbo="${CARIMBO_BACKUP:-$(date -u +%Y%m%d-%H%M%S)}"
  nome_do_backup="radar-${carimbo}.db.gz"
  arquivo_do_backup="${pasta_temporaria}/${nome_do_backup}"

  # gzip -c escreve o resultado na saida (aqui, no arquivo) e mantem o original.
  gzip -c "$BANCO_REMOTO" > "$arquivo_do_backup" \
    || falhar "Nao consegui compactar o backup. NAO publiquei nada."
  gzip -t "$arquivo_do_backup" \
    || falhar "O backup compactado esta com defeito. NAO publiquei nada."

  publicar_backup "$arquivo_do_backup" "$nome_do_backup" \
    || falhar "Nao consegui enviar o backup. Por seguranca, NAO publiquei o banco novo."
else
  echo "Sem banco remoto anterior: nao ha o que guardar de backup."
fi

echo "== Publicando o banco na branch data =="
git checkout -q -B data
git add -f "$BANCO_LOCAL"
git commit -q --allow-empty -m "Atualiza banco de editais ($(date -u +'%d/%m/%Y %H:%M UTC'))"

tentar_com_espera "enviar a branch data" git push --quiet --force origin data \
  || falhar "Nao consegui publicar a branch data depois das tentativas. O banco anterior continua intacto na branch data e o backup dele esta na branch backups."

# Confere que o GitHub ficou mesmo com o commit que acabamos de criar.
sha_local=$(git rev-parse HEAD)
sha_remoto=$(git ls-remote origin refs/heads/data | cut -f1)
if [ -n "$sha_remoto" ] && [ "$sha_remoto" != "$sha_local" ]; then
  falhar "O push parecia ter dado certo, mas a branch data no GitHub (${sha_remoto}) nao e o commit enviado (${sha_local})."
fi

echo "Banco publicado na branch data: ${quantidade_local} editais."
exit 0
