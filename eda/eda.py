import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

IN_PATH = os.path.join("data", "grid-queue-data.csv")

df = pd.read_csv(IN_PATH)

def returnunique(column):
    return df[column].unique()

def ratiocalc(category):
    counts = df["q_status"].value_counts()
    total = counts.sum()
    category_sum = df["q_status"].value_counts()[category]
    return category_sum / total
    


print(df["q_status"].value_counts())
print(returnunique("q_status"))
print(ratiocalc("withdrawn"))

def distribution(column):
    s = df[column]
    s = s[s.notna() & (s > 0)]

    bins = np.logspace(np.log10(s.min()), np.log10(s.max()), 50)
    fig, ax = plt.subplots()
    ax.hist(s, bins=bins)
    ax.set_xscale("log")
    ax.set_xlabel("col (log scale)")
    ax.set_ylabel("Count")
    plt.show()

# distribution("mw_1")