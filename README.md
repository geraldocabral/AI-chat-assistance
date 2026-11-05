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

## Consulta às políticas

O manual é extraído com `pypdf` e organizado por suas dez seções principais,
mantendo regras e exceções juntas, com indicação do arquivo e das páginas.
A busca textual ignora caixa e acentos, considera alguns termos equivalentes
e dá maior peso a termos dos títulos e menos frequentes no documento.

Essa abordagem foi escolhida pelo tamanho reduzido do manual e por funcionar
localmente, sem custo de API ou banco vetorial. A busca depende das palavras
utilizadas e pode não reconhecer todas as formas de uma pergunta. Seus resultados
são trechos de referência; a interpretação e a resposta serão integradas ao agente.

## Consulta de pedidos

Cada consulta exige o cliente associado à sessão e filtra o pedido por esse
identificador no banco. Um pedido de outro cliente tem o mesmo retorno de um
pedido inexistente, e os resultados não incluem nome, telefone ou e-mail.
O identificador do cliente é fornecido pela aplicação, separado dos parâmetros
que o agente poderá receber na ferramenta.

Na demonstração, essa identidade será simulada; não existe autenticação real.
Em produção, ela precisaria vir de uma sessão autenticada. O total histórico é
preservado, e previsões de entrega não são tratadas como datas de recebimento.
Não há consulta a transportadoras nem alteração de pedidos.

## Provedor de IA

A integração usa a API do Gemini, com o modelo `gemini-3.5-flash-lite`
configurável por variável de ambiente. A escolha considera a oferta de cota
gratuita, o suporte a ferramentas e o acesso à chave pelo Google AI Studio.
Os limites efetivos dependem da conta e precisam ser conferidos antes da demonstração.

O adaptador traduz mensagens e ferramentas para a API, mantendo o restante da
aplicação independente do provedor. Usamos o endpoint de compatibilidade do Gemini
para manter o formato de mensagens e ferramentas. Há timeout, limite de saída e tratamento
de falhas de acesso, cota e respostas inválidas, sem repetição automática de
requisições. A chave é lida do ambiente e não deve ser versionada.

Referências: [compatibilidade da API](https://ai.google.dev/gemini-api/docs/openai),
[preços](https://ai.google.dev/gemini-api/docs/pricing)
e [limites](https://ai.google.dev/gemini-api/docs/rate-limits).
Uma conversa real de busca de catálogo foi validada com Gemini, incluindo a
chamada da ferramenta e a resposta baseada no SQLite. Os demais cenários ainda
precisam de avaliação real; testes simulados verificam o contrato da integração.

## Fluxo de atendimento

O agente recebe a mensagem, solicita ferramentas e usa seus resultados para
formular a resposta. Somente as cinco consultas implementadas são permitidas,
com validação local de parâmetros. Consultas de pedidos usam a identidade da
sessão, sem aceitar um cliente escolhido pelo modelo.

Cada mensagem permite até quatro chamadas ao modelo e oito chamadas de
ferramentas. O histórico mantém os seis últimos turnos completos em memória,
sem persistência entre reinicializações. Falhas e limites encerram o fluxo com
uma resposta de indisponibilidade, preservando um histórico válido.

As instruções definem persona, uso de fontes, escopo e tratamento de informações
ausentes. Essas instruções orientam o modelo, mas a aderência precisa ser
avaliada com conversas reais. Os testes automatizados verificam a orquestração
usando um modelo simulado. Logs registram duração, ferramentas e consumo de tokens
quando informado pelo provedor, sem conteúdo de mensagens ou resultados.

## Interface

A interface inicial é um chat no terminal. Essa escolha permite demonstrar o
atendimento e o contexto de conversa com poucas dependências. A sessão começa
anônima; um cliente de demonstração pode ser selecionado explicitamente na
inicialização, sem permitir troca de identidade por mensagem ao agente.

O chat permite reiniciar o histórico e encerrar o atendimento. A configuração
local pode ser carregada de `.env` com `python-dotenv`, preservando variáveis já
definidas no ambiente. O banco é gerado a partir dos CSVs somente se ainda não
existir; as execuções seguintes não reimportam os dados automaticamente.
