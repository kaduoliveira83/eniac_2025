# -*- coding: utf-8 -*-
"""gru_artigo

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1-kYfTqK3egp6MXn23YlF_v-e8vsDEpLj
"""

# =====================
# 1. IMPORTAÇÃO DAS BIBLIOTECAS
# =====================
import optuna
import time
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error
from torch.utils.data import DataLoader, TensorDataset
import os

# =====================
# 2. CONFIGURAÇÕES INICIAIS
# =====================
optuna.logging.set_verbosity(optuna.logging.WARNING)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

save_path = "/media/work/carlosoliveira/resultados_modelos_gru"
os.makedirs(save_path, exist_ok=True)

# =====================
# 3. LEITURA E CONVERSÃO TEMPORAL DOS DADOS
# =====================
dados = pd.read_csv('/media/work/carlosoliveira/id_21_completo.csv')
dados['ds'] = pd.to_datetime(dados['ds'], errors='coerce')

# =====================
# 4. SEPARAÇÃO TEMPORAL DOS DADOS
# =====================
valores = dados[['delay_60']].values.reshape(-1, 1)
n = len(valores)
split_1 = int(0.7 * n)
split_2 = int(0.85 * n)
valores_treino      = valores[:split_1]
valores_validacao   = valores[split_1:split_2]
valores_teste       = valores[split_2:]

# =====================
# 5. NORMALIZAÇÃO DOS DADOS
# =====================
scaler = StandardScaler()
scaler.fit(valores_treino)
valores_treino    = scaler.transform(valores_treino)
valores_validacao = scaler.transform(valores_validacao)
valores_teste     = scaler.transform(valores_teste)

# =====================
# 6. GERAÇÃO DE JANELAS DESLIZANTES
# =====================
def gerar_janelas(data, tamanho_janela, horizonte_previsao):
    X, y = [], []
    L = len(data)
    for i in range(L - tamanho_janela - horizonte_previsao + 1):
        X.append(data[i : i + tamanho_janela])
        y.append(data[i + tamanho_janela : i + tamanho_janela + horizonte_previsao])
    X = np.array(X).reshape(-1, tamanho_janela, 1)
    y = np.array(y).reshape(-1, horizonte_previsao)
    return X, y

# =====================
# 7. MODELO GRU
# =====================
class GRUModel(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers, dropout, output_size):
        super().__init__()
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True
        )
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        out, _ = self.gru(x)         # out: (batch, seq_len, hidden_size)
        out = out[:, -1, :]          # pega apenas a última saída
        return self.fc(out)

# =====================
# 8. TREINAMENTO COM EARLY STOPPING
# =====================
def run_model(jan, hor, X_tr, y_tr, X_va, y_va, hid, nlayers, drop, lr, epochs=100, patience=10):
    model = GRUModel(1, hid, nlayers, drop, hor).to(device)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)
    ds = TensorDataset(torch.Tensor(X_tr), torch.Tensor(y_tr))
    loader = DataLoader(ds, batch_size=32, shuffle=True)

    best = float('inf')
    wait = 0
    for _ in range(epochs):
        model.train()
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            val_pred = model(torch.Tensor(X_va).to(device))
            vloss = criterion(val_pred, torch.Tensor(y_va).to(device)).item()
        if vloss < best:
            best = vloss
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break
    return model

# =====================
# 9. FUNÇÃO OBJETIVO DO OPTUNA (FIXOS: janela & horizonte)
# =====================
def objective(trial, jan, hor):
    hid     = trial.suggest_int('hidden_size', 16, 256)
    nlayers = trial.suggest_int('num_layers', 1, 3)
    drop    = trial.suggest_float('dropout', 0.0, 0.5)
    lr      = trial.suggest_float('lr', 1e-5, 1e-2)

    X_tr, y_tr = gerar_janelas(valores_treino, jan, hor)
    X_va, y_va = gerar_janelas(valores_validacao, jan, hor)
    if len(X_tr)==0 or len(X_va)==0:
        return float('inf')

    mdl = run_model(jan, hor, X_tr, y_tr, X_va, y_va, hid, nlayers, drop, lr)
    mdl.eval()
    with torch.no_grad():
        y_pred = mdl(torch.Tensor(X_va).to(device)).cpu().numpy()
    return np.sqrt(mean_squared_error(y_va, y_pred))

# =====================
# 10. OTIMIZAÇÃO PARA 9 CASOS FIXOS
# =====================
casos = [(12,12),(24,12),(48,12),
         (12,24),(24,24),(48,24),
         (12,48),(24,48),(48,48)]

best_params = {}
for jan, hor in casos:
    print(f"\nOtimizando GRU para janela={jan}, horizonte={hor}...")
    study = optuna.create_study(direction='minimize')
    t0 = time.time()
    study.optimize(lambda t: objective(t, jan, hor), n_trials=50)
    print(f"→ tempo: {time.time()-t0:.1f}s, params: {study.best_params}")
    best_params[(jan,hor)] = study.best_params

pd.DataFrame([
    {'tamanho_janela': j, 'horizonte_previsao': h, **p}
    for (j,h), p in best_params.items()
]).to_csv(f"{save_path}/gru_best_params.csv", index=False)

# =====================
# 11. SELEÇÃO POR CENTRÓIDE
# =====================
def pick_params(jan, hor, params_dict):
    dists = { (j,h): np.hypot(jan-j, hor-h) for (j,h) in params_dict }
    nearest = min(dists, key=dists.get)
    return params_dict[nearest]

# =====================
# 12. AVALIAÇÃO FINAL COM MÉTRICAS
# =====================
results = []
for jan in range(1,49):
    for hor in range(1,49):
        X_tr, y_tr = gerar_janelas(valores_treino, jan, hor)
        X_va, y_va = gerar_janelas(valores_validacao, jan, hor)
        X_te, y_te = gerar_janelas(valores_teste, jan, hor)
        if min(len(X_tr), len(X_va), len(X_te)) == 0:
            continue

        # combina treino + validação para treinar
        X_comb = np.vstack((X_tr, X_va))
        y_comb = np.vstack((y_tr, y_va))

        params = pick_params(jan, hor, best_params)
        mdl = run_model(jan, hor, X_comb, y_comb, X_te, y_te,
                        params['hidden_size'], params['num_layers'],
                        params['dropout'], params['lr'])
        mdl.eval()
        with torch.no_grad():
            y_pred = mdl(torch.Tensor(X_te).to(device)).cpu().numpy()

        mse  = mean_squared_error(y_te, y_pred)
        rmse = np.sqrt(mse)
        mae  = mean_absolute_error(y_te, y_pred)
        mape = (np.abs((y_te - y_pred)/(y_te + 1e-8)).mean()) * 100

        results.append({
            'tamanho_janela': jan,
            'horizonte_previsao': hor,
            'mae': mae, 'mse': mse,
            'rmse': rmse, 'mape': mape
        })

df = pd.DataFrame(results)
df.to_csv(f"{save_path}/gru_evaluation.csv", index=False)
print("Resultados GRU salvos em gru_evaluation.csv")