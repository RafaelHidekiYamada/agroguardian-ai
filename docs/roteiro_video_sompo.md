# Roteiro do vídeo — AgroGuardian AI para a Sompo

**Duração-alvo: 12 min** (limite do avaliador: 5 a 15 min). Ensaie para fechar entre 11 e 13 min e deixar folga.
**Tom:** profissional e simples. Fale de *prejuízo evitado*, não de tecnologia. Cada termo técnico ganha uma tradução em uma frase.

## Mapa dos requisitos

| Req. | O que provar | Onde no vídeo |
|---|---|---|
| 1 | 5–15 min | Cronômetro do roteiro (12 min) |
| 2 | Hardware em tempo real gravando em banco | Bloco 5 |
| 3 | IA consumindo os dados | Bloco 6 |
| 4 | IA ajusta o relatório com dado novo, ao vivo | Bloco 7 |
| 5 | Custo do hardware | Bloco 3 |
| 6 | Tela de autenticação | Bloco 4 |
| 7 | Cadastro de fazenda e maquinário | Bloco 4 |
| 8 | Diferenciais nos minutos finais | Bloco 8 (10:00–12:00) |

---

## Bloco 1 — Abertura e problema (0:00–0:50)

**Na tela:** rosto ou logo + título "AgroGuardian AI — prevenção de sinistros em máquinas agrícolas". Depois uma foto de trator atolado ou tombado.

**Fala:**
> "Olá, equipe Sompo. Somos [nomes]. Todo ano, tratores e colheitadeiras sofrem tombamentos, atolamentos e colisões perto de rios e terrenos inclinados. Hoje o seguro descobre isso depois, quando o sinistro já aconteceu.
> O AgroGuardian AI muda essa ordem: um pequeno equipamento no trator mede as condições em tempo real, e uma inteligência artificial avisa o risco *antes* do acidente. Nos próximos minutos vou mostrar tudo funcionando, ao vivo."

## Bloco 2 — Como funciona, em 1 slide (0:50–1:40)

**Na tela:** um slide com 4 caixas e setas: **Sensores no trator → Nuvem (banco de dados) → IA calcula o risco → Painel para Sompo, gestor e operador.**

**Fala:**
> "É simples: o equipamento coleta dados, envia pela internet, guarda tudo em um banco de dados, e a IA transforma isso em uma nota de risco de 0 a 100, com alerta e explicação em português. Tudo que vou mostrar já está publicado na internet, não é uma simulação no meu computador."

**Slide de apoio (opcional):** diagrama de `docs/arquitetura_agroguardian.md`, simplificado.

## Bloco 3 — O hardware e o custo (1:40–3:10) · Req. 5

**Na tela:** a placa montada sobre a mesa, câmera aproximando cada peça. Depois uma **tabela de custos** (slide) e, em seguida, **prints das lojas ou notas fiscais** como prova.

**Fala:**
> "Este é o equipamento. O cérebro é um ESP32, um chip com Wi-Fi que custa poucos reais. Ele lê três coisas:
> - **BME280:** temperatura, umidade do ar e pressão, ou seja, o clima local;
> - **MPU-6050:** inclinação e vibração, que detecta tombamento e impacto;
> - **HC-SR04:** distância até obstáculos à frente.
>
> O kit completo custa cerca de **R$ [TOTAL]**. Aqui estão as notas/prints de compra. Para uma frota, é um custo muito baixo perto do valor de um único sinistro."

**Na tela, uma tabela assim (preencher com valores reais):**

| Item | Função | Preço pago |
|---|---|---|
| ESP32 DevKit | Cérebro e Wi-Fi | R$ ___ |
| BME280 | Clima | R$ ___ |
| MPU-6050 | Inclinação/impacto | R$ ___ |
| HC-SR04 | Obstáculos | R$ ___ |
| Cabos, protoboard, resistores, fonte | Montagem | R$ ___ |
| **Total** | | **R$ ___** |

> ⚠️ **Lacuna do projeto:** nenhum arquivo do repositório tem preços. Você precisa reunir notas fiscais, prints do carrinho ou links das lojas. Uma estimativa **de referência para conferir** (não use como prova): kit de ESP32 + 3 sensores + montagem costuma ficar entre R$ 150 e R$ 300 no varejo brasileiro. O que vale no vídeo é o comprovante real.

## Bloco 4 — Login e cadastro de fazendas e máquinas (3:10–5:00) · Req. 6 e 7

**Na tela:** abrir `agroguardian-dashboard-tkxj.onrender.com`. Mostrar a **tela de acesso seguro** antes de logar.

**Fala (login):**
> "O sistema é protegido por login. Sem usuário e senha, nada aparece. Cada pessoa vê apenas o que seu perfil permite: a Sompo enxerga o painel executivo, o operador enxerga a sua máquina, o administrador cadastra."

**Ações:**
1. Mostrar a tela de login (barra lateral esquerda, campos Usuário e Senha).
2. Logar como administrador. Mostrar na barra lateral "Logado como… / Perfil: ADMIN".
3. *(opcional, 20 s)* Tentar uma senha errada antes para mostrar o bloqueio.

**Fala (cadastro):**
> "Aqui na aba **Equipamentos** fica o cadastro. A estrutura é: fazenda, máquina e dispositivo. Vou cadastrar uma nova fazenda agora."

**Ações na aba Equipamentos:**
1. Mostrar as tabelas existentes: **Fazendas**, **Equipamentos**, **Dispositivos IoT**.
2. Cadastrar uma fazenda nova ao vivo (formulário "Salvar fazenda"): nome, região, coordenadas.
3. Mostrar o equipamento e o dispositivo ESP32 já vinculados à fazenda.

**Fala:**
> "Cada dispositivo tem uma chave secreta própria. Mesmo que alguém descubra o endereço do sistema, não consegue enviar dados falsos sem a chave."

> ⚠️ **Nunca mostre** a API key gerada, a senha do Wi-Fi nem o arquivo `Secrets.h`. Se for gerar credencial na tela, corte essa parte na edição.

## Bloco 5 — Hardware ao vivo gravando no banco (5:00–7:00) · Req. 2

**Na tela (tela dividida):** à esquerda, a câmera na placa com o monitor serial do computador; à direita, o painel na aba **Telemetria**.

**Preparação:** aba Telemetria → escolher o equipamento → período "Últimos 5 minutos" → marcar **Auto** com 5 segundos.

**Fala:**
> "Ligo o equipamento. Aqui no monitor da placa vemos ela conectando no Wi-Fi e enviando uma leitura a cada 15 segundos. Repare na linha *status 200 / accepted*: é a nuvem confirmando que recebeu e guardou."

**Ações:**
1. Mostrar o serial: `[WiFi]`, `[HTTP] … status 200`, `[API] accepted telemetry_id=…`.
2. No painel, mostrar temperatura, umidade, pressão, inclinação e distância chegando.
3. **Provar o armazenamento** (mostrar pelo menos uma destas):
   - A tabela **Histórico** na aba Telemetria ganhando linhas novas a cada envio (o `telemetry_id` sobe);
   - O painel do Render → banco `agroguardian-db` (PostgreSQL) e/ou os **Logs** do serviço `agroguardian-api` mostrando `POST /api/v1/telemetry/esp 200`.

**Fala:**
> "Cada leitura vira uma linha nova no banco de dados na nuvem. Nada é sobrescrito: temos o histórico completo, o que serve de auditoria em caso de sinistro."

## Bloco 6 — A IA consumindo esses dados (7:00–8:30) · Req. 3

**Na tela:** aba Telemetria, seção **Explicação da IA**; depois aba **IA e ML**.

**Fala:**
> "Cada leitura que chegou é entregue à inteligência artificial. Ela combina os sensores da máquina com o clima da região, a distância de rios e o tipo de operação, e gera uma nota de risco. Aqui está a nota, o nível de risco e, mais importante, **a explicação em português**: quais fatores pesaram e quantos pontos cada um adicionou. Não é uma caixa-preta: a Sompo pode auditar cada decisão."

**Ações:**
1. Mostrar Risk Score, nível de risco, "Confiança" e "Qualidade do dado".
2. Mostrar a tabela de fatores (proximidade da água, obstáculo, inclinação, etc.) e a recomendação. Quando uma regra de segurança age, o resumo diz "Risco alto por regra de seguranca: …".
3. Abrir **IA e ML**: modelo em produção (`gradient_boosting`), treinado com **5.117 registros históricos reais de clima da NASA** (NASA POWER).

**Fala:**
> "O modelo aprendeu com mais de cinco mil dias de dados climáticos reais de regiões agrícolas do Brasil. Por cima dele, regras de segurança garantem que um tombamento ou um obstáculo muito próximo sempre gere alerta alto, sem depender da estatística."

> ⚠️ **Seja honesto sobre o alvo do modelo:** o "risk_score" de treino vem de regras operacionais, porque o projeto ainda não tem sinistros reais para treinar. A métrica de ~99% de acerto mede a fidelidade a essa regra, **não** a previsão de sinistros reais. Não destaque o 99% como resultado. Diga o que é: *"um protótipo calibrado, pronto para aprender com os dados reais de sinistros da Sompo"*. Um avaliador técnico vai perceber, e a franqueza pesa a seu favor.

## Bloco 7 — Nova leitura muda o relatório, ao vivo (8:30–10:00) · Req. 4

**Este é o momento mais importante. Ensaie várias vezes.**

**Na tela (dividida):** a placa na câmera + painel Telemetria com Auto ligado. Deixe visível o **Risk Score atual** antes da mudança (anote o número).

**Fala:**
> "Agora vou provocar uma situação de risco de verdade, com o equipamento na minha mão, e acompanhar o relatório."

**Níveis esperados (regras da branch `Modelo-IA-ESP32`):**

| O que você faz com a placa | Risco esperado |
|---|---|
| Parada e nivelada, **caminho livre** (HC-SR04 sem eco, "Fora de alcance") | **Baixo** (~31, medido na sua montagem) |
| Parada e nivelada, objeto entre 80 e 180 cm à frente | Médio (~55) |
| Inclinar 20° a 44° | Médio (~49–56) |
| **Inclinar 45° ou mais** (tombamento) | **Alto** (75) |
| **Mão a 80 cm ou menos do HC-SR04** (obstáculo próximo) | **Alto** (75) |
| Tombamento **e** obstáculo próximo (ou impacto) juntos | **Crítico** (88) |

**Ações (sugestão de ordem de impacto visual):**
1. Com a placa nivelada e o HC-SR04 apontado para um espaço livre (mostra "Fora de alcance"), mostre o **Baixo** (~31) e anote o Risk Score.
2. **Aproximar a mão do HC-SR04** (a 50 cm ou menos) → sobe para **Alto**.
3. Tirar a mão e **inclinar a placa** além de 45° → **Alto** de novo, agora por tombamento.
4. Fazer as duas coisas juntas → **Crítico**.
5. *(opcional)* **Balançar a placa** (impacto) ou **soprar o BME280** (temperatura e umidade sobem, sem grande efeito no risco).

**Aguardar o próximo envio (até 15 s) e mostrar:**
- O Risk Score subindo (ex.: de "Baixo" para "Alto" ou "Crítico");
- A explicação e a recomendação mudando ("Risco alto por regra de seguranca: tombamento…" ou "obstaculo proximo…");
- Um novo alerta e um novo evento na lista de **Eventos IoT**;
- Mudança na aba **Alertas e auditoria** / **Ranking** / **Risco regional**.

**Fala:**
> "Olhem: uma nova leitura chegou, a nota subiu de [X] para [Y], a explicação passou a citar [tombamento/obstáculo próximo], e o alerta apareceu sozinho. Ninguém apertou nenhum botão de recalcular. O relatório se ajustou aos dados novos."

**Fechamento do bloco:** devolver a placa à posição normal e mostrar o risco voltando a cair na leitura seguinte.

> 💡 **Dica de ensaio:** o envio acontece a cada 15 s, então a espera pode parecer longa. Mostre o serial se enviando ("accepted, risco=…") para ancorar. Corte ou acelere a espera na edição, mas **deixe o relógio visível** para provar que é contínuo.
> ⚠️ **Palavra certa:** diga "a IA **reavalia** o risco a cada leitura", não "a IA **aprende** ou **é retreinada** a cada leitura". O projeto não retreina automaticamente (só guarda o histórico para retreino controlado).

## Bloco 8 — Diferenciais e fechamento (10:00–12:00) · Req. 8

**Na tela:** 4 a 5 slides curtos, um diferencial por slide, e depois o dashboard executivo (**Resumo executivo**, **Ranking**, **Mapa/Risco regional**) ao fundo.

**Fala (escolha os 4 mais fortes; sugestão de ordem):**

1. **Prevenção, não indenização.**
   > "Hoje o seguro só entra depois do prejuízo. Aqui a Sompo enxerga o risco antes e pode agir: avisar o operador, mudar a rota, orientar parar."
2. **Hardware barato e escalável.**
   > "Por R$ [TOTAL] por máquina, dá para equipar uma frota inteira. O custo não é barreira."
3. **IA explicável, auditável e com regras de segurança.**
   > "Cada nota vem com a razão. Fica tudo registrado com data e histórico, o que ajuda na regulação de sinistros e evita disputas. E, além do modelo estatístico, regras de segurança garantem alerta alto em tombamento ou obstáculo próximo, mesmo que o modelo erre."
4. **Dados reais que alimentam a precificação.**
   > "Cada máquina gera um score de risco contínuo. Com o tempo, isso permite diferenciar bons e maus riscos, ajustar prêmios e premiar quem opera com segurança."
5. **Simulador 'e se chover amanhã?' e Rota Segura.**
   > "Além de monitorar, o sistema simula cenários e sugere a rota mais segura. Dá para planejar antes da chuva, não só reagir a ela."
6. **Segurança e governança de nível corporativo.**
   > "Login por perfil, chave secreta por dispositivo, criptografia na comunicação e registro de todos os acessos."

**Fala final (30 s):**
> "O AgroGuardian AI entrega o que o setor de seguros agrícolas mais precisa: enxergar o risco antes do sinistro, com um equipamento acessível e uma IA que explica o que decide. O próximo passo natural é uma parceria: treinar o modelo com os dados reais de sinistros da Sompo e rodar um piloto em uma frota. Obrigado!"

**Tela final:** logo, nomes da equipe, link do dashboard e do repositório.

---

## Checklist antes de gravar

**Endereços a usar no vídeo (sua conta do Render):**

| O quê | URL |
|---|---|
| Dashboard | `https://agroguardian-dashboard-tkxj.onrender.com` |
| API | `https://agroguardian-api-jhhd.onrender.com` (documentação em `/docs`) |

> ⚠️ Não use `agroguardian-api.onrender.com` nem `agroguardian-dashboard.onrender.com` (sem o sufixo): são de outra instalação, com outros dados e outro código. O firmware já aponta para `-jhhd`.

**Verificado em 20/09/2026 no seu dashboard (`-tkxj`), logado como admin:**
- ✅ Login funciona; perfil ADMIN vê todas as abas.
- ✅ Cadastro: **Fazenda Santa Helena** (Ribeirão Preto-SP), 3 máquinas (**Trator 01**, Colheitadeira 01, Pulverizador 01) e o dispositivo `ESP32-TRATOR-001` vinculado ao Trator 01.
- ✅ Telemetria física ao vivo: ESP32 **ONLINE**, leitura com 20 s de idade, origem "ESP32 fisico", qualidade **VALID**, com BME280 (23,9 °C, 72,1 %, 927,7 hPa), MPU-6050 (inclinação 0,6° com a montagem nivelada) e HC-SR04 (198,9 cm).
- ✅ IA: Risk Score com explicação e recomendação (na verificação, 51,3 "Médio" com o modelo antigo); 759 previsões acumuladas, ranking com o Trator 01.
- ✅ O deploy com as correções está no ar (`/api/v1/farms` exige login; Visão Geral mostra "Estimativa de impacto" com premissas).
- ✅ O firmware envia por HTTPS para a API `-jhhd` e recebe status 200.

**Mudanças de código feitas depois desta verificação (branch `Modelo-IA-ESP32`, commits `c4b332a` e `bf855be`):**
- A **umidade do solo foi removida do cálculo** (não há sensor): sem sliders de solo, sem fator de solo, modelo retreinado.
- Novas **regras de segurança**: tombamento (≥ 45°) ou obstáculo próximo (≤ 80 cm), cada um sozinho, forçam risco **Alto** (75); dois perigos combinados (tombamento, obstáculo, impacto) forçam **Crítico** (88). Os limites são ajustáveis por variáveis de ambiente (`TILT_ROLLOVER_DEG`, `OBSTACLE_NEAR_CM`).
- ✅ **Publicado em 20/09/2026:** os dois serviços do Render (API e dashboard) seguem o branch `Modelo-IA-ESP32` (o `render.yaml` também aponta para ele, commit `7caf61b`). A API já usa o modelo novo (`gradient_boosting`, sem `umidade_solo`) e as regras de segurança.
- ✅ **Ultrassônico sem eco (`timeout`) não interrompe mais o cálculo:** é tratado como "fora de alcance / nenhum obstáculo à frente". A leitura continua `VALID`, o risco segue atualizando com BME280 e MPU-6050, e o dashboard mostra "Fora de alcance". Um eco fora da faixa (`out_of_range`) continua marcado como suspeito. Um timeout também pode ser fio solto: se o sensor nunca mostrar distância, confira a ligação.
- Os números abaixo (risco 51 "Médio", `water_proximity`, "Umidade do solo N/D") descrevem o estado **anterior**. Refaça a checagem depois do deploy.

**Pontos de atenção da telemetria:**
- **Linha de base medida em 20/09/2026 (produção): 31 = Baixo**, com a placa nivelada e o HC-SR04 sem eco (confiança 65%, qualidade VALID). Antes das mudanças era "Médio" (~51 a 64) por causa da umidade do solo inventada. A explicação cita `water_proximity` (proximidade de água): esse fator vem da localização da fazenda e não muda com a placa. Com um objeto a ~1 m à frente, o risco sobe para Médio (~55).
- **Bateria e GPS aparecem como N/D**, pois não há medição de bateria nem GPS na montagem. No bloco 3, cite só BME280, MPU-6050 e HC-SR04.
- **Limite rígido do tombamento:** 44° dá "Médio" e 45° dá "Alto". Faça a inclinação de forma clara (bem acima de 45°) para o efeito ser óbvio, e o obstáculo a 50 cm ou menos.
- **A inclinação usa uma referência de nivelamento fixa no firmware** (`Config.h`, commit `f6c89b6`), porque o MPU-6050 está de pé na montagem. Se mover o MPU ou a montagem, a leitura de "0°" muda; grave o vídeo com a montagem na mesma posição de hoje.
- **Wi-Fi:** na primeira conexão do dia a placa levou 3 tentativas. Ligue-a 2 a 3 min antes de gravar e teste no Wi-Fi do local (2,4 GHz).

**Números do painel que eram fixos no código (corrigido no commit `6472798`):**
Os percentuais "+18,6%", "+27,4%", "+35,2%" e "+41,8%" e o gráfico "Sinistros potencialmente evitados" (risco médio × 1,8) foram removidos. Os cartões agora se chamam "Sinistros potenciais" e "Economia estimada", com o rótulo "estimativa ilustrativa" e as premissas na tela (R$ 32.800 por sinistro). No vídeo, apresente-os como estimativa, não como resultado medido.

**Riscos práticos:**
1. **API "dorme" no plano gratuito do Render.** Medi **54 s** para acordar. **Abra a API e o dashboard 3 a 5 min antes de gravar** e mantenha uma aba aberta. Nunca comece a gravar com o serviço dormindo.
2. **Banco gratuito do Render tem prazo de validade.** Confira no painel do Render que o `agroguardian-db` ainda está ativo e não vai expirar (os bancos gratuitos expiram após algumas semanas).
3. **Plano B do hardware:** se a placa falhar durante a gravação, o dashboard tem o formulário **"Enviar leitura ESP32"** (aba Operação em tempo real) e o simulador `tools/esp32_simulator.py`. Use só como reserva e diga claramente que é simulação; passar simulação por hardware real seria mentira e reprovaria o requisito 2.
4. **Não mostre as páginas do Render nem as variáveis de ambiente** (contêm segredos). Se quiser provar o armazenamento no banco (bloco 5), use a tabela **Histórico** do dashboard e os **Logs** do serviço `agroguardian-api` com o cuidado de não expor chaves.
5. **Grave em blocos** e junte na edição. O bloco 7 (mudança ao vivo) deve ser gravado sem cortes no momento da mudança e com o relógio à vista.
6. **Nunca exiba:** API key do dispositivo, senha do Wi-Fi, `Secrets.h`, variáveis de ambiente do Render.

## Ideias para elevar o nível (opcionais)

- Uma frase de contexto de mercado no Bloco 1 (com fonte) sobre perdas de máquinas agrícolas no Brasil.
- Mostrar o **Risco regional** e o **mapa** no Bloco 8 para reforçar a visão da carteira da Sompo.
- Legendas em português no vídeo (facilita quem assiste sem som).
