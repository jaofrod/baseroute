# Flow de Lucro Detalhado: Yield Optimizer USDC na Base

## 1. Visao Geral da Estrategia

**O que o bot faz:** Monitora as taxas de rendimento (APY) de USDC no Aave V3 e Compound III na rede Base. Quando detecta que um protocolo paga significativamente mais que o outro, move o capital para lá.

**Por que isso funciona:**
- Protocolos DeFi competem por liquidez. Quando muita gente saca de um protocolo, a taxa sobe (menos oferta = juros maiores para atrair de volta). Quando muita gente deposita, a taxa cai.
- Essas flutuacoes criam janelas onde um protocolo paga 2x-5x mais que o outro.
- O bot captura essas janelas automaticamente.

**Analogia simples:** Imagine dois bancos lado a lado. O Banco A paga 3% e o Banco B paga 8%. Voce move seu dinheiro pro Banco B. Quando o Banco A subir pra 10% e o B cair pra 4%, voce volta. O bot faz isso 24/7 sem dormir.

---

## 2. Rede e Contratos

### Por que Base?
Base e uma Layer 2 (L2) do Ethereum. Isso significa que ela herda a seguranca do Ethereum, mas processa transacoes fora da chain principal, tornando-as muito mais baratas.

| Propriedade | Valor |
|---|---|
| Chain ID | `8453` |
| Tempo de bloco | ~2 segundos |
| Custo medio de gas (DeFi tx) | $0.001 - $0.005 |
| Estrutura de fee | L2 execution fee + L1 data fee |

> **Conceito: L1 data fee**
> Toda L2 precisa "postar" um resumo das suas transacoes de volta no Ethereum (L1) para garantir seguranca. Esse custo e o "L1 data fee". Depois do EIP-4844 (blobs), esse custo caiu drasticamente.

### Contratos

```python
# === REDE ===
CHAIN_ID = 8453
BASE_RPC_URL = "https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"

# === USDC (nativo, emitido pela Circle) ===
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # 6 decimais

# === AAVE V3 ===
AAVE_POOL = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"
AAVE_POOL_DATA_PROVIDER = "0x0F43731EB8d45A581f4a36DD74F5f358bc90C73A"
AAVE_AUSDC = "0x4e65fE4DbA92790696d040ac24Aa414708F5c0AB"  # aToken (recibo do deposito)

# === COMPOUND III (Comet) ===
COMPOUND_COMET = "0xb125E6687d4313864e53df431d5425969c15Eb2F"  # mercado USDC nativo
COMPOUND_REWARDS = "0x123964802e6ABabBE1Bc9547D72Ef1B69B00A6b1"
```

> **Conceito: aToken**
> Quando voce deposita USDC no Aave, recebe "aUSDC" (aToken) em troca. E um recibo. Seu saldo de aUSDC cresce automaticamente a cada segundo conforme os juros acumulam. Quando voce saca, devolve os aTokens e recebe USDC + juros.

> **Conceito: Comet**
> Compound III redesenhou seu protocolo num unico contrato chamado "Comet". Diferente do Aave que te da tokens de recibo, no Compound seu saldo e rastreado internamente pelo contrato. `balanceOf()` ja retorna saldo + juros acumulados.

> **Importante: USDC nativo vs USDbC**
> Na Base existem dois "USDC": o nativo (emitido direto pela Circle na Base) e o USDbC (bridged, que veio do Ethereum via ponte). Usamos o **nativo** porque e o que os protocolos mais recentes suportam e tem mais liquidez.

---

## 3. Parametros e Thresholds

```python
# === CAPITAL ===
INITIAL_CAPITAL_USDC = 50          # Capital inicial em USDC
MIN_POSITION_SIZE = 5              # Minimo para valer a pena mover (em USDC)

# === THRESHOLDS DE DECISAO ===
MIN_APY_DIFF = 1.5                 # Diferenca minima de APY (%) para considerar mover
                                   # Ex: Aave 3% e Compound 5% = diff de 2% > 1.5% -> move
MIN_APY_ABSOLUTE = 0.5             # APY minimo absoluto do destino (%)
                                   # Nao move pra protocolo pagando menos que 0.5%

# === GAS / CUSTO ===
MAX_GAS_COST_USD = 0.10            # Maximo aceitavel de gas por operacao (em USD)
MIN_PROFIT_AFTER_GAS = 0.01        # Lucro minimo liquido apos gas (em USD)
                                   # Se mover custa $0.005 de gas, precisa render
                                   # pelo menos $0.015 a mais no destino

# === SEGURANCA ===
MAX_SINGLE_TX_USDC = 50            # Maximo por transacao (nunca mais que o capital total)
APPROVED_PROTOCOLS = ["aave_v3", "compound_iii"]  # Whitelist de protocolos
APPROVED_TOKENS = ["USDC"]         # Whitelist de tokens
MAX_GAS_PRICE_GWEI = 0.5           # Gas price maximo aceitavel na Base

# === TIMING ===
POLL_INTERVAL_SECONDS = 300        # Checar taxas a cada 5 minutos
MIN_TIME_BETWEEN_MOVES = 3600     # Minimo 1 hora entre movimentacoes
                                   # Evita ficar pulando de um lado pro outro
COOLDOWN_AFTER_ERROR = 600         # 10 min de espera apos qualquer erro
```

### Justificativa dos Thresholds

**MIN_APY_DIFF = 1.5%** — Com $50, uma diferenca de 1.5% APY gera ~$0.75/ano a mais. Parece pouco, mas como nao estamos pagando quase nada de gas na Base ($0.005), praticamente qualquer diferenca acima de 1% ja compensa. O threshold de 1.5% da uma margem de seguranca.

**MIN_TIME_BETWEEN_MOVES = 1h** — Protege contra "flapping" (ficar pulando entre protocolos quando as taxas oscilam rapido). Se Aave sobe pra 5% e Compound cai pra 3%, mas 10 min depois inverte, sem cooldown o bot gastaria gas atoa.

**MAX_GAS_COST_USD = $0.10** — Na Base, uma tx DeFi custa ~$0.005. O limite de $0.10 so seria atingido se a rede estivesse extremamente congestionada, o que e raro.

---

## 4. Fluxo Passo-a-Passo

### 4.1 Listener (O Olho)

O Listener roda em loop, coletando dados on-chain a cada `POLL_INTERVAL_SECONDS`.

```
A cada 5 minutos:
  1. Conectar via RPC (Alchemy) na Base
  2. Ler APY do Aave V3:
     - Chamar AAVE_POOL.getReserveData(USDC)
     - Extrair liquidityRate (vem em "ray" = 1e27)
     - Converter para APY%: (liquidityRate / 1e27) * 100
  3. Ler APY do Compound III:
     - Chamar COMPOUND_COMET.getUtilization()
     - Chamar COMPOUND_COMET.getSupplyRate(utilization)
     - Converter para APY%: (supplyRate / 1e18) * 31536000 * 100
  4. Ler saldo do bot em cada protocolo:
     - Aave: AAVE_POOL_DATA_PROVIDER.getUserReserveData(USDC, BOT_WALLET)
       -> campo currentATokenBalance
     - Compound: COMPOUND_COMET.balanceOf(BOT_WALLET)
  5. Ler saldo USDC livre na wallet:
     - USDC.balanceOf(BOT_WALLET)
  6. Ler gas price atual:
     - w3.eth.gas_price
  7. Montar o JSON de estado e enviar para o Engine
```

> **Conceito: Ray (1e27)**
> Aave usa uma precisao chamada "ray" onde 1e27 = 100%. Entao se `liquidityRate = 3e25`, isso e `3e25 / 1e27 = 0.03 = 3% APY`. Isso evita problemas de arredondamento com numeros muito pequenos.

> **Conceito: Utilization Rate**
> E a porcentagem do capital depositado que esta sendo emprestado. Se $1M foi depositado e $700k emprestado, utilization = 70%. Quanto maior a utilizacao, maior o APY (oferta e demanda).

### 4.2 Engine (O Cerebro — LLM)

O Engine recebe o JSON de estado e decide o que fazer usando function calling.

**Prompt do sistema para o LLM:**
```
Voce e um agente DeFi que gerencia uma posicao de USDC na rede Base.
Seu objetivo e maximizar o rendimento (APY) movendo capital entre Aave V3
e Compound III, minimizando custos de gas e riscos.

Regras:
- So opere com USDC nos protocolos aprovados (Aave V3, Compound III)
- So mova capital se a diferenca de APY for >= {MIN_APY_DIFF}%
- Sempre considere o custo de gas antes de decidir
- Se ambos APYs estiverem abaixo de {MIN_APY_ABSOLUTE}%, mantenha posicao atual
- Nunca mova mais que {MAX_SINGLE_TX_USDC} USDC por transacao
- Respeite o cooldown minimo de {MIN_TIME_BETWEEN_MOVES}s entre movimentacoes
- Se estiver em duvida, escolha "hold" (nao fazer nada)
```

**Decisoes possiveis do LLM:**
1. `hold` — Nao fazer nada (taxas parecidas, ou cooldown ativo)
2. `move_to_aave` — Sacar do Compound e depositar no Aave
3. `move_to_compound` — Sacar do Aave e depositar no Compound
4. `initial_deposit` — Depositar USDC livre da wallet no melhor protocolo

### 4.3 Firewall (O Guarda)

Antes de executar qualquer decisao do LLM, o Firewall valida deterministicamente:

```python
def validate_action(action, state):
    checks = {
        # 1. Protocolo esta na whitelist?
        "protocol_approved": action.protocol in APPROVED_PROTOCOLS,

        # 2. Token esta na whitelist?
        "token_approved": action.token in APPROVED_TOKENS,

        # 3. Valor dentro do limite?
        "amount_within_limit": action.amount <= MAX_SINGLE_TX_USDC,

        # 4. Gas dentro do limite?
        "gas_acceptable": state.gas_cost_usd <= MAX_GAS_COST_USD,

        # 5. Gas price nao esta absurdo?
        "gas_price_ok": state.gas_price_gwei <= MAX_GAS_PRICE_GWEI,

        # 6. Cooldown respeitado?
        "cooldown_ok": (now - state.last_move_timestamp) >= MIN_TIME_BETWEEN_MOVES,

        # 7. Lucro liquido positivo?
        "profitable": action.expected_gain_30d > (state.gas_cost_usd * 2),

        # 8. Bot tem saldo suficiente?
        "sufficient_balance": action.amount <= state.available_balance,

        # 9. Contrato de destino e o esperado?
        "contract_verified": action.target_contract in KNOWN_CONTRACTS,
    }

    passed = all(checks.values())
    if not passed:
        failed = [k for k, v in checks.items() if not v]
        log(f"FIREWALL BLOCKED: {failed}")

    return passed
```

> **Por que o Firewall e critico?**
> O LLM pode "alucinar" — sugerir mover $500 quando voce so tem $50, ou interagir com um contrato desconhecido. O Firewall e codigo Python puro (deterministico, sem IA) que NUNCA pode ser bypassado. Ele e a ultima linha de defesa antes de assinar qualquer transacao com sua chave privada.

### 4.4 Executor (A Mao)

Se o Firewall aprovar, o Executor monta e envia a transacao.

**Fluxo para mover de Compound -> Aave (exemplo):**

```
Passo 1: Sacar do Compound
  - Chamar COMPOUND_COMET.withdraw(USDC, amount)
  - Gas estimado: ~150,000 gas units
  - Aguardar confirmacao (1-2 blocos = 2-4 segundos na Base)
  - Verificar que USDC chegou na wallet

Passo 2: Aprovar USDC para o Aave
  - Chamar USDC.approve(AAVE_POOL, amount)
  - Gas estimado: ~50,000 gas units
  - Aguardar confirmacao

  > Conceito: Approve
  > Em DeFi, voce precisa "autorizar" um contrato a gastar seus tokens.
  > E como dizer pro banco: "permito que o Aave pegue ate X USDC da minha conta".
  > Sem isso, a transacao de deposito falha. Esse e o padrao ERC-20.

Passo 3: Depositar no Aave
  - Chamar AAVE_POOL.supply(USDC, amount, BOT_WALLET, 0)
  - Gas estimado: ~250,000 gas units
  - Aguardar confirmacao
  - Verificar que aUSDC apareceu na wallet

Custo total estimado: ~450,000 gas units * ~0.005 gwei = < $0.01
```

**Fluxo para mover de Aave -> Compound:**

```
Passo 1: Sacar do Aave
  - Chamar AAVE_POOL.withdraw(USDC, amount, BOT_WALLET)
  - Para sacar tudo: usar amount = 2**256 - 1 (tipo uint256 max)

Passo 2: Aprovar USDC para o Compound
  - Chamar USDC.approve(COMPOUND_COMET, amount)

Passo 3: Depositar no Compound
  - Chamar COMPOUND_COMET.supply(USDC, amount)
```

**Monitoramento pos-transacao:**
```
Apos cada TX enviada:
  1. Guardar o tx_hash
  2. Esperar confirmacao: w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
  3. Se receipt.status == 1: sucesso
  4. Se receipt.status == 0: transacao reverteu -> logar erro, acionar cooldown
  5. Se timeout: TX pode estar presa -> verificar nonce, considerar reenvio com gas maior
```

---

## 5. JSON de Estado

O Listener monta esse JSON a cada ciclo e envia pro Engine:

```json
{
  "timestamp": "2026-02-24T15:30:00Z",
  "network": {
    "chain_id": 8453,
    "chain_name": "Base",
    "gas_price_gwei": 0.005,
    "gas_cost_estimate_usd": 0.003,
    "block_number": 25000000
  },
  "wallet": {
    "address": "0x...",
    "usdc_balance": 0.50,
    "eth_balance": 0.001
  },
  "positions": {
    "aave_v3": {
      "deposited_usdc": 49.50,
      "current_apy_pct": 3.2,
      "atoken_balance": 49.52,
      "protocol_tvl_usdc": 150000000
    },
    "compound_iii": {
      "deposited_usdc": 0,
      "current_apy_pct": 5.8,
      "comet_balance": 0,
      "protocol_tvl_usdc": 95000000
    }
  },
  "computed": {
    "total_capital_usdc": 50.02,
    "best_protocol": "compound_iii",
    "best_apy_pct": 5.8,
    "current_protocol": "aave_v3",
    "current_apy_pct": 3.2,
    "apy_diff_pct": 2.6,
    "should_consider_move": true,
    "estimated_annual_gain_if_move": 1.30,
    "estimated_gas_cost_for_move": 0.008,
    "time_since_last_move_seconds": 7200,
    "cooldown_active": false
  },
  "history": {
    "last_move_timestamp": "2026-02-24T13:30:00Z",
    "last_move_action": "move_to_aave",
    "total_moves_24h": 2,
    "total_gas_spent_24h_usd": 0.012
  }
}
```

> **Conceito: TVL (Total Value Locked)**
> E o total de dinheiro depositado num protocolo. TVL alto = protocolo confiavel e liquido. Se o TVL de um protocolo cair drasticamente, pode ser sinal de problema (hack, panico). O bot pode usar isso como sinal de risco.

> **Conceito: ETH balance na wallet**
> Mesmo operando com USDC, o bot precisa de um pouco de ETH na wallet para pagar gas. Na Base, $1 de ETH dura centenas de transacoes. Mas se ETH zerar, o bot para. O estado monitora isso.

---

## 6. Tools Disponiveis para o LLM

O LLM interage via function calling. Estas sao as tools que ele pode chamar:

### 6.1 `hold`
Nao fazer nada neste ciclo.

```json
{
  "name": "hold",
  "description": "Manter posicao atual sem mudancas",
  "parameters": {
    "reason": {
      "type": "string",
      "description": "Explicacao da decisao de nao agir"
    }
  }
}
```

### 6.2 `move_funds`
Mover USDC de um protocolo para outro.

```json
{
  "name": "move_funds",
  "description": "Sacar USDC de um protocolo e depositar em outro",
  "parameters": {
    "from_protocol": {
      "type": "string",
      "enum": ["aave_v3", "compound_iii", "wallet"],
      "description": "De onde sacar"
    },
    "to_protocol": {
      "type": "string",
      "enum": ["aave_v3", "compound_iii"],
      "description": "Onde depositar"
    },
    "amount_usdc": {
      "type": "number",
      "description": "Quanto mover em USDC (usar -1 para mover tudo)"
    },
    "reason": {
      "type": "string",
      "description": "Explicacao da decisao"
    }
  }
}
```

### 6.3 `alert`
Sinalizar situacao que precisa atencao humana.

```json
{
  "name": "alert",
  "description": "Enviar alerta para o operador humano",
  "parameters": {
    "severity": {
      "type": "string",
      "enum": ["info", "warning", "critical"],
      "description": "Gravidade do alerta"
    },
    "message": {
      "type": "string",
      "description": "Descricao do que foi detectado"
    }
  }
}
```

**Quando o LLM deve usar `alert`:**
- APY caiu pra 0% em ambos protocolos (algo estranho)
- TVL caiu mais de 50% em um protocolo (possivel hack)
- ETH da wallet esta acabando (nao vai conseguir pagar gas)
- Alguma anomalia nos dados que nao se encaixa nos padroes normais

---

## 7. Calculos de Lucratividade

### Cenario realista: $50 de capital

| Metrica | Valor |
|---|---|
| Capital | $50 USDC |
| APY medio capturado | 4% (estimativa conservadora entre Aave ~3% e Compound ~5%) |
| Rendimento anual bruto | $2.00 |
| Rendimento mensal bruto | $0.17 |
| Movimentacoes por mes (estimativa) | 4 |
| Custo gas por movimentacao | ~$0.008 (3 TXs: withdraw + approve + supply) |
| Custo gas mensal | $0.032 |
| Rendimento mensal liquido | ~$0.14 |
| Rendimento anual liquido | ~$1.62 |
| ROI anual | ~3.2% |

### Cenario otimista: picos de APY

| Metrica | Valor |
|---|---|
| Capital | $50 USDC |
| APY medio capturado | 8% (pegando picos frequentes) |
| Rendimento anual bruto | $4.00 |
| Custo gas anual (~48 moves) | $0.38 |
| Rendimento anual liquido | ~$3.62 |
| ROI anual | ~7.2% |

### Breakeven: quanto precisa render pra cobrir gas?

```
Gas por move completo (3 TXs):     ~$0.008
Moves por mes:                      4
Gas mensal:                         $0.032
Gas anual:                          $0.384

Para breakeven com $50:
  APY minimo = $0.384 / $50 = 0.77% ao ano

Ou seja: qualquer APY medio acima de ~0.8% ja cobre os custos de gas.
Na Base, gas quase NUNCA sera o gargalo com $50 de capital.
```

### O valor real: aprendizado

Com $50, o lucro absoluto e pequeno ($1-4/ano). Mas o valor esta em:
1. **Aprender DeFi na pratica** — interagir com contratos reais
2. **Infraestrutura escalavel** — se funciona com $50, funciona com $5,000
3. **Validar a estrategia** — provar que o bot toma decisoes corretas antes de escalar

---

## 8. Tratamento de Erros

### Transacao revertida
```
Se receipt.status == 0:
  1. Logar o motivo (pode ser: saldo insuficiente, allowance expirado, slippage)
  2. Ativar cooldown de COOLDOWN_AFTER_ERROR segundos
  3. No proximo ciclo, re-ler estado completo antes de tentar novamente
  4. Se falhar 3x seguidas na mesma operacao: enviar alert("critical")
```

### Transacao presa (nonce stuck)
```
Se TX nao confirma em 60 segundos:
  1. Verificar se o nonce ja foi usado (outra TX passou na frente)
  2. Se nonce ainda pendente: reenviar com gas 50% maior (speed up)
  3. Se reenvio tambem travar: enviar alert("critical"), esperar intervencao humana
```

> **Conceito: Nonce**
> Cada transacao da sua wallet tem um numero sequencial (nonce). A TX #5 so pode ser processada depois da #4. Se a #4 travar, tudo atras dela trava tambem. Para "destravar", voce envia uma nova TX com o MESMO nonce mas gas maior — os validadores preferem a mais lucrativa e descartam a antiga.

### ETH insuficiente para gas
```
Se eth_balance < 0.0001 ETH:
  1. Enviar alert("critical", "ETH para gas esta acabando")
  2. Pausar todas as operacoes
  3. Operador humano precisa enviar ETH para a wallet do bot
```

---

## 9. Funcoes ABI Necessarias

### USDC (ERC-20)
```python
USDC_ABI = [
    # Consultar saldo
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "account", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},

    # Aprovar gasto por outro contrato
    {"name": "approve", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "spender", "type": "address"},
                {"name": "amount", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},

    # Verificar quanto ja esta aprovado
    {"name": "allowance", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "owner", "type": "address"},
                {"name": "spender", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},

    # Consultar decimais (USDC = 6)
    {"name": "decimals", "type": "function", "stateMutability": "view",
     "inputs": [],
     "outputs": [{"name": "", "type": "uint8"}]}
]
```

### Aave V3 Pool
```python
AAVE_POOL_ABI = [
    # Depositar USDC
    {"name": "supply", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "asset", "type": "address"},
         {"name": "amount", "type": "uint256"},
         {"name": "onBehalfOf", "type": "address"},
         {"name": "referralCode", "type": "uint16"}
     ], "outputs": []},

    # Sacar USDC (retorna amount real sacado)
    {"name": "withdraw", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "asset", "type": "address"},
         {"name": "amount", "type": "uint256"},
         {"name": "to", "type": "address"}
     ], "outputs": [{"name": "", "type": "uint256"}]},

    # Dados do reserve (inclui liquidityRate = APY)
    {"name": "getReserveData", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "asset", "type": "address"}],
     "outputs": [{"name": "", "type": "tuple", "components": [
         {"name": "configuration", "type": "uint256"},
         {"name": "liquidityIndex", "type": "uint128"},
         {"name": "currentLiquidityRate", "type": "uint128"},
         {"name": "variableBorrowIndex", "type": "uint128"},
         {"name": "currentVariableBorrowRate", "type": "uint128"},
         {"name": "currentStableBorrowRate", "type": "uint128"},
         {"name": "lastUpdateTimestamp", "type": "uint40"},
         {"name": "id", "type": "uint16"},
         {"name": "aTokenAddress", "type": "address"},
         {"name": "stableDebtTokenAddress", "type": "address"},
         {"name": "variableDebtTokenAddress", "type": "address"},
         {"name": "interestRateStrategyAddress", "type": "address"},
         {"name": "accruedToTreasury", "type": "uint128"},
         {"name": "unbacked", "type": "uint128"},
         {"name": "isolationModeTotalDebt", "type": "uint128"}
     ]}]
    }
]
```

### Aave V3 PoolDataProvider
```python
AAVE_DATA_PROVIDER_ABI = [
    # Dados do usuario em um reserve especifico
    {"name": "getUserReserveData", "type": "function", "stateMutability": "view",
     "inputs": [
         {"name": "asset", "type": "address"},
         {"name": "user", "type": "address"}
     ],
     "outputs": [
         {"name": "currentATokenBalance", "type": "uint256"},
         {"name": "currentStableDebt", "type": "uint256"},
         {"name": "currentVariableDebt", "type": "uint256"},
         {"name": "principalStableDebt", "type": "uint256"},
         {"name": "scaledVariableDebt", "type": "uint256"},
         {"name": "stableBorrowRate", "type": "uint256"},
         {"name": "liquidityRate", "type": "uint256"},
         {"name": "stableRateLastUpdated", "type": "uint40"},
         {"name": "usageAsCollateralEnabled", "type": "bool"}
     ]
    }
]
```

### Compound III Comet
```python
COMPOUND_COMET_ABI = [
    # Depositar USDC
    {"name": "supply", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "asset", "type": "address"},
         {"name": "amount", "type": "uint256"}
     ], "outputs": []},

    # Sacar USDC
    {"name": "withdraw", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "asset", "type": "address"},
         {"name": "amount", "type": "uint256"}
     ], "outputs": []},

    # Saldo (inclui juros acumulados)
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "account", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},

    # Taxa de utilizacao atual
    {"name": "getUtilization", "type": "function", "stateMutability": "view",
     "inputs": [],
     "outputs": [{"name": "", "type": "uint256"}]},

    # Taxa de rendimento por segundo para dada utilizacao
    {"name": "getSupplyRate", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "utilization", "type": "uint256"}],
     "outputs": [{"name": "", "type": "uint64"}]},

    # Supply total
    {"name": "totalSupply", "type": "function", "stateMutability": "view",
     "inputs": [],
     "outputs": [{"name": "", "type": "uint256"}]}
]
```

### Conversao de APY

```python
# === AAVE: liquidityRate (ray) -> APY% ===
RAY = 10**27
def aave_rate_to_apy(liquidity_rate: int) -> float:
    """Converte o liquidityRate do Aave (ray) para APY percentual."""
    rate = liquidity_rate / RAY  # ex: 0.03 = 3%
    return rate * 100

# === COMPOUND: supplyRate (per-second, 1e18) -> APY% ===
SECONDS_PER_YEAR = 31_536_000
def compound_rate_to_apy(supply_rate_per_second: int) -> float:
    """Converte o supplyRate do Compound (por segundo) para APY percentual."""
    rate_per_second = supply_rate_per_second / 1e18
    apy = ((1 + rate_per_second) ** SECONDS_PER_YEAR) - 1
    return apy * 100
```

---

## 10. Diagrama do Loop Completo

```
                    ┌─────────────────────────────┐
                    │         LOOP (5 min)        │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │          LISTENER           │
                    │  - Ler APY Aave + Compound  │
                    │  - Ler saldos do bot        │
                    │  - Ler gas price            │
                    │  - Montar JSON de estado    │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │           ENGINE            │
                    │  - Enviar estado pro LLM    │
                    │  - LLM analisa e decide     │
                    │  - Retorna: hold/move/alert │
                    └──────────────┬──────────────┘
                                   │
                         ┌─────────▼─────────┐
                         │  Decisao = hold?  │
                         └────┬─────────┬────┘
                           SIM│         │NAO
                              │         │
                    ┌─────────▼───┐  ┌──▼────────────────┐
                    │ Logar e     │  │    FIREWALL       │
                    │ aguardar    │  │  - Checar 9       │
                    │ proximo     │  │    validacoes     │
                    │ ciclo       │  │    deterministicas│
                    └─────────────┘  └──┬──────────┬─────┘
                                        │          │
                                     PASSOU     BLOQUEOU
                                        │          │
                              ┌─────────▼───┐  ┌───▼───────────┐
                              │  EXECUTOR   │  │ Logar motivo  │
                              │  1. Withdraw│  │ do bloqueio   │
                              │  2. Approve │  │ e aguardar    │
                              │  3. Supply  │  └───────────────┘
                              └──────┬──────┘
                                     │
                              ┌──────▼───────┐
                              │ CONFIRMACAO  │
                              │ - receipt OK?│
                              │ - Atualizar  │
                              │   estado     │
                              └──────────────┘
```

---

## 11. Checklist Pre-Deploy

Antes de rodar o bot com dinheiro real:

- [ ] Bot wallet criada com chave nova (nunca usada antes)
- [ ] Chave privada armazenada em variavel de ambiente ou secrets manager
- [ ] ETH suficiente na wallet para gas (~$1 de ETH dura meses na Base)
- [ ] USDC depositado na wallet do bot
- [ ] Todos os contratos verificados manualmente no BaseScan
- [ ] Firewall testado com cenarios edge-case
- [ ] Paper trading rodou por pelo menos 1 semana sem anomalias
- [ ] Alertas configurados (Telegram/Discord/email)
- [ ] Logs persistentes configurados
- [ ] Plano de emergencia: como pausar o bot e sacar tudo manualmente
