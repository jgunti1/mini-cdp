import pandas as pd


subs = pd.read_csv("data/subscribers.csv", dtype=str, keep_default_na=False)
web = pd.read_csv("data/web_events.csv", dtype=str, keep_default_na=False)
app = pd.read_csv("data/app_users.csv", dtype=str, keep_default_na=False)

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)
# -- Check for duplicates in the email column of the subscribers dataset --
# print(subs["email"].duplicated().sum())                 # raw
# print(subs["email"].str.lower().duplicated().sum())     # after lowercasing

subs["email_norm"] = subs["email"].str.lower()   # plus your third step
dupes = subs[subs["email_norm"].duplicated(keep=False) & (subs["email_norm"] != "")]
# print(dupes.sort_values("email_norm").head(20))

# values that have leading or trailing whitespace
real = subs[subs["email"] != ""]
# print(real[0:3])

dupes = subs[subs["email_norm"].duplicated(keep=False) & (subs["email_norm"] != "")]
# print(dupes.sort_values("email_norm").head(20))

real = subs[subs["email_norm"] != ""]
cols = ["signup_date", "status", "acquisition_source", "last_open_date"]
conflicts = real.groupby("email_norm")[cols].nunique().gt(1).sum()
print(conflicts)

# print(real["email"].map(repr).sample(40, random_state=1).to_list())

# 22 emails with trailing spaces
has_space = subs[subs["email"] != subs["email"].str.strip()]
# print("emails with extra spaces:", len(has_space))
# print(has_space["email"].map(repr).head(5).to_list())

# subs["email_norm"] = subs["email"].str.strip().str.lower()
# real = subs[subs["email_norm"] != ""]
# print("duplicates after strip + lowercase:", real["email_norm"].duplicated().sum())