# Segurança e Governança

## Estado atual
- JWT para usuarios e RBAC por permissoes.
- Escopos de cliente, fazenda e equipamento nas rotas protegidas.
- API keys de IoT geradas com CSPRNG e armazenadas somente como hash bcrypt.
- API key plaintext retorna apenas na criacao ou rotacao do dispositivo.
- Validacao de `X-Device-ID` contra `device_id` do corpo e vinculacao segura
  `device -> equipment -> farm -> client` no servidor.
- Revogacao, desativacao, rate limit por dispositivo, limite de payload e
  auditoria de eventos criticos.
- Rejeicao de credenciais em payloads e metadados; serializacao defensiva de
  dados legados sensiveis.
- HTTPS obrigatorio para firmware de producao. O bypass IoT so pode ocorrer em
  development/test com `IOT_AUTH_ENABLED=false`; em production ele nao e ativo.
