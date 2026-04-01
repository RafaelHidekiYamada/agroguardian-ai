# Camada de Machine Learning

Esta pasta concentra os artefatos de Machine Learning do AgroGuardian AI.

## Objetivo da Sprint 1
- adicionar uma rede neural ao projeto sem quebrar o MVP atual;
- comparar o modelo atual com uma abordagem de rede neural;
- gerar métricas reutilizáveis para a banca.

## Arquivos
- `train_neural_network.py`: treina uma rede neural (`MLPRegressor`) para previsão do risco.
- `evaluate_models.py`: compara o modelo atual do sistema com a rede neural.
- `saved_models/`: onde ficam os modelos e métricas salvas.

## Como usar
```bash
python -m ml.train_neural_network
python -m ml.evaluate_models
```
