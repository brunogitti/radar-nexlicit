"""
Ferramenta de linha de comando usada pelos scripts em shell do workflow
(restaurar_banco.sh e publicar_banco.sh). Ela so repassa o pedido pras
funcoes de captura/banco.py (que e onde a logica mora e e testada) e
traduz o resultado em codigo de saida: 0 = tudo bem, 1 = problema.

Uso:
    python .github/scripts/verificar_banco.py integridade dados/radar.db
    python .github/scripts/verificar_banco.py contar dados/radar.db
    python .github/scripts/verificar_banco.py pode-publicar --local 105 --remoto 100
    python .github/scripts/verificar_banco.py pode-publicar --local 90 --remoto 100 --permitir-reducao
"""

import argparse
import sys
from pathlib import Path

# este arquivo esta em .github/scripts/, entao a raiz do projeto fica duas
# pastas acima. Sem isso o Python nao encontraria o pacote "captura".
RAIZ_DO_PROJETO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ_DO_PROJETO))

from captura import banco


def main():
    parser = argparse.ArgumentParser(description="Conferencias do arquivo de banco do Radar.")
    subcomandos = parser.add_subparsers(dest="comando", required=True)

    integridade = subcomandos.add_parser("integridade", help="o arquivo e um banco inteiro, com a tabela editais?")
    integridade.add_argument("caminho")

    contar = subcomandos.add_parser("contar", help="imprime quantos editais o banco tem")
    contar.add_argument("caminho")

    pode_publicar = subcomandos.add_parser("pode-publicar", help="o banco local pode ser publicado por cima do remoto?")
    pode_publicar.add_argument("--local", type=int, required=True, help="quantos editais o banco local tem")
    pode_publicar.add_argument("--remoto", type=int, default=None, help="quantos editais o banco remoto tem (omita se ainda nao existe)")
    pode_publicar.add_argument("--permitir-reducao", action="store_true", help="libera um banco local menor que o remoto")

    argumentos = parser.parse_args()

    if argumentos.comando == "integridade":
        esta_ok, motivo = banco.verificar_integridade(argumentos.caminho)
        if esta_ok:
            print(f"Banco inteiro: {argumentos.caminho}")
            return 0
        print(f"Banco com problema ({argumentos.caminho}): {motivo}", file=sys.stderr)
        return 1

    if argumentos.comando == "contar":
        try:
            print(banco.contar_editais(argumentos.caminho))
        except Exception as erro:
            print(f"Nao consegui contar os editais de {argumentos.caminho}: {erro}", file=sys.stderr)
            return 1
        return 0

    pode, motivo = banco.decidir_se_pode_publicar(
        argumentos.local, argumentos.remoto, permitir_reducao=argumentos.permitir_reducao
    )
    print(motivo, file=sys.stdout if pode else sys.stderr)
    return 0 if pode else 1


if __name__ == "__main__":
    sys.exit(main())
