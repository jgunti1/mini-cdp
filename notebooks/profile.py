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

# real = subs[subs["email_norm"] != ""]
cols = ["signup_date", "status", "acquisition_source", "last_open_date"]
conflicts = real.groupby("email_norm")[cols].nunique().gt(1).sum()
# print(conflicts)

# print(real["email"].map(repr).sample(40, random_state=1).to_list())

# 22 emails with trailing spaces
has_space = subs[subs["email"] != subs["email"].str.strip()]
# print("emails with extra spaces:", len(has_space))
# print(has_space["email"].map(repr).head(5).to_list())

subs["email_norm"] = subs["email"].str.strip().str.lower()
real = subs[subs["email_norm"] != ""]
# print("duplicates after strip + lowercase:", real["email_norm"].duplicated().sum())


'''
Check fake emails
'''
no_at = real[~real["email_norm"].str.contains("@")]
# print("emails with no @:", len(no_at))
# print(no_at)

pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
invalid = real[~real["email_norm"].str.match(pattern)]
print("invalid emails:", len(invalid))
print(invalid)


print("\n===== Checks 4-6 =====")
# --- Check 4: source names across files ---
print(real["acquisition_source"].value_counts())
print(web["utm_source"].value_counts())

# --- Check 5: web events -> subscribers ---
web["email_norm"] = web["email"].str.strip().str.lower()
valid = set(real["email_norm"])
has_email = web[web["email_norm"] != ""]
print("web rows with an email:", len(has_email))
print("  match subscribers raw:", has_email["email"].isin(set(subs["email"])).sum())
print("  match after normalizing:", has_email["email_norm"].isin(valid).sum())
print("  pages where email is captured:", has_email["page"].value_counts().to_dict())
identified = set(has_email["visitor_id"])
print("visitors total:", web["visitor_id"].nunique(), "| with an email:", len(identified))
print("rows with no email, but from an identified visitor:",
      len(web[(web["email_norm"] == "") & web["visitor_id"].isin(identified)]))

# --- Check 6: app users -> subscribers ---
app["email_norm"] = app["email"].str.strip().str.lower()
print("app users:", len(app))
print("  match subscribers raw:", app["email"].isin(set(subs["email"])).sum())
print("  match after normalizing:", app["email_norm"].isin(valid).sum())
print(app[~app["email_norm"].isin(valid)].head())