library(readr)
library(dplyr)
library(ggplot2)

dados <- read_csv("data_science_r/data/agroguardian_predictions.csv")

print("Estrutura do dataset:")
print(str(dados))

print("Primeiras linhas:")
print(head(dados))

print("Resumo estatístico:")
print(summary(dados))

dados$predicted_risk <- as.numeric(dados$predicted_risk)

grafico_risco <- ggplot(dados, aes(x = predicted_risk)) +
  geom_histogram(bins = 10) +
  labs(
    title = "Distribuição do Risk Score",
    x = "Risk Score",
    y = "Frequência"
  )

print(grafico_risco)

if ("risk_label" %in% colnames(dados)) {
  grafico_labels <- ggplot(dados, aes(x = risk_label)) +
    geom_bar() +
    labs(
      title = "Quantidade por nível de risco",
      x = "Nível de risco",
      y = "Quantidade"
    )

  print(grafico_labels)
}

if ("input_operation_type" %in% colnames(dados)) {
  grafico_operacao <- ggplot(dados, aes(x = input_operation_type)) +
    geom_bar() +
    labs(
      title = "Operações analisadas",
      x = "Tipo de operação",
      y = "Quantidade"
    )

  print(grafico_operacao)
}

if ("input_operation_type" %in% colnames(dados)) {
  media_operacao <- dados |>
    group_by(input_operation_type) |>
    summarise(
      media_risco = mean(predicted_risk, na.rm = TRUE),
      .groups = "drop"
    )

  print("Média de risco por tipo de operação:")
  print(media_operacao)

  grafico_media_operacao <- ggplot(
    media_operacao,
    aes(x = input_operation_type, y = media_risco)
  ) +
    geom_col() +
    labs(
      title = "Média de risco por tipo de operação",
      x = "Tipo de operação",
      y = "Média do risco"
    )

  print(grafico_media_operacao)
}