# Assistente da Empório da Música

Assistente de atendimento em Python para consultar produtos, preços, estoque,
promoções, pedidos e políticas de uma loja fictícia de instrumentos musicais.

## Arquitetura

O projeto utiliza **Clean Architecture em uma única aplicação Python**, com
separação entre regras comerciais, casos de uso, integrações e interface.
Um agente de IA utiliza ferramentas para consultar os dados e as políticas
da loja. Cálculos e regras comerciais são executados em Python.

Essa arquitetura foi escolhida para:

- Testar consultas e regras sem depender de chamadas ao modelo de IA.
- Permitir trocar o provedor de IA, o armazenamento ou a interface sem alterar
  as regras comerciais.
- Facilitar a revisão e a implementação de cada funcionalidade em pequenas etapas.

A aplicação permanece em um único processo para simplificar a execução e o
desenvolvimento. As abstrações serão adicionadas conforme houver necessidade,
mantendo a estrutura proporcional ao tamanho do projeto.

## Tratamento dos dados

Os CSVs são preservados como fonte original. Antes da importação para SQLite,
validamos campos obrigatórios, tipos, identificadores duplicados e referências
entre tabelas.

SQLite foi escolhido para facilitar filtros e consultas entre produtos,
categorias, promoções e pedidos, sem precisar de um servidor de banco de dados.
O agente acessará essas informações por ferramentas de consulta.

Valores monetários são tratados com `Decimal` e armazenados em centavos inteiros
para evitar imprecisões. A importação usa uma transação para preservar o banco
anterior caso ocorra uma falha. O banco é gerado localmente e fica fora do Git,
pois pode ser recriado a partir dos CSVs.

## Regras de pagamento

Os cálculos são feitos em Python com `Decimal`. Promoções não acumulam entre si
nem com o desconto de 5% no PIX. Havendo várias promoções ativas para um produto,
adotamos a de maior desconto; em empate, a de menor identificador.

Para parcelamento, priorizamos a seção específica 3.1 do manual sobre a tabela
geral. Interpretamos a ressalva de R$ 50 como parcela mínima para 2 a 3 vezes.
De 4 a 6 vezes, o mínimo é R$ 80; de 7 a 12, R$ 100. Pagamento em uma vez não
tem esse mínimo. Centavos restantes são distribuídos nas primeiras parcelas,
preservando o total, e descontos são arredondados para centavos com `ROUND_HALF_UP`.

As condições calculadas são para uma unidade disponível, sem frete e com uma
única forma de pagamento. Produtos indisponíveis não recebem uma oferta de
pagamento. Simulação de carrinho e pagamento combinado ficam fora desta etapa.
