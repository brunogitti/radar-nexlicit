"""
Script auxiliar (roda sob demanda, nao faz parte da captura diaria).

Busca os itens de todo edital ja salvo no banco que AINDA NAO tem item
salvo em itens_edital, e preenche a tabela nova (Tarefa A.1/A.2). Serve
pros editais que ja estavam no banco antes da Tarefa A.2 existir: eles tem
beneficios_itens (o resumo do selo ME/EPP), mas nunca tiveram o item
detalhado guardado.

Nao mexe em nada que ja existe (situacao, segmentos, etc.), so acrescenta
itens. Seguro rodar mais de uma vez: qualquer edital que ja tenha item
salvo e pulado, e banco.salvar_itens faz upsert pela chave composta
(numero_controle_pncp + numero_item) mesmo assim, entao nunca duplica.

cnpj/ano/sequencial nao existem como colunas separadas no banco (mesma
limitacao ja registrada em ressincronizar_banco.py), entao esse script
extrai os tres de dentro do link_pncp que ja esta salvo, no formato
https://pncp.gov.br/app/editais/{cnpj}/{ano}/{sequencial} (gerado assim
desde a Tarefa 1.0, ver pncp_client._montar_edital).

Como rodar (com o venv ja ativado):
    python scripts/backfill_itens.py
"""

import sys
import time
from pathlib import Path

RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_DO_PROJETO))

from captura import banco, pncp_client

# Mesma pausa que main.py usa entre municipios: evita bater no limite de
# requisicoes do PNCP (nao documentado, mas real na pratica).
PAUSA_ENTRE_CHAMADAS_SEGUNDOS = 1.5


def _extrair_cnpj_ano_sequencial(link_pncp):
    """Tira cnpj, ano e sequencial de dentro do link_pncp ja salvo. Os tres
    ultimos pedacos da URL, separados por "/", sao exatamente o que o
    endpoint de itens precisa.
    """
    cnpj, ano, sequencial = link_pncp.rstrip("/").split("/")[-3:]
    return cnpj, int(ano), int(sequencial)


def preencher_itens_faltantes():
    conexao = banco.conectar()
    linhas = banco.consultar_historico(conexao)

    total_chamadas = 0
    total_com_itens_novos = 0

    for linha in linhas:
        if banco.buscar_itens_do_edital(conexao, linha["numero_controle_pncp"]):
            continue  # ja tem item salvo, nao busca de novo

        if total_chamadas > 0:
            time.sleep(PAUSA_ENTRE_CHAMADAS_SEGUNDOS)
        total_chamadas += 1

        cnpj, ano, sequencial = _extrair_cnpj_ano_sequencial(linha["link_pncp"])
        itens = pncp_client.buscar_itens_da_compra(cnpj, ano, sequencial)

        if itens is None:
            print(f"- {linha['numero_controle_pncp']}: falhou ao buscar itens, pulando")
            continue

        banco.salvar_itens(conexao, linha["numero_controle_pncp"], itens)
        total_com_itens_novos += 1
        print(f"- {linha['numero_controle_pncp']}: {len(itens)} item(ns) salvo(s)")

    conexao.close()
    print(f"\n{total_com_itens_novos} de {total_chamadas} edital(is) processado(s) ganharam itens novos.")


if __name__ == "__main__":
    preencher_itens_faltantes()
