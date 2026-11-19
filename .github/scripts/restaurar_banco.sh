#!/usr/bin/env bash
# Restaura o banco (dados/radar.db) a partir da branch "data" antes da
# captura. Regra de ouro: NUNCA apagar nada e NUNCA seguir adiante com um
# banco duvidoso. Na duvida, o job falha e o GitHub avisa por e-mail.
#
# O que o script decide:
#   - branch data existe        -> baixa, confere a integridade, usa o banco
#   - nao deu pra perguntar     -> tenta 4 vezes (esperas de 10, 30, 60 s) e,
#                                  se nao der, FALHA (nao confunde "sem rede"
#                                  com "nao existe")
#   - data NAO existe e a branch backups TEM arquivos
#                               -> FALHA e pede restauracao manual. Isso
#                                  indica que o banco foi apagado; comecar do
#                                  zero agora jogaria fora o historico. Nem o
#                                  input permitir_inicio_do_zero libera isso.
#   - data NAO existe e backups tambem nao tem nada
#                               -> so comeca do zero se o input manual
#                                  permitir_inicio_do_zero estiver LIGADO
#                                  (variavel PERMITIR_INICIO_DO_ZERO=true).
#                                  Desligado por padrao.
#
# Este script nunca roda "rm" no banco de verdade. O unico arquivo que ele
# apaga e a copia de referencia (radar_remoto.db) deixada por uma execucao
# anterior, que e recriada logo abaixo.
#
# Variaveis de ambiente que ele le:
#   PERMITIR_INICIO_DO_ZERO   "true" libera o inicio do zero (padrao: false)
#   PYTHON_BIN                comando do Python (padrao: python)
#   ESPERAS_ENTRE_TENTATIVAS  esperas do retry (padrao: "10 30 60")

set -uo pipefail
# shellcheck source=comum.sh
source "$(dirname "${BASH_SOURCE[0]}")/comum.sh"
cd "$RAIZ_DO_REPOSITORIO" || exit 1

PERMITIR_INICIO_DO_ZERO="${PERMITIR_INICIO_DO_ZERO:-false}"

mkdir -p dados
rm -f "$BANCO_REMOTO"

echo "== Restaurando o banco da branch data =="

# 1) Pergunta ao GitHub quais das duas branches existem (sem baixar nada).
consultar_branch data
status_da_data=$?
if [ "$status_da_data" -eq 1 ]; then
  falhar "Nao consegui falar com o GitHub pra saber se a branch data existe. NAO apaguei nada e NAO vou seguir adiante. Rode o workflow de novo mais tarde."
fi

consultar_branch backups
status_dos_backups=$?
if [ "$status_dos_backups" -eq 1 ]; then
  falhar "Nao consegui falar com o GitHub pra saber se a branch backups existe. NAO apaguei nada e NAO vou seguir adiante. Rode o workflow de novo mais tarde."
fi

# 2) Caso normal: a branch data existe.
if [ "$status_da_data" -eq 0 ]; then
  tentar_com_espera "baixar a branch data" git fetch --quiet origin data \
    || falhar "A branch data existe, mas nao consegui baixar. NAO apaguei nada e NAO vou seguir adiante."

  if ! git show "FETCH_HEAD:${BANCO_LOCAL}" > "$BANCO_REMOTO" 2> /dev/null; then
    rm -f "$BANCO_REMOTO"
    falhar "A branch data existe, mas nao tem o arquivo ${BANCO_LOCAL}. Isso nao e uma primeira execucao: restaure manualmente (veja docs/operacao-banco.md). NAO apaguei nada e NAO vou seguir adiante."
  fi

  "$PYTHON_BIN" "$VERIFICAR_BANCO" integridade "$BANCO_REMOTO" \
    || falhar "O banco da branch data nao passou na verificacao de integridade. NAO vou usar esse banco nem publicar nada. Restaure manualmente de um backup (veja docs/operacao-banco.md)."

  quantidade=$("$PYTHON_BIN" "$VERIFICAR_BANCO" contar "$BANCO_REMOTO") \
    || falhar "Nao consegui contar os editais do banco da branch data."

  cp "$BANCO_REMOTO" "$BANCO_LOCAL" || falhar "Nao consegui copiar o banco restaurado para ${BANCO_LOCAL}."
  echo "Banco restaurado da branch data: ${quantidade} editais."
  exit 0
fi

# 3) A branch data NAO existe. Antes de pensar em comecar do zero, ve se a
#    branch backups tem arquivos: se tem, o banco ja existiu e foi apagado.
if [ "$status_dos_backups" -eq 0 ]; then
  tentar_com_espera "baixar a branch backups" git fetch --quiet origin backups \
    || falhar "Nao consegui baixar a branch backups pra conferir se ha backups. NAO vou seguir adiante."

  quantidade_de_backups=$(git ls-tree --name-only FETCH_HEAD | grep -c '\.db\.gz$' || true)
  if [ "$quantidade_de_backups" -gt 0 ]; then
    falhar "A branch data NAO existe, mas a branch backups tem ${quantidade_de_backups} arquivo(s) de backup. Isso indica que o banco foi apagado. NAO vou comecar do zero (nem com permitir_inicio_do_zero ligado). Restauracao MANUAL necessaria: veja docs/operacao-banco.md."
  fi
fi

# 4) Nem data nem backups: so uma primeira execucao de verdade, e so com o
#    input manual ligado.
if [ "$PERMITIR_INICIO_DO_ZERO" != "true" ]; then
  falhar "Nao existe banco salvo (nao ha branch data nem backups). Se for realmente a primeira execucao, rode o workflow manualmente com o input permitir_inicio_do_zero LIGADO. Do contrario, algo apagou o banco: NAO comecei do zero."
fi

if [ -e "$BANCO_LOCAL" ]; then
  falhar "Inicio do zero autorizado, mas ja existe um ${BANCO_LOCAL} neste ambiente, o que nao deveria acontecer num ambiente limpo. Nao vou seguir adiante pra nao misturar bancos."
fi

echo "Inicio do zero AUTORIZADO (permitir_inicio_do_zero ligado): nao ha branch data nem backups. A captura vai criar um banco novo."
exit 0
