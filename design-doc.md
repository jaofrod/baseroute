📄 Design Doc: Agente Autônomo de Oportunidades On-Chain (DeFAI)

## 1. O QUE (Visão Geral do Sistema)
O sistema é um robô autônomo backend (Python) composto por três motores principais:

    - Ouvinte (Analytics/Indexer)
      Fica lendo a blockchain em tempo real via Alchemy para encontrar gatilhos (ex: variação de juros, grandes movimentações).

    - Cérebro (LLM/Engine de Decisão)
      Recebe o contexto do Ouvinte, analisa o risco/recompensa com base em um prompt predefinido e decide se há uma oportunidade lucrativa.

    - Mão (Executor/Signer)
      Recebe a ordem do Cérebro, formata a transação, assina com uma chave privada segura e envia para a blockchain.


## 2. COMO (A Arquitetura e o Tech Stack)
Tech Stack

    - Linguagem: Python 3.11+
    - Comunicação Web3: web3.py (Para interagir com a rede) + Alchemy (Provedor de RPC).
    - Inteligência: Anthropic (Claude 3.5 Sonnet) via API.
    - Orquestração de Agente: LangChain ou framework nativo simples (Function Calling).

O Fluxo de Execução (Loop Principal)

    - Cron/Worker: A cada X minutos, o script bate no Alchemy e pega os dados da rede (ex: Saldo atual, taxas de juros no Aave).
    - State Builder: O Python formata esses dados em um JSON estruturado.
    - Prompting: O JSON é enviado para o LLM junto com as "Tools" disponíveis (ex: sacar, depositar, fazer_swap).
    - Decisão: O LLM responde com a Tool a ser chamada e os parâmetros (ex: do_swap(token="USDC", amount=50)).
    - Validação Determinística: O Python intercepta a decisão e passa por um "Firewall" (regras de segurança hardcoded).
    - Broadcast: A transação é assinada criptograficamente e enviada via w3.eth.send_raw_transaction.

## 3. Mitigar possíveis problemas
    - Vazamento da Chave Privada
      Nunca deixar a chave no disco. Usra gerenciador de segredos em nuvem.

    - Alucinação da IA
      Guardrails determinísticos: O LLM sugere, o Python aprova.
      Regras em código rígido: if tx_acmount > MAX_LIMIT: abort().
      A IA NUNCA tem a chave, só o Python tem.

    - Rate Limits da API (Alchemy)
      O Python deve sempre consultar o w3.eth.gas_price atual.
      A IA só aprova o trade se: Lucro Esperado > (Custo do Gas * 1.5)

    - Transações Presas
      Sistema de monitoramento de Nonce. Se a TX não for confirmada em 3 blocos,
      o sistema recria a TX com a mesma identificação (nonce) e um gas maior para sobrescrevê-la

obs: "gas" significa a taxa medida em GWEI(fração pequena de ETH), que usuários pagam aos validadores
     para processas transações o executar contratos inteligentes na rede Ethereum.
     Gas Price maior: prioriza a transação
     Gas Price menor: torna a TX mais barata, porém mais lenta
     Quando a rede está congestionada, o gas price aumenta


## 4. QUANDO (Roadmap de Implementação Rápida)
Para tirar do papel sem frustração, vamos fatiar o elefante em 4 fases:

    Fase 1: "O Olho" FEITO

        Meta: Conectar via Alchemy, ler saldos, ler taxas de juros de contratos, e criar o JSON de estado. Nenhuma IA ainda. Nenhuma transação financeira.

    Fase 2: "O Paper Trading"

        Meta: Plugar o LLM. Alimentar os dados para ele e pedir decisões. O Python NÃO executa a transação, apenas dá um print() do que a IA decidiu para validarmos se ela não é "burra".

    Fase 3: "O Sandbox"

        Meta: Criar uma carteira em uma Testnet (Rede de testes onde o dinheiro é de mentira, tipo Sepolia ou Base Sepolia). Deixar o robô rodar solto lá por uns dias enviando transações falsas.

    Fase 4: "Skin in the Game"

        Meta: Deploy na Mainnet (Rede principal) com dinheiro real, mas com fundos super limitados (ex: colocar apenas 20 dólares de USDC na carteira do robô) para ver a roda girar de verdade.


## Regras de ouro da proteção
A chave privada deve ser MUUUITO PRIVADA.
 - Nunca printar ela em lado nenhum.
 - Nunca salvar num JSON
 - Nunca encostar no github, mesmo num repo privado, se chegar a tocar no github a chave já está comprometida
