# Camada de Machine Learning

Esta pasta concentra treinamento, comparacao e artefatos de IA do AgroGuardian AI.

## Modelos

- `train_decision_trees.py`: testa arvores e ensembles (`DecisionTree`, `RandomForest`, `ExtraTrees`, `GradientBoosting`, `HistGradientBoosting`), busca melhores parametros, calcula curva de threshold para alto risco e salva pesos/importancias.
- `train_neural_network.py`: treina uma rede neural `MLPRegressor`.
- `evaluate_models.py`: compara baseline, rede neural e melhor modelo de arvores.

## Artefatos

- `saved_models/best_risk_model.joblib`: melhor modelo escolhido pelo treino de arvores.
- `saved_models/tree_risk_model.joblib`: melhor artefato da familia de arvores.
- `model_metrics.json`: metricas finais, curva, accuracy, F1, ROC AUC e pesos das features.

## Como usar

```bash
python -m ml.training_data --start 20240101 --end 20251231 --force
python -m ml.train_decision_trees
python -m ml.evaluate_models
```

O runtime da API prioriza `best_risk_model.joblib`. Se ele nao existir, usa o modelo de arvores, depois a rede neural e, por fim, o artefato base do backend.

## Dados reais

`ml/training_data.py` baixa series historicas da NASA POWER Daily API para regioes
agricolas brasileiras e gera `ml/data/nasa_power_agroguardian_training.csv`.
As variaveis reais usadas sao temperatura, umidade relativa, pressao de
superficie, precipitacao e vento. O alvo `risk_score` continua heuristico ate o
projeto receber uma base real de sinistros/ocorrencias por equipamento.
