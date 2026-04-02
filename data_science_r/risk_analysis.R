library(readr)
library(dplyr)
library(ggplot2)
library(corrplot)

dados <- read_csv("data_science_r/data/agroguardian_predictions.csv")

variaveis_numericas <- dados |>
  select(
    predicted_risk,
    input_umidade_solo,
    input_inclinacao,
    input_distancia_agua,
    input_velocidade,
    input_historico_sinistros,
    input_chuva_mm,
    input_solo_instavel
  ) |>
  mutate(across(everything(), as.numeric))

print("Correlação entre variáveis:")
matriz_cor <- cor(variaveis_numericas, use = "complete.obs")
print(matriz_cor)

corrplot(
  matriz_cor,
  method = "color",
  type = "upper",
  tl.cex = 0.8
)

grafico_umidade <- ggplot(
  dados,
  aes(x = input_umidade_solo, y = predicted_risk)
) +
  geom_point() +
  labs(
    title = "Risco previsto vs Umidade do solo",
    x = "Umidade do solo",
    y = "Risk Score"
  )

print(grafico_umidade)

grafico_agua <- ggplot(
  dados,
  aes(x = input_distancia_agua, y = predicted_risk)
) +
  geom_point() +
  labs(
    title = "Risco previsto vs Distância da água",
    x = "Distância da água",
    y = "Risk Score"
  )

print(grafico_agua)

grafico_velocidade <- ggplot(
  dados,
  aes(x = input_velocidade, y = predicted_risk)
) +
  geom_point() +
  labs(
    title = "Risco previsto vs Velocidade",
    x = "Velocidade",
    y = "Risk Score"
  )

print(grafico_velocidade)

if ("input_clima" %in% colnames(dados)) {
  clima_risco <- dados |>
    group_by(input_clima) |>
    summarise(
      media_risco = mean(predicted_risk, na.rm = TRUE),
      .groups = "drop"
    )

  print("Média de risco por clima:")
  print(clima_risco)

  grafico_clima <- ggplot(
    clima_risco,
    aes(x = input_clima, y = media_risco)
  ) +
    geom_col() +
    labs(
      title = "Média de risco por clima",
      x = "Clima",
      y = "Média do risco"
    )

  print(grafico_clima)
}