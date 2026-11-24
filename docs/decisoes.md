# Decisões do Radar NexLicit v2

Registro das decisões já tomadas, para não reabrir a mesma discussão. Atualizar sempre que uma decisão mudar. Última atualização: 19/11/2026.

## 1. Modalidades de contratação

Fonte: respostas reais da API do PNCP em 19/11/2026 (campos `modalidadeId` e `modalidadeNome`). A lista fica num arquivo de configuração (Fase 1), não escrita no código, então dá para mudar sem mexer em Python.

| Código | Nome na API | Decisão |
|---|---|---|
| 4 | Concorrência - Eletrônica | Incluir |
| 5 | Concorrência - Presencial | Incluir |
| 6 | Pregão - Eletrônico | Incluir |
| 7 | Pregão - Presencial | Incluir |
| 8 | Dispensa | Incluir |
| 9 | Inexigibilidade | Incluir (só quando tiver prazo de proposta, ou como contratação direta compacta) |
| 12 | Credenciamento | Incluir |
| 1 | Leilão - Eletrônico | Excluir |
| 13 | Leilão - Presencial | Excluir |
| 3 | Concurso | Excluir |
| 10 | Manifestação de Interesse | Excluir |
| 11 | Pré-qualificação | Excluir |
| 2 | Sem nenhum registro em 19/11 (nome não confirmado, esperado: Diálogo competitivo) | Excluir |

Pendências para conferir na Fase 1:
- Código 14: sem nenhum registro em 19/11, decisão em aberto.
- "Pregão - Eletrônico Internacional": existe 1 edital com esse nome no banco, o código dele não foi conferido.

## 2. Tamanhos de página

| Endpoint | Mínimo | Máximo | Usamos |
|---|---|---|---|
| Consulta (`/proposta`, `/publicacao`, `/atualizacao`) | 10 | 50 (Swagger oficial) | 50 (`TAMANHO_PAGINA` em `pncp_client.py`) |
| Itens (`/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens`) | não documentado | não documentado | 500 |

Sobre os itens, que não estão no Swagger:
- Sem nenhum parâmetro, a API devolve só 10 itens (confirmado em 3 compras reais). Foi isso que cortou os itens no banco.
- Com `tamanhoPagina=500` vieram todos os itens nas medições de 19/11 (120 compras, a maior com 359 itens), sem precisar de segunda página. O valor 1000 também foi aceito.
- Regra adotada: pedir 500 por página e pedir a página seguinte até vir página vazia ou 204 (nunca parar por "página menor que o pedido"). O máximo real do endpoint continua sem documentação.

## 3. Regras técnicas do banco (decididas em 19/11/2026)

- Itens completos só para editais classificados em um segmento principal.
- Editais classificados só como prospecção: só os itens que casaram, mais a contagem total de itens.
- Editais não classificados: nenhum item.
- Itens de editais encerrados há mais de 60 dias são apagados.
- Os contadores de termos não classificados são calculados na ingestão (no momento em que o edital entra), não depois.
- Modo sombra (Fase 7): registrar o volume real do e-mail principal (quantidade de editais e tamanho em KB, por execução) para decidir se ele precisa ser dividido.
- Ordem das fases: a Fase 0.5 vem antes da Fase 1. Ela tem duas partes: paginação completa dos itens (com reprocessamento dos editais abertos que têm exatamente 10 itens) e blindagem do workflow do banco.

## 4. Para a Fase 1 (decidido em 19/11/2026)

- **Edital excluído no PNCP (HTTP 410, "A contratação informada foi excluída"):** tratar como edital excluído. Ele deve sair das listas de abertos e do e-mail.
- **Painel:** deixar de filtrar só pelo prazo da proposta. Edital excluído (e, a avaliar, anulado ou suspenso) não pode aparecer como aberto.
- **Motivo:** o edital 46599833000111-1-000218/2026 foi excluído pelo órgão depois de o Radar capturá-lo. Hoje ele continua no banco como "Divulgada no PNCP" e aparece como aberto no painel até 02/12/2026, porque o Radar não percebe quando um edital deixa de aparecer na lista de propostas abertas.
- **Hospedagem:** decidir se o repositório continua público ou vira privado, considerando a cota de minutos do GitHub Actions e o acesso do painel no Streamlit Community Cloud.

## 5. Fuso e edital excluído (implementado em 23 e 24/11/2026)

**Fuso do prazo.** `dataEncerramentoProposta` vem em horário de Brasília, sem marcação de fuso (conferido no portal do PNCP com o edital 49576416000141/2026/359: API 09:00, portal 09:00). O código passou a comparar o prazo com `captura/relogio.py` (`agora_em_brasilia`, `hoje_em_brasilia`, `dias_ate_o_prazo`), não com `datetime.now()`, porque o relógio do GitHub Actions e do Streamlit Cloud é UTC. Os carimbos `visto_em` e `atualizado_em` continuam com o relógio de onde a captura rodou, para não criar um salto de 3 horas no histórico. `tzdata` está fixado no `requirements.txt` porque o Windows não traz o banco de fusos.

**Edital excluído e situação diferente de "Divulgada".**
- URL que revela o estado de uma compra: `GET https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}`. 200 com `situacaoCompraNome`, ou 410 quando o PNCP excluiu o edital. O 410 não consta no Swagger, só existe testando. O mesmo caminho em `/api/pncp/v1/` responde 301.
- Medido em 23/11/2026 nos 74 editais abertos do banco: 72 normais, 1 excluído (410) e 1 suspenso (`situacaoCompraId` 4, "Suspensa"). A lista `/proposta` ainda devolve o suspenso, mas o cliente descarta tudo que não é "Divulgada", então o banco nunca percebia a mudança. Os nomes de revogada e anulada não aparecem no Swagger nem em nenhuma amostra, por isso o código grava o texto que a API devolve e nunca compara com números de código.
- Coluna `excluido_em` em `editais`, criada por `ALTER TABLE` idempotente em `banco.conectar`. A linha nunca é apagada (a conferência de publicação exige contagem maior ou igual).
- Reconciliação (`main.reconciliar_editais_sumidos`): depois de salvar, consulta uma vez cada edital do banco que ainda parece aberto (prazo entre agora e o fim da janela de dias, sem `excluido_em`) e que não veio na lista. 410 grava `excluido_em`; outra situação grava a situação nova; "Divulgada" não muda nada; falha de consulta não muda nada. Não roda com `--municipio` nem com `--dry-run`, e um erro inesperado nela não derruba a captura.
- Painel: editais com `excluido_em` ficam de fora de tudo (contagens e lista). Situação diferente de "Divulgada" aparece num selo no card e o edital não conta como "Encerra em breve".
- Limite conhecido: um edital já enviado por e-mail não pode ser "retirado" depois, e o aviso de que ele foi suspenso ou excluído aparece só no painel.

## 6. E-mail semanal "Radar ativo" e registro de execuções (implementado em 24/11/2026)

- **Para quê:** se o e-mail de segunda-feira não chegar, a captura quebrou (token vencido, workflow travado). É um aviso por ausência. Limite: prova que a captura rodou, não que o disparo externo está ativo.
- **Quando sai:** na primeira captura completa de segunda-feira a partir das 05h de Brasília (`entrega/batimento.deve_enviar`). Uma captura de madrugada de segunda não gasta o envio. No máximo um por dia. Se a segunda passa sem captura bem-sucedida, não sai (a falta do e-mail é o sinal).
- **Controle de envio:** tabela chave-valor `metadados` no banco (chave `batimento_enviado_em`), porque o banco é a única coisa que o workflow publica entre execuções. E-mail que falha não marca como enviado, então a próxima captura de segunda tenta de novo.
- **Registro de execuções:** tabela `execucoes`, uma linha por captura completa e de verdade (nunca em `--dry-run` nem com `--municipio`): horário de Brasília, resultado (`completa` ou `com_falhas`), municípios consultados e com falha, editais na lista e novos ou atualizados. Captura em que todos os municípios falharam não é registrada. Serve ao resumo semanal e já adianta o registro de execuções da coleta v2.
- **Conteúdo:** só números, sem lista de editais. Primeiro o que mostra se o Radar está vivo (data e hora da última captura bem-sucedida, execuções nos últimos 7 dias, quantas com municípios de fora, maior intervalo entre duas capturas na semana), depois o que ele encontrou (editais abertos, novos na semana). O maior intervalo existe porque a última captura de um e-mail de segunda é sempre a que acabou de rodar, então sozinha não distingue "sem novidade" de "Radar parado".
- **Destinatário:** o mesmo endereço que a captura já usa (`--enviar-email`, secret `EMAIL_DESTINATARIO`).
- `capturar_editais` passou a devolver também a lista de municípios que falharam.
