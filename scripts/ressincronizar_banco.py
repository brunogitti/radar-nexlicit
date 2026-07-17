"""
Script auxiliar (roda sob demanda, nao faz parte da captura diaria).

Reavalia TODO edital ja salvo no banco contra o config/keywords.yaml
ATUAL, e corrige o segmento de quem estiver desatualizado (por exemplo,
depois que uma regra foi ajustada porque estava gerando falso positivo).
Nao apaga nenhuma linha, so corrige a coluna segmentos de quem mudou.

Rode isso depois de qualquer ajuste no keywords.yaml, se quiser que os
editais que ja estao no banco reflitam a regra nova.

Como rodar (com o venv ja ativado):
    python scripts/ressincronizar_banco.py
"""

import sys
from datetime import datetime
from pathlib import Path

RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_DO_PROJETO))

from captura import banco, filtro
from captura.modelos import Edital


def _linha_para_edital(linha):
    """Reconstroi um Edital a partir de uma linha do banco, só com os
    campos que o filtro.avaliar_edital realmente usa (objeto e
    informacao_complementar). cnpj_orgao/ano_compra/sequencial_compra nao
    existem como colunas no banco, entao entram com um valor de
    preenchimento: o filtro nunca olha pra eles.
    """
    return Edital(
        numero_controle_pncp=linha["numero_controle_pncp"],
        cnpj_orgao="",
        ano_compra=0,
        sequencial_compra=0,
        orgao=linha["orgao"],
        municipio=linha["municipio"],
        uf=linha["uf"],
        codigo_ibge=linha["codigo_ibge"],
        modalidade=linha["modalidade"],
        objeto=linha["objeto"],
        situacao=linha["situacao"],
        data_encerramento_proposta=datetime.fromisoformat(linha["data_encerramento_proposta"]),
        informacao_complementar=linha["informacao_complementar"],
    )


def ressincronizar_banco():
    conexao = banco.conectar()
    config_keywords = filtro.carregar_keywords()
    linhas = banco.consultar_historico(conexao)

    total_atualizados = 0

    for linha in linhas:
        edital = _linha_para_edital(linha)
        segmentos_novos = filtro.avaliar_edital(edital, config_keywords)

        if segmentos_novos != linha["segmentos"]:
            segmentos_antigos = [m["segmento"] for m in linha["segmentos"]]
            segmentos_atuais = [m["segmento"] for m in segmentos_novos]
            print(f"- {linha['numero_controle_pncp']}: {segmentos_antigos} -> {segmentos_atuais}")

            banco.atualizar_segmentos(conexao, linha["numero_controle_pncp"], segmentos_novos)
            total_atualizados += 1

    conexao.close()

    print(f"\n{total_atualizados} de {len(linhas)} edital(is) tiveram o segmento corrigido.")


if __name__ == "__main__":
    ressincronizar_banco()
