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
