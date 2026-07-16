"""
Script auxiliar (roda uma vez, não faz parte da captura diária).

Le o config/municipios.csv, busca a lista oficial de municipios de cada UF
na API publica do IBGE, casa cada linha do CSV por nome (normalizado) + UF,
e preenche a coluna codigo_ibge que hoje esta vazia.

Municipio que nao achar correspondencia NAO e pulado em silencio: fica de
fora do CSV preenchido e aparece, explicitamente, na lista impressa no final.

Como rodar (com o venv ja ativado):
    python scripts/resolver_ibge.py
"""

import csv
import unicodedata
from pathlib import Path

import requests

CAMINHO_CSV = Path(__file__).resolve().parent.parent / "config" / "municipios.csv"
URL_IBGE = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"


def normalizar_nome(nome):
    """Deixa o nome minusculo e sem acento, para comparar 'Dolcinópolis' com 'dolcinopolis'.

    unicodedata.normalize('NFKD', nome) separa cada letra acentuada em duas
    partes: a letra normal e o acento como um caractere "combinante" a parte
    (ex.: 'ó' vira 'o' + acento). O laco abaixo entao descarta qualquer
    caractere que unicodedata.combining() reconhece como um desses acentos,
    sobrando so a letra sem acento.
    """
    nome = nome.strip().lower()
    nome_sem_acento = unicodedata.normalize("NFKD", nome)
    letras = [c for c in nome_sem_acento if not unicodedata.combining(c)]
    return "".join(letras)


def buscar_municipios_do_ibge(uf):
    """Busca todos os municipios de uma UF na API do IBGE.

    Devolve um dicionario {nome_normalizado: codigo_ibge}.
    """
    resposta = requests.get(URL_IBGE.format(uf=uf), timeout=15)
    resposta.raise_for_status()
    municipios = resposta.json()

    mapa = {}
    for municipio in municipios:
        nome_normalizado = normalizar_nome(municipio["nome"])
        mapa[nome_normalizado] = str(municipio["id"])
    return mapa


def resolver_codigos_ibge():
    with open(CAMINHO_CSV, newline="", encoding="utf-8") as arquivo:
        leitor = csv.DictReader(arquivo)
        colunas = leitor.fieldnames
        linhas = list(leitor)

    ufs_presentes = sorted({linha["uf"] for linha in linhas})
    print(f"UFs encontradas no municipios.csv: {', '.join(ufs_presentes)}")

    mapa_por_uf = {}
    for uf in ufs_presentes:
        print(f"Buscando municipios de {uf} na API do IBGE...")
        mapa_por_uf[uf] = buscar_municipios_do_ibge(uf)

    nao_casaram = []
    total_casou = 0

    for linha in linhas:
        nome_normalizado = normalizar_nome(linha["municipio"])
        mapa_da_uf = mapa_por_uf[linha["uf"]]

        if nome_normalizado in mapa_da_uf:
            linha["codigo_ibge"] = mapa_da_uf[nome_normalizado]
            total_casou += 1
        else:
            nao_casaram.append(linha["municipio"] + "/" + linha["uf"])

    with open(CAMINHO_CSV, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas)
        escritor.writeheader()
        escritor.writerows(linhas)

    print(f"\n{total_casou} de {len(linhas)} municipios casaram e tiveram o codigo_ibge preenchido.")

    if nao_casaram:
        print(f"\n{len(nao_casaram)} municipio(s) NAO casaram (ficaram sem codigo_ibge):")
        for nome_uf in nao_casaram:
            print(f"  - {nome_uf}")
    else:
        print("\nTodos os municipios casaram.")


if __name__ == "__main__":
    resolver_codigos_ibge()
