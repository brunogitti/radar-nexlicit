"""
Formato padrao de um edital dentro do projeto.

Todo modulo que devolve ou recebe um edital usa esta mesma "ficha": o
pncp_client.py monta um Edital a partir da resposta da API, o filtro.py le
os campos objeto/informacao_complementar para decidir o segmento, e o
main.py le tudo isso pra imprimir e salvar.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Edital:
    # numero_controle_pncp e o identificador unico do edital no PNCP.
    # Vai ser a chave usada na Camada 2 (banco de dados) pra saber se um
    # edital ja foi visto antes.
    numero_controle_pncp: str

    # Guardados separados (em vez de so dentro de numero_controle_pncp)
    # porque buscar_beneficios_da_compra (pncp_client.py) precisa dos tres
    # na hora de montar a URL do endpoint de itens. Tentar extrair de volta
    # a partir do texto do numero_controle_pncp seria fragil.
    cnpj_orgao: str
    ano_compra: int
    sequencial_compra: int

    orgao: str
    municipio: str
    uf: str
    codigo_ibge: str
    modalidade: str
    objeto: str
    situacao: str
    data_encerramento_proposta: datetime

    # Nem todo edital preenche esse campo na API (varias vezes vem vazio).
    # O filtro.py analisa objeto + informacao_complementar juntos, porque
    # o keywords.yaml pede os dois (campos_analisados).
    informacao_complementar: str | None = None

    # Nem todo edital tem valor estimado divulgado, por isso pode ser None
    # (o jeito do Python de dizer "esse valor nao existe", diferente de zero).
    valor_estimado: float | None = None

    link_sistema_origem: str | None = None
    link_pncp: str | None = None

    # None aqui significa "ainda nao verificamos o selo ME/EPP" (a chamada
    # extra ao endpoint de itens so acontece depois do filtro de palavra-chave,
    # na Tarefa 1.6). Quando verificado, guarda o texto cru que a API devolveu
    # em cada item (ex.: ["Sem beneficio"] ou ["Participacao exclusiva para
    # ME/EPP"]). A decisao de como transformar isso num selo na tela fica
    # pra Tarefa 1.6, com o Bruno.
    beneficios_itens: list | None = None

    # field(default_factory=list) existe porque uma lista e um valor
    # "mutavel": se eu escrevesse "segmentos: list = []" direto, todo Edital
    # criado sem informar segmentos passaria a COMPARTILHAR a mesma lista por
    # baixo dos panos, e alterar o segmento de um edital vazaria pros outros.
    # default_factory=list diz "toda vez que criar um Edital sem esse
    # argumento, crie uma lista nova e vazia", em vez de reaproveitar uma.
    segmentos: list = field(default_factory=list)
