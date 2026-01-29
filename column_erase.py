import pandas as pd

df = pd.read_csv("csv/US/trend.csv")

# remove last column
df = df.iloc[:, :-1]

df.to_csv("csv/US/trend.csv", index=False)
