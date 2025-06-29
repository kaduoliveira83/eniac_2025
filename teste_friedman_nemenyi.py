# -*- coding: utf-8 -*-
"""teste_friedman_nemenyi

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/122jnrJdPOd_ULB6sO8yH7-jDnDmO0j9z
"""

# Atualizar pacotes no Google Colab para evitar conflitos
!pip install --upgrade numpy pandas scipy matplotlib scikit-posthocs orange3 -q

# Reiniciar automaticamente o ambiente (importante para evitar erros de compatibilidade)
import os
import IPython
os.kill(os.getpid(), 9)

!pip install fpdf

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import friedmanchisquare
import scikit_posthocs as sp
from fpdf import FPDF
import matplotlib.image as mpimg

# Load data
df_transformer = pd.read_csv("transformers_artigo_avaliacao.csv")
df_lstm = pd.read_csv("lstm_evaluation.csv")
df_gru = pd.read_csv("gru_evaluation.csv")

# Add model name
df_transformer["model"] = "Transformer"
df_lstm["model"] = "LSTM"
df_gru["model"] = "GRU"

# Combine all data
df_all = pd.concat([df_transformer, df_lstm, df_gru])

# Define groups
groups = {
    "Group_1_1-16": df_all[df_all["tamanho_janela"].between(1, 16)],
    "Group_2_17-33": df_all[df_all["tamanho_janela"].between(17, 33)],
    "Group_3_34-50": df_all[df_all["tamanho_janela"].between(34, 50)],
}

# Function to apply tests and generate CD plot
def apply_cd_test_and_plot(df_group, group_name):
    pivot = df_group.pivot_table(
        index=["tamanho_janela", "horizonte_previsao"],
        columns="model",
        values="rmse"
    ).dropna()

    stat, p_value = friedmanchisquare(pivot["GRU"], pivot["LSTM"], pivot["Transformer"])
    print(f"\n== {group_name} ==")
    print(f"Friedman statistic: {stat:.4f}")
    print(f"p-value: {p_value:.4g}")

    if p_value >= 0.05:
        print("↪ No statistically significant differences detected.")
        return

    # Nemenyi test
    nemenyi = sp.posthoc_nemenyi_friedman(pivot.to_numpy())
    nemenyi.columns = ["GRU", "LSTM", "Transformer"]
    nemenyi.index = ["GRU", "LSTM", "Transformer"]
    print("\nNemenyi test results (pairwise p-values):")
    print(nemenyi.round(4))

    # Ranking
    ranks = pivot.rank(axis=1, method='average')
    mean_ranks = ranks.mean().sort_values()
    models = mean_ranks.index.tolist()

    # Define custom vertical offsets to avoid overlap
    text_offsets = {"GRU": 0.3, "LSTM": 0.5, "Transformer": 0.3}

    # Plot CD
    fig, ax = plt.subplots(figsize=(6, 1.8), facecolor='white')

    y = np.zeros(len(mean_ranks))
    ax.scatter(mean_ranks.values, y, s=100, color='black', zorder=3)

    for model, rank in mean_ranks.items():
        offset = text_offsets.get(model, 0.3)
        ax.text(rank, offset, model, ha='center', va='bottom', fontsize=10)

    ax.set_ylim(-0.5, 1.0)
    ax.set_xlim(mean_ranks.min() - 0.5, mean_ranks.max() + 0.5)
    ax.set_yticks([])
    ax.set_xlabel("Average Rank (lower is better)", fontsize=10)
    ax.set_title(f"Critical Difference Plot - {group_name.replace('_', ' ')}", fontsize=12)
    ax.grid(axis='x', linestyle='--', alpha=0.5)

    # Draw lines for models with no statistical difference
    threshold = 0.05
    offset = 0.15
    step = 0.05
    line_idx = 0

    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            pval = nemenyi.loc[models[i], models[j]]
            if pval >= threshold:
                x1, x2 = mean_ranks[models[i]], mean_ranks[models[j]]
                y_line = -offset - line_idx * step
                ax.plot([x1, x2], [y_line, y_line], color='black', lw=1)
                line_idx += 1

    # Caption
    plt.figtext(0.5, -0.25,
        "Models connected by a line are not statistically different (Nemenyi test, p ≥ 0.05).",
        ha='center', fontsize=9)

    # Save image
    image_filename = f"CD_plot_{group_name}.png"
    plt.tight_layout()
    plt.savefig(image_filename, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✅ Image saved: {image_filename}")

    # Save to individual PDF
    img = mpimg.imread(image_filename)
    h, w = img.shape[:2]
    scale = min(180 / w, 130 / h)
    w_scaled = w * scale
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.multi_cell(0, 10, f"Critical Difference Plot - {group_name.replace('_', ' ')}", align="C")
    pdf.ln(5)
    pdf.image(image_filename, x=(210 - w_scaled) / 2, w=w_scaled)
    pdf_filename = f"{image_filename.replace('.png', '.pdf')}"
    pdf.output(pdf_filename)
    print(f"✅ PDF saved: {pdf_filename}")

# Run for each group
for group_name, df_group in groups.items():
    apply_cd_test_and_plot(df_group, group_name)

