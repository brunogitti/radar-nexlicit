#!/usr/bin/env bash
# Funcoes e variaveis compartilhadas pelos scripts restaurar_banco.sh e
# publicar_banco.sh. Este arquivo nao faz nada sozinho: os outros dois o
# carregam com "source" (que significa "execute o conteudo desse arquivo
# aqui dentro, como se estivesse escrito neste script").
#
# Por que shell e nao Python: tudo aqui e conversa com o git (baixar uma
# branch, empurrar uma branch), que e o que o workflow ja fazia em shell. A
# parte que precisa de logica de verdade (o banco esta inteiro? pode
# publicar?) mora em captura/banco.py e e testada com pytest.

RAIZ_DO_REPOSITORIO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
VERIFICAR_BANCO="$RAIZ_DO_REPOSITORIO/.github/scripts/verificar_banco.py"

# O banco com que a captura trabalha.
BANCO_LOCAL="dados/radar.db"

# Copia do banco exatamente como estava na branch data quando este job
# comecou. Serve de referencia pra comparar antes de publicar e vira o
# backup. Fica na pasta dados/, que o git ignora (nunca vai pra commit).
BANCO_REMOTO="dados/radar_remoto.db"

# Esperas, em segundos, entre uma tentativa e outra de uma operacao de rede.
# Sao 3 esperas, entao 4 tentativas no total. Os testes trocam isso por
# "0 0 0" pra nao esperar de verdade.
ESPERAS_ENTRE_TENTATIVAS="${ESPERAS_ENTRE_TENTATIVAS:-10 30 60}"


falhar() {
  # Mostra o erro e encerra o script inteiro com codigo 1 (o GitHub Actions
  # marca o passo como falho e avisa por e-mail).
  echo "ERRO: $*" >&2
  exit 1
}


tentar_com_espera() {
  # Uso: tentar_com_espera "descricao do que esta fazendo" comando arg1 arg2...
  # Roda o comando. Se falhar, espera (10 s, depois 30 s, depois 60 s) e
  # tenta de novo. Devolve 0 se alguma tentativa deu certo e 1 se todas
  # falharam.
  local descricao="$1"
  shift
  local esperas=($ESPERAS_ENTRE_TENTATIVAS)
  local total_de_tentativas=$(( ${#esperas[@]} + 1 ))
  local tentativa

  for (( tentativa = 1; tentativa <= total_de_tentativas; tentativa++ )); do
    if "$@"; then
      return 0
    fi
    if [ "$tentativa" -lt "$total_de_tentativas" ]; then
      local espera="${esperas[$(( tentativa - 1 ))]}"
      echo "Falhou (${descricao}), tentativa ${tentativa}/${total_de_tentativas}. Tentando de novo em ${espera}s..."
      sleep "$espera"
    fi
  done

  echo "Falhou de vez (${descricao}) depois de ${total_de_tentativas} tentativas." >&2
  return 1
}


consultar_branch() {
  # Uso: consultar_branch nome_da_branch
  # Pergunta ao GitHub se a branch existe, SEM baixar nada. Devolve:
  #   0 = a branch existe
  #   2 = a branch NAO existe (resposta clara do GitHub)
  #   1 = nao deu pra saber (erro de rede, GitHub fora do ar), mesmo
  #       depois de todas as tentativas
  # Essa diferenca e o coracao da blindagem: "nao existe" e "nao consegui
  # perguntar" sao coisas completamente diferentes, e tratar as duas
  # igual foi o que permitia apagar o banco por engano.
  local nome="$1"
  local esperas=($ESPERAS_ENTRE_TENTATIVAS)
  local total_de_tentativas=$(( ${#esperas[@]} + 1 ))
  local tentativa codigo

  for (( tentativa = 1; tentativa <= total_de_tentativas; tentativa++ )); do
    git ls-remote --exit-code --heads origin "refs/heads/${nome}" > /dev/null 2>&1
    codigo=$?
    if [ "$codigo" -eq 0 ] || [ "$codigo" -eq 2 ]; then
      return "$codigo"
    fi
    if [ "$tentativa" -lt "$total_de_tentativas" ]; then
      local espera="${esperas[$(( tentativa - 1 ))]}"
      echo "Nao consegui perguntar ao GitHub sobre a branch ${nome}, tentativa ${tentativa}/${total_de_tentativas}. Tentando de novo em ${espera}s..."
      sleep "$espera"
    fi
  done

  return 1
}
